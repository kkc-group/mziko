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
from app.telegram import signature, telegram_photo_url, telegram_user_id  # noqa: E402

get_settings.cache_clear()

BOT_TOKEN = "123456:test-bot-token"
PARENT_TG = 42
TODAY = date(2026, 9, 29)


def init_data(
    user_id: int = PARENT_TG,
    issued: datetime | None = None,
    token: str = BOT_TOKEN,
    photo_url: str | None = None,
) -> str:
    """What Telegram would hand the Mini App for this user, signed with the bot's token."""
    issued = issued or datetime.now(UTC)
    user: dict[str, Any] = {"id": user_id, "first_name": "Нино", "language_code": "ru"}
    if photo_url is not None:
        user["photo_url"] = photo_url
    fields = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user),
        "auth_date": str(int(issued.timestamp())),
    }
    fields["hash"] = signature(fields, token)
    return urlencode(fields)


def word(
    ka: str, ru: str, stage: int, last: date | None = None, shown: date | None = None
) -> dict[str, Any]:
    """A word as the API reports it; `shown` is the first lesson day of a stage-0 word."""
    first = shown or last
    return {
        "ka": ka,
        "ru": ru,
        "stage": stage,
        "last_correct_date": last.isoformat() if last else None,
        "introduced": first is not None,
        "introduced_on": first.isoformat() if first else None,
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
        [word("ბ", "буква б", 1, LONG_AGO), word("გ", "буква г", 0, shown=LONG_AGO)],
        "✏️",
    ),
    topic("syllables", "syllables", "Слоги", [word("ბა", "ба", 0)], "🧩"),
    topic(
        "colors",
        "words",
        "Цвета",
        [word("წითელი", "красный", 2, TODAY), word("ლურჯი", "синий", 0)],
        "🎨",
    ),
]
LESSONS_DONE = 4


