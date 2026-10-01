"""Rendering tests for the parent card page: real data, plus the honest empty/error states.

Follows the fake-API-plus-fake-Google pattern from test_login.py / test_parents_page.py.
"""

import os
from datetime import timedelta
from typing import Any

import httpx
from httpx import ASGITransport, AsyncClient

os.environ.update(
    ADMIN_SESSION_SECRET="test-secret",
    ADMIN_EMAIL="Owner@Example.com",
    ADMIN_API_TOKEN="test-admin-token",
    API_URL="http://api.test",
    PUBLIC_URL="http://localhost",
)

from app.api import AdminApi  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.format import today_tbilisi  # noqa: E402
from app.main import GoogleOutcome, Identity, create_app, google_outcome  # noqa: E402

get_settings.cache_clear()

# The route reads the real clock (today_tbilisi()), not an injectable date, so
# every date below is anchored to "today" rather than hardcoded -- otherwise
# the "открыта" chip, the calendar's "today" cell and the day counts would
# only pass on the one calendar date they were written against.
TODAY = today_tbilisi()
THIS_MONDAY = TODAY - timedelta(days=TODAY.weekday())
LAST_MONDAY = THIS_MONDAY - timedelta(days=7)
YESTERDAY = TODAY - timedelta(days=1)
DEVICE_REVOKED_AT = TODAY - timedelta(days=42)


def fake_api(parent_id: int, response: httpx.Response) -> AdminApi:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/api/admin/parents/{parent_id}"
        return response

    return AdminApi(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handle),
            base_url="http://api.test/api/admin",
            headers={"Authorization": "Bearer test-admin-token"},
        )
    )


async def signed_in_client(parent_id: int, response: httpx.Response) -> AsyncClient:
    """A logged-in owner session, backed by a fake API answering one parent-card request."""
    app = create_app()
    app.state.api = fake_api(parent_id, response)
    app.dependency_overrides[google_outcome] = lambda: GoogleOutcome(
        Identity("owner@example.com", verified=True)
    )
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")
    await client.get("/admin/login/callback?code=x&state=y")
    return client


# Сандро: a done topic, one in-progress topic, today's lesson left unfinished,
# one open (current) week and one paid week, one active and one revoked device.
CHILD_A: dict[str, Any] = {
    "id": 10,
    "name": "Сандро",
    "created_at": "2026-08-14T00:00:00",
    "code": "PUMA-7205",
    "login_url": "https://mziko.example/c/PUMA-7205",
    "rate": 10,
    "cap_lari": 15,
    "show_hint": True,
    "learned_words": 11,
    "topics": [
        {
            "slug": "letters1",
            "icon": "🔤",
            "title_ru": "Буквы 1",
            "learned": 8,
            "total": 8,
            "started": True,
        },
        {
            "slug": "colors",
            "icon": "🎨",
            "title_ru": "Цвета",
            "learned": 3,
            "total": 10,
            "started": True,
        },
    ],
    "study_days": [
        {"day": YESTERDAY.isoformat(), "finished": True},
        {"day": TODAY.isoformat(), "finished": False},  # today, unfinished
    ],
    "first_try_pct": 82,
    "weeks": [
        {
            "id": 1,
            "week_start": THIS_MONDAY.isoformat(),
            "week_end": (THIS_MONDAY + timedelta(days=6)).isoformat(),
            "coins": 40,
            "status": "open",
            "lari_due": 4.0,
            "lari_paid": None,
            "paid_at": None,
        },
        {
            "id": 2,
            "week_start": LAST_MONDAY.isoformat(),
            "week_end": (LAST_MONDAY + timedelta(days=6)).isoformat(),
            "coins": 150,
            "status": "paid",
            "lari_due": 15.0,
            "lari_paid": 15.0,
            "paid_at": f"{THIS_MONDAY.isoformat()}T08:00:00",
        },
    ],
    "devices": [
        {
            "id": 1,
            "name": "iPad Сандро",
            "created_at": "2026-08-14T00:00:00",
            "last_seen_at": f"{TODAY.isoformat()}T09:00:00",
            "revoked_at": None,
        },
        {
            "id": 2,
            "name": "Старый iPad",
            "created_at": "2026-06-01T00:00:00",
            "last_seen_at": "2026-08-01T00:00:00",
            "revoked_at": f"{DEVICE_REVOKED_AT.isoformat()}T00:00:00",
        },
    ],
}

# Мариам: one topic in progress, one untouched, a session that never finished,
# no answers yet (first_try_pct is None), no coins week and no devices.
CHILD_B: dict[str, Any] = {
    "id": 11,
    "name": "Мариам",
    "created_at": "2026-09-02T00:00:00",
    "code": "ZEBU-1190",
    "login_url": "https://mziko.example/c/ZEBU-1190",
    "rate": 10,
    "cap_lari": 15,
    "show_hint": False,
    "learned_words": 2,
    "topics": [
        {
            "slug": "greetings",
            "icon": "👋",
            "title_ru": "Приветствия",
            "learned": 2,
            "total": 10,
            "started": True,
        },
        {
            "slug": "numbers",
            "icon": "🔢",
            "title_ru": "Числа",
            "learned": 0,
            "total": 10,
            "started": False,
        },
    ],
    "study_days": [{"day": YESTERDAY.isoformat(), "finished": False}],
    "first_try_pct": None,
    "weeks": [],
    "devices": [],
}


