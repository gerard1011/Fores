.PHONY: build up down restart logs clean test types lfs

# The census database ships through Git LFS, and Docker can't fetch it for you:
# the image never clones the repo — data/ is bind-mounted from the host — so the
# real file has to exist host-side before the container starts. `build` depends
# on this so a fresh clone gets it as part of the documented first-run flow.
# Kept to two plain commands so the recipe runs under both cmd.exe and sh; if
# git-lfs is missing, `git lfs` itself errors clearly and make stops. The
# runtime guard in api/db.py catches an un-pulled pointer with a fuller message.
lfs:
	git lfs install --local
	git lfs pull

build: lfs
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart: down up

logs:
	docker compose logs -f

# `freeze` is gone: requirements.txt is now a curated list of direct
# dependencies, and pip freeze would blow it back up with every transitive.

clean:
	docker compose down --rmi local

test:
	.venv/Scripts/python -m pytest -q

# Regenerates web/src/api/schema.d.ts from FastAPI's OpenAPI schema, so a
# renamed Pydantic field breaks the frontend build instead of production.
# Generated from the app object directly — no server needs to be running.
types:
	.venv/Scripts/python -c "import json; from api.main import app; print(json.dumps(app.openapi()))" > web/openapi.json
	cd web && npx --yes openapi-typescript openapi.json -o src/api/schema.d.ts
	rm -f web/openapi.json
