import anthropic
import httpx
import pytest

from api import agent, config, db
from tests.conftest import FakeAnthropic, text_block, tool_use_block, turn


async def collect(messages):
    return [event async for event in agent.stream_ask(messages)]


def install(monkeypatch, turns) -> FakeAnthropic:
    fake = FakeAnthropic(turns)
    monkeypatch.setattr(agent, "client", lambda: fake)
    return fake


async def test_plain_answer_streams_text_then_done(census_db, monkeypatch):
    install(monkeypatch, [turn(text="Boroondara had 167,900 people in 2021.")])

    events = await collect([{"role": "user", "content": "How many people in 2021?"}])

    assert [e["type"] for e in events] == ["text", "done"]
    assert events[0]["text"].startswith("Boroondara")
    assert events[-1]["stop_reason"] == "end_turn"


async def test_tool_call_emits_use_then_result_with_real_data(census_db, monkeypatch):
    install(
        monkeypatch,
        [
            turn(
                stop_reason="tool_use",
                content=[
                    tool_use_block(
                        "toolu_1",
                        "query_census",
                        {"category": "dwelling_structure", "subcategory": "separate house"},
                    )
                ],
            ),
            turn(text="Separate houses grew from 39,500 to 40,100."),
        ],
    )

    events = await collect([{"role": "user", "content": "separate houses?"}])

    assert [e["type"] for e in events] == ["tool_use", "tool_result", "text", "done"]
    assert events[0]["name"] == "query_census"
    # The result carries the actual rows, which is what makes the expandable
    # chip a verification surface rather than decoration.
    assert "39500" in events[1]["content"]
    assert events[1]["is_error"] is False


async def test_tool_results_are_fed_back_to_the_model(census_db, monkeypatch):
    fake = install(
        monkeypatch,
        [
            turn(
                stop_reason="tool_use",
                content=[tool_use_block("toolu_1", "calculate_change", {
                    "value_start": 39500, "value_end": 40100
                })],
            ),
            turn(text="A 1.52% increase."),
        ],
    )

    await collect([{"role": "user", "content": "change?"}])

    second_call = fake.calls[1]["messages"]
    assert second_call[-2]["role"] == "assistant"
    assert second_call[-1]["role"] == "user"
    result = second_call[-1]["content"][0]
    assert result["tool_use_id"] == "toolu_1"
    assert "1.52" in result["content"]


async def test_caller_history_is_not_mutated(census_db, monkeypatch):
    install(
        monkeypatch,
        [
            turn(
                stop_reason="tool_use",
                content=[tool_use_block("toolu_1", "calculate_change", {
                    "value_start": 1, "value_end": 2
                })],
            ),
            turn(text="Doubled."),
        ],
    )

    history = [{"role": "user", "content": "hi"}]
    await collect(history)

    # The client owns the conversation; the server appending to it in place
    # would silently corrupt the next request.
    assert history == [{"role": "user", "content": "hi"}]


async def test_multi_turn_history_reaches_the_model(census_db, monkeypatch):
    fake = install(monkeypatch, [turn(text="In 2016 it was 39,500.")])

    history = [
        {"role": "user", "content": "How many separate houses in 2021?"},
        {"role": "assistant", "content": "40,100."},
        {"role": "user", "content": "And in 2016?"},
    ]
    await collect(history)

    # The follow-up is only answerable because the earlier turns were sent —
    # this is the bug the old single-shot ask() had.
    assert len(fake.calls[0]["messages"]) == 3


async def test_unknown_tool_reports_an_error_result(census_db, monkeypatch):
    install(
        monkeypatch,
        [
            turn(
                stop_reason="tool_use",
                content=[tool_use_block("toolu_1", "nonexistent_tool", {})],
            ),
            turn(text="Sorry."),
        ],
    )

    events = await collect([{"role": "user", "content": "?"}])
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] is True
    assert "nonexistent_tool" in result["content"]


