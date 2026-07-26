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
# Wired up in the commit that adds web/.
types:
	@echo "Not yet — added with the React app."
