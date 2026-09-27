# Build context is the repository root (see docker-compose.yml): the image carries the
# word content, so a server needs no checkout of the repository.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 CONTENT_DIR=/srv/content

WORKDIR /srv/backend

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ .
COPY content/ /srv/content/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
