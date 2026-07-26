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
DB_PATH = Path(os.environ.get("CENSUS_DB_PATH", REPO_ROOT / "data" / "boroondara_census.db"))

# --- Model ----------------------------------------------------------------
# Deliberately pinned. Sonnet 4.5's prompt-cache minimum is 1024 tokens; the
# schema summary we cache below is ~1600. On Opus 4.8 (4096-token minimum) the
# same block would silently fail to cache, so changing this is a real
# migration, not a string swap.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
MAX_TOKENS = _int("ANTHROPIC_MAX_TOKENS", 1024)

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
