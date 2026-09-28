# Build context is the repository root (see docker-compose.yml). The image carries the
# media (audio, pictures) so a server needs no checkout of the repository.
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ .
RUN pnpm build

# The parents' landing page (/about/) is the guide rendered by scripts/build_site.py.
FROM python:3.12-alpine AS site
RUN pip install --no-cache-dir markdown
WORKDIR /app
COPY scripts/build_site.py scripts/
COPY site/template.html site/
COPY docs/general/parent-guide.md docs/general/
COPY docs/general/parent-guide/ docs/general/parent-guide/
RUN python scripts/build_site.py

FROM caddy:2
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY media/ /srv/media/
COPY --from=build /app/dist /srv/web
COPY --from=site /app/_site /srv/about
