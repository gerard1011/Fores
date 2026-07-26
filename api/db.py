"""Read-only access to the census database.

Connections are opened per query rather than pooled: the database is a
~72KB file, queries are sub-millisecond, and per-query connections avoid
SQLite's cross-thread restrictions entirely. Revisit if the data grows by
orders of magnitude.
"""

import sqlite3
from pathlib import Path

from . import config


class DatabaseMissing(RuntimeError):
    """Raised when the census database is not where we expect it."""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    if not path.exists():
        raise DatabaseMissing(
            f"Census database not found at {path}.\n"
            "The database is gitignored and bind-mounted from ./data, so it is not "
            "created by the build. Place boroondara_census.db there, or point "
            "CENSUS_DB_PATH at an existing copy.\n"
            "Note: pipeline/boroondara.py cannot regenerate it as-is — its input and "
            "output paths are hardcoded to another machine."
        )
    # mode=ro matches the read-only bind mount and makes an accidental write
    # fail loudly here rather than silently succeed against a stale copy.
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_categories(path: Path | None = None) -> list[dict]:
    """Every category with how many distinct subcategories it holds.

    The count drives the UI: `population` has one subcategory and is a single
    number, `country_of_birth` has 35 and is a real chart.
    """
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT category, COUNT(DISTINCT subcategory) AS subcategory_count "
            "FROM census_data GROUP BY category ORDER BY category"
        ).fetchall()
    return [dict(r) for r in rows]


def category_series(category: str, path: Path | None = None) -> list[dict]:
    """Every (subcategory, year, value) triple for one category."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT subcategory, year, value FROM census_data "
            "WHERE category = ? ORDER BY subcategory, year",
            (category,),
        ).fetchall()
    return [dict(r) for r in rows]


def query_census(category: str, subcategory: str, path: Path | None = None) -> list[tuple]:
    """Year/value pairs for one subcategory. Backs the agent's query_census tool."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT year, value FROM census_data "
            "WHERE category = ? AND subcategory = ? ORDER BY year",
            (category, subcategory),
        ).fetchall()
    return [(r["year"], r["value"]) for r in rows]


# --- Schema summary -------------------------------------------------------
# This string is ~6.4KB / ~1600 tokens and goes into the system prompt on every
# turn. Rebuilding it per call meant a SQLite round trip each time; sending it
# uncached meant paying for 1600 tokens per turn. It is memoized here and
# marked cache_control in agent.py.
#
# The cache key is the database's mtime, not a plain lru_cache: the file is
# bind-mounted, so it can change under a running process. Keying on mtime keeps
# the memo correct across a data refresh without needing a restart.
_schema_cache: dict[float, str] = {}


def schema_summary(path: Path | None = None) -> str:
    path = path or config.DB_PATH
    if not path.exists():
        raise DatabaseMissing(f"Census database not found at {path}.")
    mtime = path.stat().st_mtime

    cached = _schema_cache.get(mtime)
    if cached is not None:
        return cached

    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT category, subcategory FROM census_data "
            "ORDER BY category, subcategory"
        ).fetchall()

    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row["category"], []).append(row["subcategory"])
    summary = "\n".join(f"- {cat}: {', '.join(subs)}" for cat, subs in grouped.items())

    # A refreshed database makes every prior entry dead weight; there is only
    # ever one live version of this string.
    _schema_cache.clear()
    _schema_cache[mtime] = summary
    return summary