async def test_failing_tool_is_reported_not_raised(census_db, monkeypatch):
    install(
        monkeypatch,
        [
            turn(
                stop_reason="tool_use",
                # Wrong argument name — the impl raises TypeError.
                content=[tool_use_block("toolu_1", "calculate_change", {"wrong": 1})],
            ),
            turn(text="Let me try differently."),
        ],
    )

    events = await collect([{"role": "user", "content": "?"}])
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] is True
    # The model gets to see the failure and adapt, rather than the stream dying.
    assert events[-1]["type"] == "done"


async def test_runaway_tool_loop_is_bounded(census_db, monkeypatch):
    looping = turn(
        stop_reason="tool_use",
        content=[tool_use_block("toolu_x", "calculate_change", {
            "value_start": 1, "value_end": 2
        })],
    )
    install(monkeypatch, [looping] * (agent.MAX_TOOL_ITERATIONS + 2))

    events = await collect([{"role": "user", "content": "?"}])

    assert events[-1]["type"] == "error"
    assert events[-1]["retryable"] is True
    assert len([e for e in events if e["type"] == "tool_use"]) == agent.MAX_TOOL_ITERATIONS


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(429, True), (500, True), (503, True), (400, False)],
)
async def test_api_errors_become_error_events(census_db, monkeypatch, status, retryable):
    def boom(**kwargs):
        raise anthropic.APIStatusError(
            "upstream said no",
            response=httpx.Response(
                status_code=status, request=httpx.Request("POST", "http://x")
            ),
            body=None,
        )

    from types import SimpleNamespace

    monkeypatch.setattr(
        agent, "client", lambda: SimpleNamespace(messages=SimpleNamespace(stream=boom))
    )

    events = await collect([{"role": "user", "content": "?"}])
    assert events[-1]["type"] == "error"
    assert events[-1]["retryable"] is retryable


