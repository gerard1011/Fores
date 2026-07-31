"""Read-only access to the census database.

Connections are opened per query rather than pooled: the indexed lookups are
sub-millisecond even though the file is now ~88MB, and per-query connections
avoid SQLite's cross-thread restrictions entirely. Revisit if the query shape
changes to something that scans rather than seeks.

The data carries a geography dimension: every row is scoped to a `level`
('LGA' or 'STE') and a `geo_code`. The `geo_code` — not `geo_name` — is the
stable cross-year key: the ABS drifts display names across censuses (Boroondara
is 'Boroondara (C)' in 2011/2016 but 'Boroondara' in 2021 under the same
`geo_code` LGA21110). All selection and cross-year logic keys on `geo_code`;
`geo_name` is only ever a label, resolved to a single canonical form here.
"""

import re
import sqlite3
from pathlib import Path

from . import config

LEVELS = ("LGA", "STE")


class DatabaseMissing(RuntimeError):
    """Raised when the census database is not where we expect it."""


class BadRequest(ValueError):
    """Bad caller input (unknown level, too many areas). Endpoints turn this
    into a 4xx; the agent turns it into a tool error the model can recover
    from."""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    if not path.exists():
        raise DatabaseMissing(
            f"Census database not found at {path}.\n"
            "The database is gitignored and bind-mounted from ./data, so it is not "
            "created by the build. Place census.db there, or point CENSUS_DB_PATH "
            "at an existing copy."
        )
    # mode=ro matches the read-only bind mount and makes an accidental write
    # fail loudly here rather than silently succeed against a stale copy.
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _validate_level(level: str) -> None:
    if level not in LEVELS:
        raise BadRequest(f"Unknown level {level!r}; expected one of {', '.join(LEVELS)}.")


def _validate_geo_codes(geo_codes: list[str]) -> None:
    if not geo_codes:
        raise BadRequest("At least one geo_code is required.")
    if len(geo_codes) > config.MAX_GEO_CODES:
        raise BadRequest(
            f"Too many areas: {len(geo_codes)} (max {config.MAX_GEO_CODES})."
        )


# --- Canonical names ------------------------------------------------------
# geo_name drifts across years and is not unique even within one year: in 2011
# 'Campbelltown (C)' is both an LGA in NSW and one in SA. We resolve one stable,
# unique display name per geo_code for the *latest-year universe* (the areas the
# app offers — see list_geographies): take the latest year's name, strip the
# trailing ABS type suffix (' (C)'/' (S)'/…), and — where stripping collapses
# two areas onto the same name — append the state to keep the label unique.
#
# Memoized like the schema summary: the map is stable for a given database file,
# so it is keyed on the file's mtime (the file is bind-mounted and can change
# under a running process) and rebuilt only when the data is refreshed.
_TYPE_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")

_canonical_cache: dict[tuple[float, str], dict[str, str]] = {}


def _strip_suffix(name: str) -> str:
    return _TYPE_SUFFIX.sub("", name).strip()


def _state_names(conn: sqlite3.Connection) -> dict[str, str]:
    """geo_code digit → state name, read from the STE rows themselves.

    An LGA's `geo_code` is 'LGA' + five digits whose first digit is the state
    (LGA11500 → '1' → New South Wales), and that digit is exactly the STE
    `geo_code`. So the states table doubles as the digit→name lookup.
    """
    rows = conn.execute(
        "SELECT DISTINCT geo_code, geo_name FROM census_data WHERE level = 'STE'"
    ).fetchall()
    return {r["geo_code"]: r["geo_name"] for r in rows}


def _state_of(geo_code: str, states: dict[str, str]) -> str | None:
    if geo_code.startswith("LGA") and len(geo_code) >= 4:
        return states.get(geo_code[3])
    return states.get(geo_code)  # STE codes are the digit itself


def _build_canonical(conn: sqlite3.Connection, level: str) -> dict[str, str]:
    latest = conn.execute(
        "SELECT MAX(year) FROM census_data WHERE level = ?", (level,)
    ).fetchone()[0]
    if latest is None:
        return {}

    rows = conn.execute(
        "SELECT DISTINCT geo_code, geo_name FROM census_data WHERE level = ? AND year = ?",
        (level, latest),
    ).fetchall()
    raw = {r["geo_code"]: r["geo_name"] for r in rows}

    # Group by stripped name to find collisions.
    stripped = {gc: _strip_suffix(name) for gc, name in raw.items()}
    groups: dict[str, list[str]] = {}
    for gc, name in stripped.items():
        groups.setdefault(name, []).append(gc)

    states = _state_names(conn)
    canonical: dict[str, str] = {}
    for name, codes in groups.items():
        if len(codes) == 1:
            canonical[codes[0]] = name
            continue
        # Collision: append the state to disambiguate.
        appended = {gc: f"{name} ({_state_of(gc, states)})" for gc in codes}
        if len(set(appended.values())) == len(codes):
            canonical.update(appended)
        else:
            # Degenerate: two areas of the same name in the same state. Fall
            # back to the full ABS name, which carries the type suffix and is
            # the last thing that still distinguishes them.
            for gc in codes:
                canonical[gc] = raw[gc]
    return canonical


