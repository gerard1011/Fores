# Fores
Application that utilises agentic capabilites that provides companies with accurate and on demand knowledge about their internal systems

## Census Data Pipeline

Extracts ABS Census Time Series data (2011/2016/2021) for Boroondara LGA
from raw Excel spreadsheets into a structured SQLite database.

### What it does
Parses 30+ ABS census tables (population, age, dwellings, income, etc.)
 Handles ABS's non-standard Excel layout (merged cells, multi-year 
  column blocks)
Loads into a normalized `census_data` table: (lga, year, category, 
  subcategory, value)
Idempotent safe to re-run without duplicating data

### Data source
Australian Bureau of Statistics, 2021 Census Time Series Profile

## Layout

```
api/       FastAPI service — the agent and the census endpoints
web/       React frontend (added in a later commit)
pipeline/  offline ETL from the ABS spreadsheets into SQLite
data/      the SQLite database — gitignored, bind-mounted into the container
```

## Prerequisites

Two things are not in the repo and must be present before the app will work:

1. **`.env`** in the project root with `ANTHROPIC_API_KEY` set.
2. **`data/boroondara_census.db`.** The database is gitignored and is *not*
   built into the image — it is bind-mounted read-only from `./data`, so
   refreshing it needs no rebuild. Note that `pipeline/boroondara.py` cannot
   currently regenerate it: its input spreadsheet and output paths are
   hardcoded to an absolute path on another machine. Until that is
   parameterised, you need an existing copy of the `.db` file.

Without the key, the census endpoints still work and `/api/chat` returns 503.
Without the database, both return 503 with an explanatory message rather than a
stack trace.

## Running the app

```
#first use
make build
#then
make up
#when finished
make down
```

- API: http://localhost:8000 (`/api/health` for a status summary)
- Streamlit UI: http://localhost:8501 — being replaced by `web/`, removed once
  the React frontend lands

Other commands: `make logs`, `make restart`, `make test`, `make freeze`
(regenerate `requirements.txt` from the built image).

## Tests

```
py -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-dev.txt
make test
```

Tests build their own small database, so they do not depend on the gitignored
one being present.

## Rate limits

`/api/chat` costs money per call and there is no auth, so three separate guards
apply. All are configurable by environment variable — see `api/config.py`.

| Guard | Default | Stops |
|---|---|---|
| Per-IP request rate | 10/min, 100/hr | One source hammering the endpoint |
| Per-IP concurrent streams | 2 | Held-open SSE connections, which a rate limit alone does not catch |
| Global in-flight agent calls | 8 | The actual spend ceiling — holds even against rotated IPs |
| Per-IP rate on census endpoints | 120/min | Backstop only; these just read SQLite |

`X-Forwarded-For` is deliberately ignored, because nothing sits in front of the
service and an untrusted header would make the limits opt-out. If a proxy or a
second replica is ever introduced, that and the in-memory counters must change
together.
