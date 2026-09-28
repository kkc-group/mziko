.PHONY: dev db migrate revision seed test lint api bot admin web code token tts twemoji images

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

bot:
	cd backend && uv run python -m bot.main

# Back office at http://localhost:8080/admin/ (set PUBLIC_URL=http://localhost:8080 for Google's redirect).
admin:
	cd admin && uv run uvicorn app.main:app --reload --port 8080

web:
	cd frontend && pnpm dev

# Local testing without Telegram (dev parent + child "Сандро" are created on first use).
code:            # the child's login code and link, as the bot would show
	cd backend && uv run python dev_login.py
token:           # shared link that logs in any browser
	cd backend && uv run python dev_login.py token

test:
	cd backend && uv run pytest
	cd admin && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app bot
	cd admin && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd frontend && pnpm lint && pnpm typecheck

# Temporary TTS audio for words that have no recording yet (existing files are kept).
tts:
	uv run --no-project --with edge-tts --with pyyaml python scripts/gen_tts.py

twemoji:
	uv run --no-project --with pyyaml python scripts/fetch_twemoji.py

# Word pictures dropped into media/images/: crop to the object, square, shrink to 384 px.
images:
	uv run --no-project --with pillow python scripts/prep_images.py
