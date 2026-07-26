.PHONY: build up down restart logs freeze clean test types

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart: down up

logs:
	docker compose logs -f

freeze:
	docker compose run --rm api pip freeze > requirements.txt

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
