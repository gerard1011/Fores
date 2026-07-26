# Backend (FastAPI)

A thin FastAPI wrapper around the existing agent logic in `app/agent.py`.
It does not reimplement any agent behavior — `POST /chat` calls `ask()`
and `GET /lookup` calls `query_census()` directly from `app/agent.py`.

## Endpoints

- `POST /chat` — body `{"question": "..."}`, returns `{"answer": "..."}`
- `GET /categories` — list of distinct categories
- `GET /subcategories?category=X` — list of distinct subcategories for `X`
- `GET /lookup?category=X&subcategory=Y` — list of `{"year", "value"}` pairs

## Setup

From the **project root** (not from inside `backend/`):

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

Make sure a `.env` file with `ANTHROPIC_API_KEY` exists in the project root
(same one used by the Streamlit app).

## Run

```bash
backend/.venv/bin/uvicorn backend.main:app --reload --port 8000
```

Run this from the project root. `backend/main.py` `chdir`s to the project
root on import anyway (see note below), so it will also work if invoked
from elsewhere as long as the venv path is correct — but running from the
root is the simplest and matches how the Streamlit app is normally started.

Visit http://localhost:8000/docs for interactive API docs.

## Note on `app/agent.py`

`agent.py` opens the database with a relative path,
`"data/boroondara_census.db"`, which only resolves if the process's current
working directory is the project root — the same assumption the existing
Streamlit app relies on (`streamlit run app/app.py` from the repo root, per
the Dockerfile). Rather than editing `agent.py`, `backend/main.py` calls
`os.chdir()` to the project root before importing it, so the API works
regardless of where `uvicorn` is launched from. Flagging this here per your
request rather than silently changing `agent.py`.
