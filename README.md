# Мзико

Грузинские слова для детей: карточки с картинкой и звуком, монеты за правильные
ответы, раз в неделю монеты превращаются в лари, которые родитель выдаёт наличными.
Родитель управляет всем через Telegram-бот. Задание целиком: [TASK.md](TASK.md),
как это работает: [docs/features/mziko-mvp.md](docs/features/mziko-mvp.md).

Статическая проверочная страница «Цвета» без сервера: https://kkc-group.github.io/mziko/
(это `index.html` в корне, GitHub Pages отдаёт его из ветки `main`).

## Состав

| Папка | Что это |
|---|---|
| `backend/app` | FastAPI: модели, миграции Alembic, логика обучения и монет, HTTP-ручки |
| `backend/bot` | Telegram-бот на aiogram 3 с недельным планировщиком |
| `backend/tests` | pytest + testcontainers (нужен Docker) |
| `frontend` | React + TypeScript + Vite, PWA |
| `content/topics` | Слова по темам в YAML, порядок = порядок изучения |
| `media/audio` | Звук слов, `<тема>/<slug>.mp3` |
| `deploy/Caddyfile` | Caddy: статика фронта, прокси `/api`, раздача `/media`, HTTPS |
| `docs/prototype.html` | Кликабельный прототип, визуальный референс |

## Локальная разработка

Нужны Docker, [uv](https://docs.astral.sh/uv/) и pnpm.

```sh
cp .env.example .env        # при занятом 5432 поменяйте POSTGRES_PORT и DATABASE_URL
make db                     # PostgreSQL в Docker
make migrate && make seed   # схема и все темы: буквы, слоги, слова
make api                    # http://localhost:8000, документация /api/docs
make web                    # http://localhost:5173, /api проксируется на 8000
make pair                   # одноразовая ссылка привязки без Telegram, как из бота
make token                  # общая ссылка с тестовым токеном: логинит любой браузер
```

Ссылки печатаются для `http://localhost` (стек в Docker); при `make web` замените
адрес на `http://localhost:5173`, а для телефона в той же сети — на IP компьютера.

Бот локально: впишите `BOT_TOKEN`, свой Telegram id в `ADMIN_TELEGRAM_IDS` и
секрет `BOT_API_TOKEN` (`openssl rand -hex 32`) в `.env`, поднимите `make api`,
затем `make bot`. Бот ходит только в API (`API_URL`, по умолчанию
`http://localhost:8000`), в базу он не заглядывает. В Telegram: `/start`,
`/addchild Сандро`, `/pair`.

Если API слушает другой порт: `API_URL=http://localhost:8001 make web`.

Проверки:

```sh
make test   # backend
make lint   # ruff, mypy, oxlint, tsc
```

Всё разом в Docker: `make dev` (миграции и seed применяются при старте `api`).

## Деплой на чистый сервер

1. Сервер с Docker и docker compose, домен с A-записью на сервер, открытые порты 80 и 443.
2. `git clone … && cd mziko && cp .env.example .env`, в `.env`:
   - `POSTGRES_PASSWORD` — свой;
   - `SITE_ADDRESS=mziko.example.com` — Caddy сам получит сертификат;
   - `PUBLIC_URL=https://mziko.example.com` — попадает в ссылки привязки;
   - `BOT_TOKEN` от @BotFather, `ADMIN_TELEGRAM_IDS=[123456789]` — ваш id;
   - `BOT_API_TOKEN` — секрет между ботом и API, `openssl rand -hex 32`.
3. `docker compose up -d --build`. Поднимутся `db`, `api` (накатит миграции и слова),
   `bot` и `web`.
4. В Telegram: `/start`, `/addchild Сандро`, `/pair`. Ссылку из ответа открыть на iPad,
   затем «Поделиться → На экран Домой».

Обновление: `git pull && docker compose up -d --build`.
Резервная копия базы: `docker compose exec db pg_dump -U mziko mziko > backup.sql`.

## Контент и звук

Слова правятся в `content/topics/*.yaml`, затем `make seed` (или перезапуск `api`).
Добавленные слова получают звук командой `make tts` (временный синтез, уже
существующие файлы не перезаписываются), а картинки для новых эмодзи — командой
`make twemoji` (набор Twemoji, CC BY 4.0, файлы в `media/twemoji/`). Транскрипции
и звук перед запуском проверяет носитель языка, см. [content/README.md](content/README.md).