def _canonical_map(path: Path | None, level: str) -> dict[str, str]:
    path = path or config.DB_PATH
    if not path.exists():
        raise DatabaseMissing(f"Census database not found at {path}.")
    key = (path.stat().st_mtime, level)
    cached = _canonical_cache.get(key)
    if cached is not None:
        return cached
    with _connect(path) as conn:
        built = _build_canonical(conn, level)
    # Only ever one live database version; drop stale entries on refresh.
    for stale in [k for k in _canonical_cache if k[0] != key[0]]:
        del _canonical_cache[stale]
    _canonical_cache[key] = built
    return built


def _name_for(canonical: dict[str, str], geo_code: str) -> str:
    """Canonical label for a code, falling back to the code itself for an area
    outside the latest-year universe (the UI never offers such a code, but the
    agent could pass a stale one)."""
    return canonical.get(geo_code, geo_code)


# --- Geography ------------------------------------------------------------


# Memoized like the canonical map and schema summary: the levels and their
# area counts are stable for a given database file, so the result is keyed on
# the file's mtime and recomputed only when the data is refreshed. This matters
# because /levels is hit on every page load and its full-table GROUP BY /
# COUNT(DISTINCT) scans are slow over the read-only bind mount.
_levels_cache: dict[float, list[dict]] = {}


def list_levels(path: Path | None = None) -> list[dict]:
    """Every level with its area count.

    `area_count` is the number of areas in the *latest* year — the universe the
    app offers (see list_geographies). It is deliberately not the all-time
    distinct count, which is larger because the ABS creates, merges, and
    abolishes areas between censuses.
    """
    path = path or config.DB_PATH
    if not path.exists():
        raise DatabaseMissing(f"Census database not found at {path}.")
    mtime = path.stat().st_mtime
    cached = _levels_cache.get(mtime)
    if cached is not None:
        return cached
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT level, MAX(year) AS latest FROM census_data GROUP BY level"
        ).fetchall()
        levels = []
        for r in rows:
            count = conn.execute(
                "SELECT COUNT(DISTINCT geo_code) FROM census_data "
                "WHERE level = ? AND year = ?",
                (r["level"], r["latest"]),
            ).fetchone()[0]
            levels.append({"level": r["level"], "area_count": count})
    built = sorted(levels, key=lambda x: x["level"])
    # Only ever one live database version; drop stale entries on refresh.
    for stale in [k for k in _levels_cache if k != mtime]:
        del _levels_cache[stale]
    _levels_cache[mtime] = built
    return built


def resolve_geographies(level: str, geo_codes: list[str], path: Path | None = None) -> list[dict]:
    """Canonical `{geo_code, geo_name}` for each requested area, in the order
    given — so /series can echo the legend even for an area that turned out to
    have no rows."""
    _validate_level(level)
    canonical = _canonical_map(path, level)
    return [{"geo_code": gc, "geo_name": _name_for(canonical, gc)} for gc in geo_codes]


def find_geography(level: str, name_query: str, limit: int = 25, path: Path | None = None) -> list[dict]:
    """Areas at a level whose canonical name contains `name_query`
    (case-insensitive). Backs the agent's find_geography tool: it turns a user's
    area name into the `geo_code`(s) that query_census needs.

    Matching is over the canonical names — the same unique labels the picker
    shows — so a collision like Campbelltown comes back as two clearly
    distinguished candidates ('Campbelltown (New South Wales)' /
    '(South Australia)') for the model to choose between.
    """
    _validate_level(level)
    q = name_query.strip().lower()
    canonical = _canonical_map(path, level)
    matches = [
        {"geo_code": gc, "geo_name": name}
        for gc, name in canonical.items()
        if q in name.lower()
    ]
    matches.sort(key=lambda m: m["geo_name"].lower())
    return matches[:limit]


def category_exists(category: str, level: str, path: Path | None = None) -> bool:
    """Whether a category exists at a level at all.

    Lets /series separate an unknown category (404) from a known category that
    simply has no rows for the requested areas (200 with empty points)."""
    _validate_level(level)
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT 1 FROM census_data WHERE category = ? AND level = ? LIMIT 1",
            (category, level),
        ).fetchone()
    return row is not None


def list_geographies(level: str, path: Path | None = None) -> list[dict]:
    """One row per selectable area at a level: `{geo_code, geo_name}` with the
    canonical name, sorted by name. Backs the area picker.

    The universe is the latest year's areas; areas abolished before then are not
    selectable (their historical rows still exist and are reachable by geo_code,
    they just don't appear in the picker).
    """
    _validate_level(level)
    canonical = _canonical_map(path, level)
    geos = [{"geo_code": gc, "geo_name": name} for gc, name in canonical.items()]
    return sorted(geos, key=lambda g: g["geo_name"].lower())


