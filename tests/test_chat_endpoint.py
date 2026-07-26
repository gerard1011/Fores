"""The SSE endpoint: framing, rejection shapes, and slot accounting."""

import json

import anyio
import pytest
from starlette.requests import Request

from api import config, main, schemas


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")


def scripted(events, *, hold: float = 0.0):
    """Replace the agent with a fixed event sequence."""

    async def _stream(messages):
        for event in events:
            if hold:
                await anyio.sleep(hold)
            yield event

    return _stream


def parse(body: str) -> list[dict]:
    return [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


async def test_chat_streams_sse_frames(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "stream_ask",
        scripted(
            [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": " there"},
                {"type": "done", "stop_reason": "end_turn"},
            ]
        ),
    )

    resp = await client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert [e["type"] for e in parse(resp.text)] == ["text", "text", "done"]


async def test_tool_events_survive_the_wire_intact(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "stream_ask",
        scripted(
            [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "query_census",
                    "input": {"category": "dwelling_structure", "subcategory": "separate house"},
                },
                {"type": "done", "stop_reason": "end_turn"},
            ]
        ),
    )

    resp = await client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )

    tool_event = parse(resp.text)[0]
    # The chip drives the explorer straight from this payload, so the structured
    # input has to arrive unflattened.
    assert tool_event["input"]["category"] == "dwelling_structure"


async def test_full_history_is_forwarded_to_the_agent(client, monkeypatch):
    seen = {}

    async def _stream(messages):
        seen["messages"] = messages
        yield {"type": "done", "stop_reason": "end_turn"}

    monkeypatch.setattr(main, "stream_ask", _stream)

    await client.post(
        "/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "How many separate houses in 2021?"},
                {"role": "assistant", "content": "40,100."},
                {"role": "user", "content": "And 2016?"},
            ]
        },
    )

    assert len(seen["messages"]) == 3
    assert seen["messages"][-1]["content"] == "And 2016?"


async def test_empty_message_list_is_rejected(client):
    resp = await client.post("/api/chat", json={"messages": []})
    assert resp.status_code == 422


async def test_missing_api_key_is_503(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    resp = await client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code == 503
    assert resp.json()["kind"] == "unavailable"


async def test_rate_limit_is_a_429_before_the_stream_opens(client, monkeypatch):
    monkeypatch.setattr(config, "CHAT_PER_MINUTE", 2)
    monkeypatch.setattr(
        main, "stream_ask", scripted([{"type": "done", "stop_reason": "end_turn"}])
    )
    body = {"messages": [{"role": "user", "content": "hi"}]}

    for _ in range(2):
        assert (await client.post("/api/chat", json=body)).status_code == 200

    resp = await client.post("/api/chat", json=body)
    # Not an error event on a 200 stream — the client needs a status code it can
    # branch on before it starts rendering a message.
    assert resp.status_code == 429
    assert resp.json()["kind"] == "rate"
    assert resp.headers["Retry-After"]


async def test_capacity_rejection_is_distinguishable_from_rate(client, monkeypatch, fresh_limiter):
    monkeypatch.setattr(config, "GLOBAL_INFLIGHT", 0)
    monkeypatch.setattr(
        main, "stream_ask", scripted([{"type": "done", "stop_reason": "end_turn"}])
    )

    resp = await client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )

    # Different copy in the UI: this one is not the caller's fault.
    assert resp.status_code == 429
    assert resp.json()["kind"] == "capacity"


async def test_slot_is_freed_after_a_completed_stream(client, monkeypatch, fresh_limiter):
    monkeypatch.setattr(
        main, "stream_ask", scripted([{"type": "done", "stop_reason": "end_turn"}])
    )

    await client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert fresh_limiter.snapshot()["inflight"] == 0
    assert fresh_limiter.snapshot()["active_ips"] == 0


async def test_slot_is_held_for_the_duration_and_freed_when_abandoned(
    census_db, monkeypatch, fresh_limiter
):
    """The client-disconnect path: the slot is held mid-stream, then released.

    This drives the endpoint directly rather than going through the test
    client. httpx's ASGITransport runs the app to completion even when the
    caller stops reading, so a `client.stream(...)` test cannot express
    "the client went away" — it would just be the happy path under another
    name. Closing the response's body iterator is what Starlette does on a real
    disconnect, so that is what is exercised here.
    """
    monkeypatch.setattr(
        main,
        "stream_ask",
        scripted([{"type": "text", "text": f"chunk {i}"} for i in range(50)]),
    )

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "headers": [],
            "client": ("1.2.3.4", 5555),
        }
    )
    response = await main.chat(
        request, schemas.ChatRequest(messages=[{"role": "user", "content": "hi"}])
    )

    body = response.body_iterator
    await body.__anext__()
    # Held while streaming — otherwise the concurrency cap would be decorative.
    assert fresh_limiter.snapshot()["inflight"] == 1

    await body.aclose()

    assert fresh_limiter.snapshot()["inflight"] == 0
    assert fresh_limiter.snapshot()["active_ips"] == 0


async def test_agent_crash_becomes_an_in_band_error_event(client, monkeypatch):
    async def _stream(messages):
        yield {"type": "text", "text": "partial"}
        raise RuntimeError("exploded after the response started")

    monkeypatch.setattr(main, "stream_ask", _stream)

    resp = await client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )

    # Status was already sent as 200, so the only channel left is the stream.
    assert resp.status_code == 200
    events = parse(resp.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["retryable"] is True
