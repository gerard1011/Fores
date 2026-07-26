.PHONY: build up down restart logs freeze clean

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
	docker compose run --rm app pip freeze > requirements.txt

clean:
	docker compose down --rmi local
