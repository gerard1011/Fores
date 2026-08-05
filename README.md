# Fores
Application that utilises agentic capabilites that provides companies with accurate and on demand knowledge about their internal systems

## Census Data Pipeline

Extracts ABS Census Time Series data (2011/2016/2021) for multiple Australian LGAs and states, 
tracked via Git LFS.LGA from raw Excel spreadsheets into a structured SQLite database.

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
web/       React frontend — Vite, TypeScript, Tailwind, Recharts
pipeline/  offline ETL from the ABS spreadsheets into SQLite
data/      the SQLite database — gitignored, bind-mounted into the container
```

The UI is two linked panes. Ask a question on the left and the answer streams in
with its tool calls shown as expandable steps; click one and the explorer on the
right jumps to that category with the cited subcategory highlighted, so an
answer and the data behind it are on screen together.

## Prerequisites

One thing is not in the repo and must be present before the app will work:

1. **`.env`** in the project root with `ANTHROPIC_API_KEY` set.

The census database (`data/census.db`) **is** in the repo, tracked via
[Git LFS](https://git-lfs.com), so install `git-lfs` once
(`git lfs install`) before cloning. `make build` runs `git lfs pull` for you,
so the normal first-run flow materialises the real file; if git-lfs is missing
it stops with instructions rather than building against a pointer. Docker can't
do this step — the image never clones the repo (`data/` is bind-mounted from
the host), so the file must exist host-side first. It is bind-mounted read-only
into the container from `./data`, so refreshing the data needs no image rebuild.

Regenerating it from source is not yet automated: `pipeline/boroondara.py` has
its input spreadsheet and output paths hardcoded to an absolute path on another
machine. Until that is parameterised, treat the committed `.db` as the source
of truth and refresh it by replacing the file (which updates the LFS object).

**Any regenerated database must carry this index on `census_data`:**

```sql
CREATE INDEX ix_levels ON census_data(level, year, geo_code);
```

Without it, `/api/datasets/census/levels` does full-table `GROUP BY` and
`COUNT(DISTINCT geo_code)` scans. Those are cheap on a local disk but take
~60s over the read-only bind mount on Docker Desktop (random I/O on an ~87 MB
file), and that endpoint is hit on every page load. The index makes both
queries index-only. `api.db.list_levels` also memoizes its result on the
file's mtime, which covers repeat loads, but the *first* load after any data
refresh or container restart still needs the index to be fast. The committed
database already has it.

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

Then open http://localhost:8000. One container serves both the UI and the API
on one port — the image's first stage builds the React bundle and FastAPI serves
it, so there is no CORS to configure and no second runtime to deploy.
`/api/health` gives a status summary including live rate-limit counters.

Other commands: `make logs`, `make restart`, `make test`, `make types`.

`requirements.txt` is a curated list of direct dependencies. It used to be a
full `pip freeze`, most of which existed to support Streamlit; there is no
longer a `make freeze` target, since freezing would put every transitive back.
The pipeline's own dependencies are in `requirements-pipeline.txt` and are
deliberately not installed into the runtime image.

## Frontend development

The React app lives in `web/`. In dev it runs on its own server and proxies
`/api` to FastAPI, so the app talks to the same paths in dev and production and
there is no CORS config or base URL to manage.

```
.venv/Scripts/python -m uvicorn api.main:app --port 8000
npm --prefix web run dev
```

Then open http://localhost:5173.

`make types` regenerates `web/src/api/schema.d.ts` from FastAPI's OpenAPI
schema. Run it after changing any Pydantic model — a renamed field then breaks
the frontend build instead of production. Note the SSE event shapes are the one
thing generation cannot cover: they are declared in `web/src/api/events.ts` and
mirror the docstring on `agent.stream_ask` by hand.

TypeScript is pinned to 5.x deliberately. TypeScript 7 (the native compiler)
does not expose the `ts.factory` API that `openapi-typescript` builds on, so
type generation breaks on it.

## Tests

```
py -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-dev.txt
make test              # backend
npm --prefix web test  # frontend
```

Backend tests build their own small database, so they do not depend on the
gitignored one being present.

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

## Observability

The agent logs token usage per model call at INFO:

```
api.agent: tokens: input=332 cache_write=0 cache_read=2413 output=72
```

`cache_read` is the one to watch. The system prompt inlines every category and
subcategory, so the cached prefix is ~2,400 tokens; if `cache_read` drops to 0
the prompt cache has stopped working and each turn is paying full price for all
of it, with no error raised. The usual cause is something making the prefix vary
between requests, or a model change — cache minimums are model-specific, and the
note on `config.MODEL` explains why the model is pinned.

Set `LOG_LEVEL=WARNING` to quieten it.

A turn that ends before it finished logs a warning:

```
api.agent: turn ended early: stop_reason=max_tokens
```

`max_tokens` means the answer was cut off mid-generation and the user was told
so. The budget (`ANTHROPIC_MAX_TOKENS`, default 8192) has to cover the tool calls
as well as the prose — asking about a 15-bracket category makes the model emit 15
`query_census` calls in a single turn. If this starts appearing regularly, raise
it rather than assuming the model is being verbose.
