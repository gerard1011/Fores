"""Environment-driven settings.

Everything here has a working default so `make up` needs nothing but a
`.env` with ANTHROPIC_API_KEY. The rate-limit values are the ones agreed
for a single container exposed directly; see limits.py for why they are
shaped the way they are.
"""

import os
from pathlib import Path


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


# --- Data -----------------------------------------------------------------
# Relative paths resolve against the repo root rather than the process CWD,
# so `uvicorn api.main:app` works from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CENSUS_DB_PATH", REPO_ROOT / "data" / "census.db"))

# The geography level shown on first load and used as the default for the
# category/subcategory endpoints when no `level` is supplied. LGA is the richer
# granularity (565 areas vs 9 states) and keeps continuity with the app's
# single-LGA (Boroondara) heritage.
DEFAULT_LEVEL = os.environ.get("CENSUS_DEFAULT_LEVEL", "LGA")

# Max areas comparable in one /series (or db.category_series) request. Bounds
# the SQL IN() size and the chart legend's legibility.
MAX_GEO_CODES = _int("CENSUS_MAX_GEO_CODES", 12)

# The agent's own ceiling on areas per query_census call — kept separate from
# MAX_GEO_CODES on purpose: this one is about output tokens per turn (each area
# multiplies the tool-result payload and the prose), not query size, so it can
# be tightened independently if a wide comparison starts hitting max_tokens.
AGENT_MAX_GEO_CODES = _int("CENSUS_AGENT_MAX_GEO_CODES", 12)

# --- Frontend -------------------------------------------------------------
# The built React bundle. Present in the image; absent when running uvicorn
# directly in dev, where Vite serves the UI instead.
WEB_DIST = Path(os.environ.get("WEB_DIST", REPO_ROOT / "web" / "dist"))

# --- Model ----------------------------------------------------------------
# Deliberately pinned. Sonnet 4.5's prompt-cache minimum is 1024 tokens; the
# schema summary we cache in agent.py is ~1600. On Opus 4.8 (4096-token
# minimum) the same block would silently fail to cache, so changing this is a
# real migration, not a string swap.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# A ceiling, not a target — output is billed per token actually generated, so
# headroom is free. It has to cover the tool_use blocks as well as the prose:
# asking about a 15-bracket category makes the model emit 15 query_census calls
# in one turn, and at the previous value of 1024 it ran out mid-generation,
# returning stop_reason "max_tokens" with zero usable tool calls. Since
# responses stream, a large value carries no timeout risk either.
MAX_TOKENS = _int("ANTHROPIC_MAX_TOKENS", 8192)

# --- Rate limits ----------------------------------------------------------
CHAT_PER_MINUTE = _int("CHAT_PER_MINUTE", 10)
CHAT_PER_HOUR = _int("CHAT_PER_HOUR", 100)
CHAT_STREAMS_PER_IP = _int("CHAT_STREAMS_PER_IP", 2)
# The one that actually bounds the Anthropic bill: with no auth, per-IP limits
# are defeated by rotating IPs, this is not.
GLOBAL_INFLIGHT = _int("GLOBAL_INFLIGHT", 8)
CENSUS_PER_MINUTE = _int("CENSUS_PER_MINUTE", 120)

# --- CORS -----------------------------------------------------------------
# Only needed in dev, where Vite serves the UI on another port. In production
# FastAPI serves the built bundle from its own origin, so this stays empty.
CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