async def test_missing_database_yields_an_error_event(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gone.db")
    db._schema_cache.clear()

    events = await collect([{"role": "user", "content": "?"}])
    assert events == [
        {"type": "error", "message": events[0]["message"], "retryable": False}
    ]
    assert "not found" in events[0]["message"]


# --- prompt caching -------------------------------------------------------


async def test_system_block_is_marked_cacheable(census_db, monkeypatch):
    fake = install(monkeypatch, [turn(text="ok")])
    await collect([{"role": "user", "content": "?"}])

    system = fake.calls[0]["system"]
    assert system[-1]["cache_control"] == {"type": "ephemeral"}


async def test_system_prompt_is_byte_identical_across_turns(census_db, monkeypatch):
    fake = install(monkeypatch, [turn(text="a"), turn(text="b")])

    await collect([{"role": "user", "content": "one"}])
    await collect([{"role": "user", "content": "two"}])

    # Any drift here — a timestamp, a re-sorted dict — silently costs a cache
    # miss on every request with no error to notice.
    assert fake.calls[0]["system"] == fake.calls[1]["system"]


def test_schema_summary_is_memoized(census_db):
    first = db.schema_summary()
    assert db.schema_summary() is first, "should be served from the memo"
    assert "dwelling_structure: flat or apartment, separate house" in first


def test_schema_summary_refreshes_when_the_database_changes(census_db):
    import os
    import sqlite3
    import time

    before = db.schema_summary()
    assert "brand_new_category" not in before

    conn = sqlite3.connect(census_db)
    conn.execute(
        "INSERT INTO census_data VALUES ('Boroondara', 2021, 'brand_new_category', 'x', 1)"
    )
    conn.commit()
    conn.close()
    # The memo is keyed on mtime; nudge it so the test does not depend on the
    # filesystem's timestamp resolution.
    stamp = time.time() + 10
    os.utime(census_db, (stamp, stamp))

    # The database is bind-mounted and can change under a running process, so
    # the memo has to notice without a restart.
    assert "brand_new_category" in db.schema_summary()


async def test_token_usage_is_logged(census_db, monkeypatch, caplog):
    """Cache behaviour has to be observable or a silent regression is free.

    A prompt that stops caching costs ~1600 tokens per turn and raises nothing.
    """
    from types import SimpleNamespace

    usage = SimpleNamespace(
        input_tokens=12,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=1604,
        output_tokens=41,
    )
    events, final = turn(text="ok")
    final.usage = usage
    install(monkeypatch, [(events, final)])

    with caplog.at_level("INFO", logger="api.agent"):
        await collect([{"role": "user", "content": "?"}])

    assert "cache_read=1604" in caplog.text


# --- how turns end ---------------------------------------------------------


async def test_normal_finish_reports_done_with_no_error(census_db, monkeypatch):
    install(monkeypatch, [turn(text="167,900 people.")])

    events = await collect([{"role": "user", "content": "?"}])

    assert [e["type"] for e in events] == ["text", "done"]
    assert events[-1]["stop_reason"] == "end_turn"


async def test_truncated_turn_is_reported_as_an_error(census_db, monkeypatch):
    """A turn cut off mid-generation must not look like a finished one.

    Reproduces the real failure: asked about a 15-bracket category, the model
    wrote "I'll retrieve that now…" and then ran out of budget emitting its
    tool calls. stop_reason was "max_tokens" with zero usable tool calls, and
    the UI presented the preamble as the complete answer.
    """
    install(
        monkeypatch,
        [turn(text="I'll retrieve the family income data now.", stop_reason="max_tokens")],
    )

    events = await collect([{"role": "user", "content": "family income for couples"}])

    kinds = [e["type"] for e in events]
    assert "error" in kinds, "a truncated turn must surface an error"
    assert kinds.index("error") < kinds.index("done")

    error = next(e for e in events if e["type"] == "error")
    assert "cut off" in error["message"]
    assert error["retryable"] is True

    # Whatever did stream is kept — the user should see the partial text, just
    # not be told it is the whole answer.
    assert any(e["type"] == "text" for e in events)


async def test_context_window_exhaustion_is_not_retryable(census_db, monkeypatch):
    install(
        monkeypatch,
        [turn(text="", stop_reason="model_context_window_exceeded")],
    )

    events = await collect([{"role": "user", "content": "?"}])
    error = next(e for e in events if e["type"] == "error")
    # Retrying the same oversized conversation fails identically.
    assert error["retryable"] is False
    assert "new one" in error["message"]


async def test_refusal_is_surfaced(census_db, monkeypatch):
    install(monkeypatch, [turn(text="", stop_reason="refusal")])

    events = await collect([{"role": "user", "content": "?"}])
    error = next(e for e in events if e["type"] == "error")
    assert error["retryable"] is False
    assert "declined" in error["message"]


async def test_unrecognised_stop_reason_is_treated_as_a_normal_finish(
    census_db, monkeypatch
):
    install(monkeypatch, [turn(text="fine", stop_reason="something_new")])

    events = await collect([{"role": "user", "content": "?"}])
    # A stop reason we have not seen should not invent a user-facing failure.
    assert [e["type"] for e in events] == ["text", "done"]


async def test_max_tokens_is_high_enough_for_a_wide_fan_out(census_db, monkeypatch):
    """Fifteen tool calls in one turn is a real shape, not a hypothetical.

    family_income_couple_by_children has 15 subcategories, and the model asks
    for all of them at once.
    """
    calls = [
        tool_use_block(f"toolu_{i}", "query_census", {
            "category": "family_income_couple_by_children",
            "subcategory": f"bracket {i}",
        })
        for i in range(15)
    ]
    fake = install(
        monkeypatch,
        [
            turn(stop_reason="tool_use", content=calls),
            turn(text="Here is the distribution."),
        ],
    )

    events = await collect([{"role": "user", "content": "family income?"}])

    assert len([e for e in events if e["type"] == "tool_use"]) == 15
    assert events[-1]["type"] == "done"
    # Headroom for that many blocks plus prose; 1024 was not enough.
    assert fake.calls[0]["max_tokens"] >= 4096
