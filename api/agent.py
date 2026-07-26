"""The census agent.

`stream_ask` is the real entry point: an async generator of typed events that
the SSE endpoint forwards more or less verbatim. `ask` is a thin synchronous
wrapper kept so the CLI below and the Streamlit app still work while the React
frontend is being built.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

import anthropic
from dotenv import load_dotenv

from . import config, db

load_dotenv()

log = logging.getLogger("api.agent")

# Constructed lazily so importing this module (in tests, or to reach TOOLS)
# does not require credentials.
_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


def calculate_change(value_start: float, value_end: float) -> dict:
    absolute_change = value_end - value_start
    percent_change = (absolute_change / value_start) * 100 if value_start != 0 else None
    return {
        "absolute_change": absolute_change,
        "percent_change": round(percent_change, 2) if percent_change is not None else None,
    }


# Order is load-bearing: tools render first in the cached prefix, so reordering
# this list invalidates the prompt cache on every subsequent request.
TOOLS = [
    {
        "name": "query_census",
        "description": (
            "Query Boroondara census data by category and subcategory. "
            "Returns year/value pairs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "subcategory": {"type": "string"},
            },
            "required": ["category", "subcategory"],
        },
    },
    {
        "name": "calculate_change",
        "description": (
            "Calculate the absolute and percentage change between two numeric values "
            "(e.g. comparing a metric between two years). Always use this instead of "
            "computing changes yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "value_start": {"type": "number", "description": "The earlier/starting value"},
                "value_end": {"type": "number", "description": "The later/ending value"},
            },
            "required": ["value_start", "value_end"],
        },
    },
]

TOOL_IMPLS = {
    "query_census": lambda **kw: db.query_census(**kw),
    "calculate_change": lambda **kw: calculate_change(**kw),
}

# A turn that keeps calling tools without concluding would otherwise hold the
# rate limiter's global slot until it exhausted itself. Two tools over three
# census years never needs anywhere near this many round trips.
MAX_TOOL_ITERATIONS = 10


def system_blocks() -> list[dict[str, Any]]:
    """System prompt as content blocks, with the whole thing marked cacheable.

    cache_control on the last (only) system block caches tools + system
    together, since tools render ahead of system in the prefix. The schema
    summary is ~1600 tokens, comfortably over Sonnet 4.5's 1024-token minimum.
    Read the note on config.MODEL before changing models — Opus 4.8's minimum
    is 4096 and this block would silently stop caching.
    """
    text = (
        "You are a census data assistant for Boroondara, Australia.\n"
        "You have access to a query_census tool. The database contains these exact \n"
        "categories and subcategories - always use these EXACT values, never guess \n"
        "or paraphrase them:\n\n"
        f"{db.schema_summary()}\n\n"
        "When comparing values across years or calculating growth/change, always \n"
        "use the calculate_change tool rather than computing the difference yourself."
    )
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


async def stream_ask(messages: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    """Run the tool loop, yielding events as they happen.

    Event shapes (mirrored by hand in web/src/api/events.ts — OpenAPI does not
    describe SSE, so those two definitions have no compiler keeping them
    honest):

        {"type": "text",        "text": str}
        {"type": "tool_use",    "id": str, "name": str, "input": dict}
        {"type": "tool_result", "tool_use_id": str, "content": str, "is_error": bool}
        {"type": "error",       "message": str, "retryable": bool}
        {"type": "done",        "stop_reason": str}

    The caller owns the conversation history; this never mutates the list it is
    given.
    """
    messages = list(messages)

    try:
        system = system_blocks()
    except db.DatabaseMissing as exc:
        yield {"type": "error", "message": str(exc), "retryable": False}
        return

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            async with client().messages.stream(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                system=system,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield {"type": "text", "text": event.delta.text}
                response = await stream.get_final_message()

            # Cache behaviour is otherwise invisible: a prompt that silently
            # stops caching costs ~1600 tokens a turn with no error to notice.
            # After the first turn, cache_read should be non-zero and input
            # small — if cache_read stays 0, something is invalidating the
            # prefix (see the note on config.MODEL about cache minimums).
            usage = response.usage
            log.info(
                "tokens: input=%s cache_write=%s cache_read=%s output=%s",
                usage.input_tokens,
                usage.cache_creation_input_tokens,
                usage.cache_read_input_tokens,
                usage.output_tokens,
            )
        except anthropic.APIStatusError as exc:
            yield {
                "type": "error",
                "message": f"The model API returned an error ({exc.status_code}).",
                # 429 and 5xx are worth another go; a 400 would fail identically.
                "retryable": exc.status_code == 429 or exc.status_code >= 500,
            }
            return
        except anthropic.APIConnectionError:
            yield {
                "type": "error",
                "message": "Could not reach the model API.",
                "retryable": True,
            }
            return

        if response.stop_reason != "tool_use":
            yield {"type": "done", "stop_reason": response.stop_reason}
            return

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            yield {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }

            impl = TOOL_IMPLS.get(block.name)
            if impl is None:
                content, is_error = f"Unknown tool: {block.name}", True
            else:
                try:
                    content, is_error = str(impl(**block.input)), False
                except Exception as exc:  # returned to the model so it can adapt
                    content, is_error = f"{type(exc).__name__}: {exc}", True

            result_block = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
                "is_error": is_error,
            }
            yield dict(result_block)
            tool_results.append(result_block)

        messages.append({"role": "user", "content": tool_results})

    yield {
        "type": "error",
        "message": f"Gave up after {MAX_TOOL_ITERATIONS} tool calls without an answer.",
        "retryable": True,
    }


def ask(question: str) -> str:
    """Synchronous single-question helper.

    Kept for the CLI below and the Streamlit app. Note it is genuinely
    single-shot — no history — which is the limitation the streaming API
    exists to fix.
    """
    import asyncio

    async def _collect() -> str:
        parts: list[str] = []
        async for event in stream_ask([{"role": "user", "content": question}]):
            if event["type"] == "text":
                parts.append(event["text"])
            elif event["type"] == "error":
                raise RuntimeError(event["message"])
        return "".join(parts)

    return asyncio.run(_collect())


if __name__ == "__main__":
    print(ask("How did the number of separate houses change between 2016 and 2021?"))
