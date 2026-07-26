# Frontend (React + TypeScript + Tailwind)

Replicates the Streamlit app's UI: a chat interface backed by the Claude
agent, and a manual category/subcategory lookup to verify the agent's
answers against the raw data.

Talks to the FastAPI backend at `http://localhost:8000` by default. Override
with a `VITE_API_URL` env var (e.g. in a `.env.local` file) if needed.

## Setup

```bash
cd frontend
npm install
```

## Run

```bash
npm run dev
```

Opens at http://localhost:5173. The backend (see `../backend/README.md`)
must be running on port 8000 — its CORS config already allows
`http://localhost:5173`.

## Build

```bash
npm run build
```
