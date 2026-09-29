"""The parents' cabinet: the Telegram entry boundary and the progress page's states.

Follows the fake-API pattern of test_login.py: the API answers only with the
shared token and only about the parent named in X-Telegram-Id.
"""

import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.update(
    ADMIN_SESSION_SECRET="test-secret",
    ADMIN_EMAIL="Owner@Example.com",
    ADMIN_API_TOKEN="test-admin-token",
    BOT_TOKEN="123456:test-bot-token",
    BOT_API_TOKEN="test-bot-api-token",
    API_URL="http://api.test",
    PUBLIC_URL="http://localhost",
)

from app.api import ParentApi  # noqa: E402
from app.cabinet import IDLE_DAYS, build_sections  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.telegram import signature, telegram_user_id  # noqa: E402

get_settings.cache_clear()

BOT_TOKEN = "123456:test-bot-token"
PARENT_TG = 42
TODAY = date(2026, 9, 29)


def init_data(
    user_id: int = PARENT_TG, issued: datetime | None = None, token: str = BOT_TOKEN
) -> str:
    """What Telegram would hand the Mini App for this user, signed with the bot's token."""
    issued = issued or datetime.now(UTC)
    fields = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Нино", "language_code": "ru"}),
        "auth_date": str(int(issued.timestamp())),
    }
    fields["hash"] = signature(fields, token)
    return urlencode(fields)


def word(ka: str, ru: str, stage: int, last: date | None = None) -> dict[str, Any]:
    return {
        "ka": ka,
        "ru": ru,
        "stage": stage,
        "last_correct_date": last.isoformat() if last else None,
    }


def topic(
    slug: str, section: str, title: str, words: list[dict[str, Any]], icon: str = "🐶"
) -> dict[str, Any]:
    return {
        "slug": slug,
        "section": section,
        "icon": icon,
        "title_ru": title,
        "learned": sum(1 for w in words if w["stage"] >= 3),
        "total": len(words),
        "words": words,
    }


CHILDREN = [
    {"id": 10, "name": "Сандро", "rate": 10, "cap_lari": 15, "show_hint": True},
    {"id": 11, "name": "Мариам", "rate": 10, "cap_lari": 15, "show_hint": True},
]
LONG_AGO = TODAY - timedelta(days=12)
TOPICS = [
    topic("letters-1", "letters", "Буквы 1", [word("ა", "буква а", 3, TODAY)] * 2, "🔤"),
    topic(
        "letters-2",
        "letters",
        "Буквы 2",
        [word("ბ", "буква б", 1, LONG_AGO), word("გ", "буква г", 0)],
        "✏️",
    ),
    topic("syllables", "syllables", "Слоги", [word("ბა", "ба", 0)], "🧩"),
    topic("colors", "words", "Цвета", [word("წითელი", "красный", 2, TODAY)], "🎨"),
]


