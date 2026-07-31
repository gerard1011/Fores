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

YEARS = (2011, 2016, 2021)


def _boroondara_name(year: int) -> str:
    # The name drift that makes geo_code, not geo_name, the cross-year key:
    # 'Boroondara (C)' in the earlier censuses, 'Boroondara' in 2021.
    return "Boroondara (C)" if year < 2021 else "Boroondara"


def _rows() -> list[tuple]:
    """A small multi-geography database exercising every path the app cares
    about: two LGAs to compare, a same-name LGA pair in different states (to
    lock the collision → state-append naming), three STEs, the Boroondara name
    drift, and one area (Campbelltown NSW) that lacks dwelling_structure so the
    empty-series case is reachable.

    Columns: level, geo_code, geo_name, year, category, subcategory, value.
    """
    rows: list[tuple] = []

    def add(level, geo_code, name, cat, sub, per_year):
        for year, value in zip(YEARS, per_year):
            nm = name(year) if callable(name) else name
            rows.append((level, geo_code, nm, year, cat, sub, value))

    # LGA Boroondara (Victoria) — drifting name, full category coverage.
    add("LGA", "LGA21110", _boroondara_name, "population", "total", (159182, 167232, 167900))
    add("LGA", "LGA21110", _boroondara_name, "dwelling_structure", "separate house", (39000, 39500, 40100))
    add("LGA", "LGA21110", _boroondara_name, "dwelling_structure", "flat or apartment", (11000, 12500, 14200))

    # LGA Stonnington (Victoria) — a second area to compare against.
    add("LGA", "LGA22910", "Stonnington (C)", "population", "total", (103000, 110000, 116000))
    add("LGA", "LGA22910", "Stonnington (C)", "dwelling_structure", "separate house", (20000, 20500, 21000))
    add("LGA", "LGA22910", "Stonnington (C)", "dwelling_structure", "flat or apartment", (30000, 32000, 34000))

    # Same display name, two states → must disambiguate by appending the state.
    add("LGA", "LGA11500", "Campbelltown (C)", "population", "total", (150000, 158000, 175000))
    add("LGA", "LGA40910", "Campbelltown (C)", "population", "total", (50000, 52000, 54000))

    # STEs. South Australia is present so the digit-4 Campbelltown resolves its
    # state name; NSW and Victoria carry full data for STE comparison paths.
    add("STE", "1", "New South Wales", "population", "total", (6917657, 7480228, 8072163))
    add("STE", "1", "New South Wales", "dwelling_structure", "separate house", (1000000, 1050000, 1100000))
    add("STE", "1", "New South Wales", "dwelling_structure", "flat or apartment", (500000, 550000, 600000))
    add("STE", "2", "Victoria", "population", "total", (5354043, 5926624, 6503491))
    add("STE", "2", "Victoria", "dwelling_structure", "separate house", (900000, 950000, 1000000))
    add("STE", "2", "Victoria", "dwelling_structure", "flat or apartment", (400000, 450000, 500000))
    add("STE", "4", "South Australia", "population", "total", (1600000, 1670000, 1780000))

    return rows


ROWS = _rows()


@pytest.fixture
def census_db(tmp_path, monkeypatch):
    path = tmp_path / "census.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE census_data ("
        "level TEXT, geo_code TEXT, geo_name TEXT, year INTEGER, "
        "category TEXT, subcategory TEXT, value INTEGER)"
    )
    conn.executemany("INSERT INTO census_data VALUES (?, ?, ?, ?, ?, ?, ?)", ROWS)
    conn.commit()
    conn.close()

    monkeypatch.setattr(config, "DB_PATH", path)
    db._schema_cache.clear()
    db._canonical_cache.clear()
    yield path
    db._schema_cache.clear()
    db._canonical_cache.clear()


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