async def test_parent_with_two_children() -> None:
    parent = {
        "id": 2,
        "telegram_id": 318552904,
        "name": "Нино Церетели",
        "photo_url": "https://t.me/i/userpic/320/nino.svg",
        "created_at": "2026-08-12T09:00:00",
        "children": [CHILD_A, CHILD_B],
    }
    client = await signed_in_client(2, httpx.Response(200, json=parent))
    r = await client.get("/admin/parents/2")
    await client.aclose()
    assert r.status_code == 200
    assert "Нино Церетели" in r.text
    assert '<span class="av"><img src="https://t.me/i/userpic/320/nino.svg"' in r.text
    assert "PUMA-7205" in r.text

    assert "пройдена" in r.text  # Буквы 1: learned == total
    assert 'class="cell part today"' in r.text  # today's lesson, unfinished
    assert "открыта" in r.text  # this week's row
    assert "выдано 15,0 ₾" in r.text  # last week, paid
    assert 'class="rv"' in r.text
    assert f"отозвано {DEVICE_REVOKED_AT.strftime('%d.%m.%Y')}" in r.text
    assert "уроков за 4 недели: <b>2</b>" in r.text
    assert "ответов верно с первой попытки: <b>82%</b>" in r.text

    assert "Мариам" in r.text
    assert "в работе" in r.text
    assert "не начата" in r.text
    assert "Недель пока нет" in r.text
    assert "Устройств пока нет" in r.text
    assert "уроков за 4 недели: <b>1</b>" in r.text
    assert "ответов верно с первой попытки: <b>—</b>" in r.text


async def test_parent_without_children() -> None:
    parent: dict[str, Any] = {
        "id": 3,
        "telegram_id": 719045213,
        "name": "Заур Немсадзе",
        "photo_url": None,
        "created_at": "2026-09-25T09:00:00",
        "children": [],
    }
    client = await signed_in_client(3, httpx.Response(200, json=parent))
    r = await client.get("/admin/parents/3")
    await client.aclose()
    assert r.status_code == 200
    assert "Детей пока нет" in r.text
    assert '<span class="av"></span>' in r.text
    assert "/addchild" in r.text


async def test_freshly_added_child() -> None:
    fresh_child: dict[str, Any] = {
        "id": 20,
        "name": "Гурам",
        "created_at": "2026-10-01T00:00:00",
        "code": "FOXY-3348",
        "login_url": "https://mziko.example/c/FOXY-3348",
        "rate": 10,
        "cap_lari": 15,
        "show_hint": True,
        "learned_words": 0,
        "topics": [
            {
                "slug": "letters1",
                "icon": "🔤",
                "title_ru": "Буквы 1",
                "learned": 0,
                "total": 8,
                "started": False,
            },
        ],
        "study_days": [],
        "first_try_pct": None,
        "weeks": [],
        "devices": [],
    }
    parent = {
        "id": 4,
        "telegram_id": 687120455,
        "name": "Дмитрий Козлов",
        "created_at": "2026-09-27T09:00:00",
        "children": [fresh_child],
    }
    client = await signed_in_client(4, httpx.Response(200, json=parent))
    r = await client.get("/admin/parents/4")
    await client.aclose()
    assert r.status_code == 200
    assert "FOXY-3348" in r.text
    assert "Прогресса пока нет" in r.text
    assert "Календарь появится после первого урока" in r.text
    assert "Недель пока нет" in r.text
    assert "Устройств пока нет" in r.text


async def test_unknown_parent_is_404() -> None:
    client = await signed_in_client(999, httpx.Response(404, json={"detail": "no such parent"}))
    r = await client.get("/admin/parents/999")
    await client.aclose()
    assert r.status_code == 200
    assert "Родитель не найден" in r.text
    assert "К списку родителей" in r.text


async def test_api_failure_shows_retry() -> None:
    def down(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("api is down")

    app = create_app()
    app.state.api = AdminApi(
        httpx.AsyncClient(transport=httpx.MockTransport(down), base_url="http://api.test/api/admin")
    )
    app.dependency_overrides[google_outcome] = lambda: GoogleOutcome(
        Identity("owner@example.com", verified=True)
    )
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")
    await client.get("/admin/login/callback?code=x&state=y")
    r = await client.get("/admin/parents/1")
    await client.aclose()
    assert r.status_code == 200
    assert "Не удалось загрузить карточку" in r.text
    assert "Повторить" in r.text