def fake_api(
    children: list[dict[str, Any]] | None = CHILDREN,
    topics: list[dict[str, Any]] = TOPICS,
    *,
    known: bool = True,
) -> ParentApi:
    """An API that answers only with the shared token, only for the known parent."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != "Bearer test-bot-api-token":
            return httpx.Response(401, json={"detail": "bot token required"})
        if not known or request.headers.get("X-Telegram-Id") != str(PARENT_TG):
            return httpx.Response(403, json={"detail": "unknown parent"})
        if request.url.path == "/api/parent/children":
            return httpx.Response(200, json=children or [])
        assert request.url.path == "/api/parent/children/10/progress"
        return httpx.Response(200, json={"child": CHILDREN[0], "topics": topics})

    return ParentApi(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handle),
            base_url="http://api.test/api/parent",
            headers={"Authorization": "Bearer test-bot-api-token"},
        )
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.state.parent_api = fake_api()  # the lifespan is not started
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as c:
        c.app = app  # type: ignore[attr-defined]
        yield c


async def enter(client: AsyncClient) -> None:
    r = await client.post("/cabinet/session", data={"init_data": init_data()})
    assert r.status_code == 303 and r.headers["location"] == "/cabinet/?in=1"
    assert "mziko_cabinet" in r.cookies


# --- the entry boundary -------------------------------------------------------------


def test_init_data_is_trusted_only_with_telegram_signature() -> None:
    now = datetime.now(UTC)
    hour = timedelta(hours=1)
    assert telegram_user_id(init_data(), BOT_TOKEN, now, hour) == PARENT_TG
    assert telegram_user_id(init_data(token="other"), BOT_TOKEN, now, hour) is None
    assert telegram_user_id(init_data(), "", now, hour) is None
    assert telegram_user_id("", BOT_TOKEN, now, hour) is None
    tampered = init_data().replace(str(PARENT_TG), "43")
    assert telegram_user_id(tampered, BOT_TOKEN, now, hour) is None
    stale = init_data(issued=now - timedelta(hours=2))
    assert telegram_user_id(stale, BOT_TOKEN, now, hour) is None


async def test_browser_without_telegram_is_told_to_open_from_the_bot(client: AsyncClient) -> None:
    r = await client.get("/cabinet/")
    assert r.status_code == 200
    assert "Откройте из бота" in r.text and 'action="/cabinet/session"' in r.text
    # After a failed entry the page does not loop back into the form.
    again = await client.get("/cabinet/?in=1")
    assert "Не получилось войти" in again.text and "/cabinet/session" not in again.text


async def test_bad_init_data_is_refused(client: AsyncClient) -> None:
    r = await client.post("/cabinet/session", data={"init_data": init_data(token="other")})
    assert r.status_code == 401 and "Не получилось войти" in r.text
    assert "mziko_cabinet" not in r.cookies
    assert "Откройте из бота" in (await client.get("/cabinet/")).text


async def test_signed_parent_gets_a_session_and_their_children(client: AsyncClient) -> None:
    await enter(client)
    r = await client.get("/cabinet/")
    assert r.status_code == 200, r.text
    assert "Сандро" in r.text and "Мариам" in r.text
    assert 'href="/cabinet/?child=11"' in r.text
    assert "Неделя · скоро" in r.text


async def test_stale_cookie_asks_telegram_again(client: AsyncClient) -> None:
    r = await client.get("/cabinet/", cookies={"mziko_cabinet": "stale"})
    assert r.status_code == 200 and "Откройте из бота" in r.text


async def test_unregistered_telegram_user_is_sent_to_start(client: AsyncClient) -> None:
    client.app.state.parent_api = fake_api(known=False)  # type: ignore[attr-defined]
    await enter(client)
    r = await client.get("/cabinet/")
    assert r.status_code == 200 and "Вы ещё не зарегистрированы" in r.text


# --- the progress page ---------------------------------------------------------------


async def test_progress_page_shows_sections_topics_and_words(client: AsyncClient) -> None:
    await enter(client)
    r = await client.get("/cabinet/")
    html = r.text
    assert "Выучено <b>2</b> из 6 карточек" in html
    for section in ("Буквы", "Слоги", "Слова"):
        assert f"<b>{section}</b>" in html
    assert "✓" not in html  # the check mark is CSS, the class carries it
    assert 'class="tcnt done">2 из 2' in html
    assert 'class="tcnt now">0 из 2' in html
    assert 'class="tcnt ">0 из 1' in html
    assert "12 дн. без продвижения" in html
    assert "წითელი" in html and "· красный" in html
    assert "Занятий пока не было" not in html


async def test_child_is_chosen_by_query_and_falls_back_to_the_first(client: AsyncClient) -> None:
    await enter(client)
    r = await client.get("/cabinet/?child=10")
    assert 'href="/cabinet/?child=10" aria-current="true"' in r.text
    # An id that is not this parent's child: the first child, not an error.
    r = await client.get("/cabinet/?child=999")
    assert r.status_code == 200 and 'href="/cabinet/?child=10" aria-current="true"' in r.text


async def test_fresh_child_shows_the_empty_notice(client: AsyncClient) -> None:
    untouched = [topic("letters-1", "letters", "Буквы 1", [word("ა", "буква а", 0)] * 3)]
    client.app.state.parent_api = fake_api(CHILDREN[:1], untouched)  # type: ignore[attr-defined]
    await enter(client)
    r = await client.get("/cabinet/")
    assert "Занятий пока не было" in r.text and "Выучено <b>0</b> из 3 карточек" in r.text
    assert 'class="kids"' not in r.text  # one child: no switcher


async def test_no_children_yet(client: AsyncClient) -> None:
    client.app.state.parent_api = fake_api(children=[])  # type: ignore[attr-defined]
    await enter(client)
    r = await client.get("/cabinet/")
    assert r.status_code == 200 and "Детей пока нет" in r.text


async def test_api_failure_is_shown_with_retry(client: AsyncClient) -> None:
    await enter(client)

    def down(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("api is down")

    client.app.state.parent_api = ParentApi(  # type: ignore[attr-defined]
        httpx.AsyncClient(transport=httpx.MockTransport(down), base_url="http://api.test")
    )
    r = await client.get("/cabinet/?child=10")
    assert r.status_code == 200
    assert "Не получилось загрузить" in r.text and 'href="/cabinet/?child=10">Повторить' in r.text


def test_idle_mark_only_on_started_unfinished_topics() -> None:
    sections = build_sections(TOPICS, TODAY)
    by_slug = {t.slug: t for s in sections for t in s.topics}
    assert by_slug["letters-1"].idle_days is None  # done
    assert by_slug["letters-2"].idle_days == 12  # started, stuck
    assert by_slug["syllables"].idle_days is None  # not started
    assert by_slug["colors"].idle_days is None  # grew today
    recent = build_sections(TOPICS, LONG_AGO + timedelta(days=IDLE_DAYS - 1))
    assert {t.idle_days for s in recent for t in s.topics} == {None}
    assert [s.key for s in sections] == ["letters", "syllables", "words"]
    assert (sections[0].learned, sections[0].total) == (2, 4)
