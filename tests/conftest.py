"""Shared fixtures.

Tests run against a small purpose-built database rather than the real one:
the real file is gitignored, so anything depending on it would pass on this
machine and fail in CI.
"""

import sqlite3
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from api import config, db, limits

ROWS = [
    ("Boroondara", 2011, "population", "total", 159182),
    ("Boroondara", 2016, "population", "total", 167232),
    ("Boroondara", 2021, "population", "total", 167900),
    ("Boroondara", 2011, "dwelling_structure", "separate house", 39000),
    ("Boroondara", 2016, "dwelling_structure", "separate house", 39500),
    ("Boroondara", 2021, "dwelling_structure", "separate house", 40100),
    ("Boroondara", 2011, "dwelling_structure", "flat or apartment", 11000),
    ("Boroondara", 2016, "dwelling_structure", "flat or apartment", 12500),
    ("Boroondara", 2021, "dwelling_structure", "flat or apartment", 14200),
]


@pytest.fixture
def census_db(tmp_path, monkeypatch):
    path = tmp_path / "census.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE census_data ("
        "lga TEXT, year INTEGER, category TEXT, subcategory TEXT, value INTEGER)"
    )
    conn.executemany("INSERT INTO census_data VALUES (?, ?, ?, ?, ?)", ROWS)
    conn.commit()
    conn.close()

    monkeypatch.setattr(config, "DB_PATH", path)
    db._schema_cache.clear()
    yield path
    db._schema_cache.clear()


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    """A clean limiter per test — the real one is a process-wide singleton."""
    fresh = limits.Limiter()
    monkeypatch.setattr(limits, "limiter", fresh)
    # main.py imported the name directly, so it needs rebinding too.
    from api import main

    monkeypatch.setattr(main, "limiter", fresh)
    return fresh


@pytest.fixture
async def client(census_db):
    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Anthropic stand-in ---------------------------------------------------
# The SDK's stream() is a sync call returning an async context manager that is
# also an async iterable and exposes get_final_message(). This mirrors that
# shape closely enough that agent.stream_ask cannot tell the difference.


def text_delta(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=text)
    )


def tool_use_block(block_id: str, name: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=payload)


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


class FakeStream:
    def __init__(self, events, final):
        self._events = events
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):
        for event in self._events:
            yield event

    async def get_final_message(self):
        return self._final


class FakeAnthropic:
    """Replays a scripted list of turns, one per stream() call."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        if not self._turns:
            raise AssertionError("agent requested more turns than the test scripted")
        events, final = self._turns.pop(0)
        return FakeStream(events, final)


def usage(*, input_tokens=10, cache_write=0, cache_read=1600, output_tokens=20):
    return SimpleNamespace(
        input_tokens=input_tokens,
        cache_creation_input_tokens=cache_write,
        cache_read_input_tokens=cache_read,
        output_tokens=output_tokens,
    )


def turn(*, text="", stop_reason="end_turn", content=None):
    """One scripted model turn: streamed deltas plus the final message.

    Carries a `usage` object because the real response does — the agent reads it
    to log cache behaviour, and a double that omits it would pass tests while
    production raised AttributeError.
    """
    events = [text_delta(chunk) for chunk in ([text] if text else [])]
    final = SimpleNamespace(
        stop_reason=stop_reason,
        content=content if content is not None else [text_block(text)],
        usage=usage(),
    )
    return events, final
