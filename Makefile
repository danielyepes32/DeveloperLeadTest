.PHONY: help install lint test run up dev down logs lock

help:
	@echo "install  - sync dependencies into .venv (uv)"
	@echo "lock     - regenerate uv.lock"
	@echo "lint     - run ruff"
	@echo "test     - run pytest (SQLite, no external services)"
	@echo "run      - run the API locally with autoreload"
	@echo "up       - build & start the prod-like stack (API + Postgres)"
	@echo "dev      - start the stack with live reload (no rebuild on code changes)"
	@echo "down     - stop the stack and remove volumes"

install:
	uv sync

lock:
	uv lock

lint:
	uv run ruff check .

test:
	uv run pytest

run:
	uv run uvicorn app.main:app --reload

up:
	docker compose up --build

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api
