# Build context is the repository root (see docker-compose.yml). The image carries the
# media (audio, pictures) so a server needs no checkout of the repository.
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ .
RUN pnpm build

FROM caddy:2
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY media/ /srv/media/
COPY --from=build /app/dist /srv/web