# --- Vocabulary -----------------------------------------------------------


def list_categories(level: str, path: Path | None = None) -> list[dict]:
    """Every category at a level with how many distinct subcategories it holds.

    The count drives the UI: `population` has one subcategory and is a single
    number, `country_of_birth` has 35 and is a real chart. The vocabulary is
    currently identical across levels, but the filter keeps the endpoint honest
    if that ever stops being true.
    """
    _validate_level(level)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT category, COUNT(DISTINCT subcategory) AS subcategory_count "
            "FROM census_data WHERE level = ? GROUP BY category ORDER BY category",
            (level,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_subcategories(level: str, path: Path | None = None) -> list[dict]:
    """Every (category, subcategory) pair at a level — the explorer's search
    index. Names only, no values."""
    _validate_level(level)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT category, subcategory FROM census_data "
            "WHERE level = ? ORDER BY category, subcategory",
            (level,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- Series ---------------------------------------------------------------


def category_series(category: str, level: str, geo_codes: list[str], path: Path | None = None) -> list[dict]:
    """Every (geo_code, geo_name, subcategory, year, value) point for one
    category across the requested areas — the comparison workhorse.

    Names are the canonical form; the underlying join is on geo_code so the
    '(C)' name drift across years never splits an area's line.
    """
    _validate_level(level)
    _validate_geo_codes(geo_codes)
    canonical = _canonical_map(path, level)
    placeholders = ",".join("?" for _ in geo_codes)
    with _connect(path) as conn:
        rows = conn.execute(
            f"SELECT geo_code, subcategory, year, value FROM census_data "
            f"WHERE category = ? AND level = ? AND geo_code IN ({placeholders}) "
            f"ORDER BY geo_code, subcategory, year",
            (category, level, *geo_codes),
        ).fetchall()
    return [
        {
            "geo_code": r["geo_code"],
            "geo_name": _name_for(canonical, r["geo_code"]),
            "subcategory": r["subcategory"],
            "year": r["year"],
            "value": r["value"],
        }
        for r in rows
    ]


def query_census(
    category: str, subcategory: str, level: str, geo_codes: list[str], path: Path | None = None
) -> dict:
    """Per-area year/value series for one subcategory. Backs the agent's
    query_census tool.

    Returns `{geo_code: {"name": canonical, "series": [(year, value), ...]}}`.
    A requested area with no matching rows (a gap subcategory, §1.4) comes back
    with an empty series rather than being dropped, so the caller can tell "no
    data" from "zero".
    """
    _validate_level(level)
    _validate_geo_codes(geo_codes)
    canonical = _canonical_map(path, level)
    placeholders = ",".join("?" for _ in geo_codes)
    with _connect(path) as conn:
        rows = conn.execute(
            f"SELECT geo_code, year, value FROM census_data "
            f"WHERE category = ? AND subcategory = ? AND level = ? "
            f"AND geo_code IN ({placeholders}) ORDER BY geo_code, year",
            (category, subcategory, level, *geo_codes),
        ).fetchall()
    out: dict[str, dict] = {
        gc: {"name": _name_for(canonical, gc), "series": []} for gc in geo_codes
    }
    for r in rows:
        out[r["geo_code"]]["series"].append((r["year"], r["value"]))
    return out


# --- Schema summary -------------------------------------------------------
# This string is ~6.4KB / ~1600 tokens and goes into the system prompt on every
# turn. Rebuilding it per call meant a SQLite round trip each time; sending it
# uncached meant paying for 1600 tokens per turn. It is memoized here and
# marked cache_control in agent.py.
#
# The cache key is (database mtime, level): the file is bind-mounted so it can
# change under a running process, and the summary is level-scoped. The
# vocabulary is currently identical across levels, so switching level does not
# actually change the string — but keying on level keeps that an implementation
# detail rather than an assumption.
_schema_cache: dict[tuple[float, str], str] = {}


def schema_summary(level: str, path: Path | None = None) -> str:
    _validate_level(level)
    path = path or config.DB_PATH
    if not path.exists():
        raise DatabaseMissing(f"Census database not found at {path}.")
    key = (path.stat().st_mtime, level)

    cached = _schema_cache.get(key)
    if cached is not None:
        return cached

    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT category, subcategory FROM census_data "
            "WHERE level = ? ORDER BY category, subcategory",
            (level,),
        ).fetchall()

    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row["category"], []).append(row["subcategory"])
    summary = "\n".join(f"- {cat}: {', '.join(subs)}" for cat, subs in grouped.items())

    # A refreshed database makes every prior entry dead weight; there is only
    # ever one live version of this string per level.
    for stale in [k for k in _schema_cache if k[0] != key[0]]:
        del _schema_cache[stale]
    _schema_cache[key] = summary
    return summary
