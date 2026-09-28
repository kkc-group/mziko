# Сборка на GitHub и деплой на Digital Ocean

Документ отвечает на «как устроено» тому, кто код не писал.

## Что изменилось

Раньше сервер был копией репозитория: `git clone`, `docker compose up --build`,
и картинки, звук и слова читались с диска сервера. Теперь сервер не знает про
git. Образы собираются на GitHub из исходников при каждом пуше в `main`,
кладутся в GitHub Container Registry и запускаются на Droplet готовыми. На
сервере лежат два файла: `docker-compose.yml` и `.env`.

## Как это работает

- **Образы самодостаточны.** `mziko-api` несёт контент (`content/` →
  `/srv/content`, seed читает оттуда), `mziko-web` — собранный фронт и медиа
  (`media/` → `/srv/media`, аудио и картинки Twemoji). Оба собираются из корня
  репозитория, `.dockerignore` держит контекст маленьким. Локальный `make dev`
  поверх образов подмонтирует `content` и `media` с диска, чтобы правки слов и
  звука применялись без пересборки.
- **Workflow** `.github/workflows/deploy.yml`, три шага по пушу в `main` (или
  вручную кнопкой «Run workflow»):
  1. `test` — `ruff`, `mypy`, `pytest` бэкенда (Postgres в testcontainers) и
     бэк-офиса, линт, типы и сборка фронта. Красное — дальше не идёт.
  2. `build` — три образа через buildx с кэшем GitHub, теги `<sha>` и `latest`,
     в `ghcr.io/kkc-group/mziko-api`, `mziko-admin` и `mziko-web`. Логин
     встроенным `GITHUB_TOKEN`.
  3. `deploy` — по SSH на Droplet: копирует `deploy/docker-compose.prod.yml` в
     `/srv/mziko/docker-compose.yml`, логинится в ghcr тем же токеном, `docker
     compose pull` и `up -d` с `IMAGE_TAG=<sha>`, чистит старые образы.
     Миграции и seed по-прежнему выполняет контейнер `api` при старте.
- **Секреты GitHub** (Settings → Secrets → Actions): `DO_HOST` — IP Droplet,
  `DO_USER` — пользователь SSH, `DO_SSH_KEY` — приватный ключ деплоя, чей
  публичный ключ лежит в `authorized_keys` на сервере. Секреты приложения в
  GitHub не попадают: `.env` живёт только на сервере.
- **Откат**: на сервере `IMAGE_TAG=<старый sha> docker compose up -d`. Теги
  по sha остаются в ghcr.

## Сервер

Один раз, руками (см. README, «Деплой»): Ubuntu 24.04 с Docker, каталог
`/srv/mziko` с `.env` по образцу `.env.example`, публичный ключ деплоя в
`authorized_keys`, открытые порты 22, 80, 443. Резервные копии — снимки
Droplet в панели DO плюс `pg_dump` по README.

## За бортом

- Отдельные окружения (staging): один Droplet, один `main`.
- Уведомление о результате деплоя в Telegram.
