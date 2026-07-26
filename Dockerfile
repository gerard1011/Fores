# --- Stage 1: build the React bundle --------------------------------------
FROM node:24-slim AS web

WORKDIR /build

# Copied before the source so a source-only change reuses the install layer.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build


# --- Stage 2: runtime -------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY --from=web /build/dist ./web/dist

# Not copied, on purpose:
#   data/      gitignored and bind-mounted read-only, so `COPY data/` would
#              fail on a fresh clone and baking it in would make every data
#              refresh a rebuild. See docker-compose.yml.
#   pipeline/  an offline ETL that is not on the serving path; its pandas
#              stack is not installed here. See requirements-pipeline.txt.

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# One process serving both the API and the bundle, so there is no CORS to
# configure and no second runtime to deploy.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