def fake_api(
    children: list[dict[str, Any]] | None = CHILDREN,
    topics: list[dict[str, Any]] = TOPICS,
    *,
    known: bool = True,
    photos: list[str] | None = None,
    saved: list[tuple[str, str]] | None = None,
) -> ParentApi:
    """An API that answers only with the shared token, only for the known parent."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != "Bearer test-bot-api-token":
            return httpx.Response(401, json={"detail": "bot token required"})
        if not known or request.headers.get("X-Telegram-Id") != str(PARENT_TG):
            return httpx.Response(403, json={"detail": "unknown parent"})
        if request.url.path == "/api/parent/me/photo":
            if photos is None:
                return httpx.Response(500, json={"detail": "boom"})
            photos.append(json.loads(request.content)["photo_url"])
            return httpx.Response(204)
        if request.url.path == "/api/parent/children":
            return httpx.Response(200, json=children or [])
        if request.method == "PUT":  # /children/10/topics/<slug>/access
            # ["", "api", "parent", "children", "10", "topics", slug, "access"]
            parts = request.url.path.split("/")
            assert parts[:6] + parts[7:] == [*"/api/parent/children/10/topics".split("/"), "access"]
            if saved is None:
                return httpx.Response(500, json={"detail": "boom"})
            saved.append((parts[6], json.loads(request.content)["access"]))
            return httpx.Response(204)
        assert request.url.path == "/api/parent/children/10/progress"
        return httpx.Response(
            200, json={"child": CHILDREN[0], "topics": topics, "lessons_done": LESSONS_DONE}
        )

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


async def test_every_open_reports_the_profile_photo(client: AsyncClient) -> None:
    url = "https://t.me/i/userpic/320/abc.svg"
    assert telegram_photo_url(init_data(photo_url=url)) == url
    assert telegram_photo_url(init_data()) is None and telegram_photo_url("user=nope") is None

    photos: list[str] = []
    client.app.state.parent_api = fake_api(photos=photos)  # type: ignore[attr-defined]
    # The entry itself reports nothing: a parent with a month-long cookie never passes it.
    r = await client.post("/cabinet/session", data={"init_data": init_data(photo_url=url)})
    assert r.status_code == 303 and photos == []
    # Every page carries the background report, and the cabinet itself never shows the photo.
    page = (await client.get("/cabinet/")).text
    assert "fetch('/cabinet/photo'" in page and url not in page

    # The report needs no cookie, only Telegram's signature.
    client.cookies.clear()
    r = await client.post("/cabinet/photo", data={"init_data": init_data(photo_url=url)})
    assert r.status_code == 204 and photos == [url]
    # No photo in Telegram's data (hidden or absent) reports nothing: the saved link stays.
    r = await client.post("/cabinet/photo", data={"init_data": init_data()})
    assert r.status_code == 204
    # A wrong signature reports nothing either, and is answered the same way.
    bad = init_data(token="other", photo_url=url)
    r = await client.post("/cabinet/photo", data={"init_data": bad})
    assert r.status_code == 204 and photos == [url]
    # The default fake API fails the photo call (500): still 204.
    client.app.state.parent_api = fake_api()  # type: ignore[attr-defined]
    r = await client.post("/cabinet/photo", data={"init_data": init_data(photo_url=url)})
    assert r.status_code == 204


async def test_stale_cookie_asks_telegram_again(client: AsyncClient) -> None:
    r = await client.get("/cabinet/", cookies={"mziko_cabinet": "stale"})
    assert r.status_code == 200 and "Откройте из бота" in r.text


async def test_unregistered_telegram_user_is_sent_to_start(client: AsyncClient) -> None:
    client.app.state.parent_api = fake_api(known=False)  # type: ignore[attr-defined]
    await enter(client)
    r = await client.get("/cabinet/")
    assert r.status_code == 200 and "Вы ещё не зарегистрированы" in r.text


# --- the progress page ---------------------------------------------------------------


async def test_progress_page_shows_sections_topics_and_words(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fixtures are dated against TODAY, so the page must count idle days from it too.
    monkeypatch.setattr("app.cabinet.today_tbilisi", lambda: TODAY)
    await enter(client)
    r = await client.get("/cabinet/")
    html = r.text
    assert "Выучено <b>2</b> из 7 карточек" in html
    assert "В работе: <b>3</b> · пройдено уроков: <b>4</b>" in html
    for section in ("Буквы", "Слоги", "Слова"):
        assert f"<b>{section}</b>" in html
    assert "<b>Буквы</b><span>2 из 4 · 2 в работе</span>" in html
    assert "<b>Слоги</b><span>0 из 1</span>" in html
    assert "✓" not in html  # the check mark is CSS, the class carries it
    assert 'class="tcnt done">2 из 2<' in html
    assert 'class="tcnt now">0 из 2<small>2 в работе</small>' in html
    assert 'class="tcnt ">0 из 1<' in html
    # The bar: light segment for words in work, solid for learned, both from the left.
    assert '<i class="soft" style="width:100%"></i><i style="width:0%"></i>' in html
    assert "12 дн. без продвижения" in html
    assert "წითელი" in html and "· красный" in html
    # A met word at stage 0 says so; a word the child never met is faded and counted.
    assert '· буква г</span></span><span class="chip open">показано</span>' in html
    assert 'class="w new"' in html and "Бледные ещё не были на уроках: 1 слово" in html
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
    assert "Бледные ещё не были" not in r.text  # nothing met yet: no point counting the rest


async def test_all_wrong_first_day_still_counts_as_started(client: AsyncClient) -> None:
    """Every word shown, none guessed on the first try: stages are 0, but the lesson happened."""
    shown = [word("ა", "буква а", 0, shown=TODAY)] * 3
    client.app.state.parent_api = fake_api(  # type: ignore[attr-defined]
        CHILDREN[:1], [topic("letters-1", "letters", "Буквы 1", shown)]
    )
    await enter(client)
    r = await client.get("/cabinet/")
    assert "Занятий пока не было" not in r.text
    assert "В работе: <b>3</b>" in r.text and 'class="tcnt now">0 из 3<small>3 в работе' in r.text
    assert r.text.count("показано") == 3


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
    assert (sections[0].learned, sections[0].in_work, sections[0].total) == (2, 2, 4)
    assert (by_slug["colors"].pct, by_slug["colors"].pct_started) == (0, 50)
    # A topic met but never answered right: idle counts from the day it was shown.
    all_wrong = [topic("greetings", "words", "Приветствия", [word("კი", "да", 0, shown=LONG_AGO)])]
    assert build_sections(all_wrong, TODAY)[2].topics[0].idle_days == 12


# --- topic access ---------------------------------------------------------------------


async def test_topic_switch_shows_the_access_and_what_it_means(client: AsyncClient) -> None:
    topics = [
        TOPICS[0],
        {**TOPICS[1], "access": "closed", "status": "locked"},  # started 12 days ago
        TOPICS[2],
        {**TOPICS[3], "status": "locked", "waits_for": "Первые слова"},
        {**topic("food", "words", "Еда", [word("პური", "хлеб", 0)]), "access": "open"},
        {**topic("home", "words", "Дом", [word("კარი", "дверь", 0)]), "status": "locked"},
    ]
    client.app.state.parent_api = fake_api(topics=topics)  # type: ignore[attr-defined]
    await enter(client)
    html = (await client.get("/cabinet/?open=colors")).text

    assert html.count('<form class="acc" method="post"') == len(topics)
    assert 'action="/cabinet/topics/colors/access"' in html
    assert '<input type="hidden" name="child" value="10">' in html
    assert '<details class="topic" id="t-colors" open>' in html
    assert '<details class="topic" id="t-food">' in html
    assert html.count('value="closed" class="on" aria-pressed="true"') == 1
    assert html.count('value="open" class="on" aria-pressed="true"') == 1

    # A closed topic says so in the row and loses the idle mark; an opened one says so too.
    assert html.count("закрыта вручную") == 1 and html.count("открыта вручную") == 1
    assert "без продвижения" not in html
    assert "У ребёнка на теме замок, «Повторить» тоже недоступно." in html
    assert "Ребёнок может начать тему сразу" in html
    assert "Тема идёт по порядку. Сейчас открыта." in html
    assert "Откроется после темы «Первые слова»." in html
    assert "Откроется завтра: сегодня в этом разделе уже начата новая тема." in html
    assert "Не получилось сохранить" not in html


async def test_topic_switch_saves_and_comes_back_to_the_topic(client: AsyncClient) -> None:
    saved: list[tuple[str, str]] = []
    client.app.state.parent_api = fake_api(saved=saved)  # type: ignore[attr-defined]
    url = "/cabinet/topics/colors/access"

    # No session: nothing is saved, the entry page takes over.
    r = await client.post(url, data={"child": "10", "access": "closed"})
    assert (r.status_code, r.headers["location"], saved) == (303, "/cabinet/", [])

    await enter(client)
    r = await client.post(url, data={"child": "10", "access": "closed"})
    assert r.status_code == 303
    assert r.headers["location"] == "/cabinet/?child=10&open=colors#t-colors"
    assert saved == [("colors", "closed")]

    # An unknown position or a broken child id never reaches the API.
    for data in ({"child": "10", "access": "sideways"}, {"child": "x", "access": "open"}, {}):
        r = await client.post(url, data=data)
        assert r.status_code == 303 and "&failed=1#t-colors" in r.headers["location"]
    assert saved == [("colors", "closed")]


async def test_topic_switch_failure_is_shown_at_the_topic(client: AsyncClient) -> None:
    await enter(client)  # the default fake API answers 500 to a write
    r = await client.post("/cabinet/topics/colors/access", data={"child": "10", "access": "open"})
    assert r.headers["location"] == "/cabinet/?child=10&open=colors&failed=1#t-colors"
    html = (await client.get(r.headers["location"])).text
    assert html.count("Не получилось сохранить.") == 1
    assert "Тема осталась «По порядку», попробуйте ещё раз." in html
    assert '<details class="topic" id="t-colors" open>' in html
