"""The census agent.

`stream_ask` is the entry point: an async generator of typed events that the
SSE endpoint forwards more or less verbatim, consumed by the React frontend
in `web/`.
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


def _format_query_census(result: dict) -> str:
    """Render per-area series for the model, making a gap explicit.

    An area with no rows for the subcategory (a curated gap, or an area that
    does not carry that metric) is reported as "no data available" rather than
    omitted — otherwise the model is liable to read absence as a zero.
    """
    lines = []
    for geo_code, info in result.items():
        if info["series"]:
            points = ", ".join(f"{year}: {value}" for year, value in info["series"])
            lines.append(f"{info['name']} ({geo_code}): {points}")
        else:
            lines.append(
                f"{info['name']} ({geo_code}): no data available for this subcategory"
            )
    return "\n".join(lines) if lines else "no data available for the requested areas"


def _format_find_geography(matches: list[dict]) -> str:
    if not matches:
        return "no matching areas found"
    return "\n".join(f"{m['geo_name']} -> geo_code {m['geo_code']}" for m in matches)


# Order is load-bearing: tools render first in the cached prefix, so reordering
# this list invalidates the prompt cache on every subsequent request. New tools
# and fields are appended, never inserted.
TOOLS = [
    {
        "name": "query_census",
        "description": (
            "Query census data for one or more areas at a chosen granularity "
            "(LGA or State). Returns per-area year/value series."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "subcategory": {"type": "string"},
                "level": {
                    "type": "string",
                    "enum": ["LGA", "STE"],
                    "description": "Granularity: 'LGA' (local government area) or 'STE' (state/territory).",
                },
                "geo_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": config.AGENT_MAX_GEO_CODES,
                    "description": "Area identifiers from find_geography. Pass several to compare areas.",
                },
            },
            "required": ["category", "subcategory", "level", "geo_codes"],
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
    {
        "name": "find_geography",
        "description": (
            "Resolve an area name to its geo_code(s) at a granularity (LGA or "
            "State). Call this before query_census to turn a place name into the "
            "geo_codes it needs. Returns candidate areas; if more than one "
            "matches, pick the intended area or ask the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["LGA", "STE"]},
                "name_query": {
                    "type": "string",
                    "description": "Part of an area's name, e.g. 'Boroondara' or 'Victoria'.",
                },
            },
            "required": ["level", "name_query"],
        },
    },
]

TOOL_IMPLS = {
    "query_census": lambda **kw: _format_query_census(db.query_census(**kw)),
    "calculate_change": lambda **kw: calculate_change(**kw),
    "find_geography": lambda **kw: _format_find_geography(db.find_geography(**kw)),
}

# A turn that keeps calling tools without concluding would otherwise hold the
# rate limiter's global slot until it exhausted itself. A find_geography lookup
# followed by a query or two over three census years never needs anywhere near
# this many round trips.
MAX_TOOL_ITERATIONS = 10

# Why the answer stopped, when it stopped for a reason worth telling the user
# about. Anything not listed here and not "tool_use" is treated as a normal
# finish. The failure this guards against: a turn cut off mid-generation used to
# be reported as a completed one, so the UI showed the model's "I'll retrieve
# that now…" preamble as if it were the whole answer.
INTERRUPTED_STOP_REASONS = {
    "max_tokens": (
        "The answer was cut off because it got too long. Try asking about a "
        "narrower slice of the data.",
        True,
    ),
    "model_context_window_exceeded": (
        "This conversation has grown too long for the model to process. Start a "
        "new one to continue.",
        False,
    ),
    "refusal": (
        "The model declined to answer this one.",
        False,
    ),
}


def system_blocks() -> list[dict[str, Any]]:
    """System prompt as content blocks, with the whole thing marked cacheable.

    cache_control on the last (only) system block caches tools + system
    together, since tools render ahead of system in the prefix. The schema
    summary is ~1600 tokens, comfortably over Sonnet 4.5's 1024-token minimum.
    Read the note on config.MODEL before changing models — Opus 4.8's minimum
    is 4096 and this block would silently stop caching.

    The vocabulary is identical across levels, so the summary is injected once
    (for the default level) and stays byte-identical from turn to turn — which
    is what keeps the cached prefix stable.
    """
    text = (
        "You are a census data assistant for Australian census data at Local "
        "Government Area (LGA) and State/Territory (STE) level.\n"
        "Areas are identified by a stable geo_code, not their name: a name can "
        "drift across census years or be shared by two areas. To answer a "
        "question about a place, first call find_geography to turn its name into "
        "geo_code(s), then call query_census with those codes. To compare areas, "
        "pass several geo_codes in a single query_census call.\n"
        "Available levels: LGA (local government areas) and STE (states and "
        "territories).\n\n"
        "The database contains these exact categories and subcategories - always "
        "use these EXACT values, never guess or paraphrase them:\n\n"
        f"{db.schema_summary(config.DEFAULT_LEVEL)}\n\n"
        "When comparing values across years or calculating growth/change, always "
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
            interrupted = INTERRUPTED_STOP_REASONS.get(response.stop_reason or "")
            if interrupted is not None:
                # Report it as a failure even though whatever streamed so far is
                # kept. Ending on a bare `done` here is what made a cut-off turn
                # look finished.
                message, retryable = interrupted
                log.warning("turn ended early: stop_reason=%s", response.stop_reason)
                yield {"type": "error", "message": message, "retryable": retryable}
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


