.PHONY: dev db migrate revision seed test lint api tts

# Everything in Docker, with migrations and seed applied on api start.
dev:
	docker compose up --build

# Local development: only Postgres in Docker, API and bot run from ./backend with uv.
db:
	docker compose up -d db

migrate:
	cd backend && uv run alembic upgrade head

# Usage: make revision m="add something"
revision:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

seed:
	cd backend && uv run python -m app.seed

api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app bot

# Temporary TTS audio for words that have no recording yet (existing files are kept).
tts:
	uv run --no-project --with edge-tts --with pyyaml python scripts/gen_tts.py
