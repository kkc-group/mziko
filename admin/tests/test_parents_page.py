"""Rendering tests for the parents table: real row markup and the empty states.

Follows the fake-API-plus-fake-Google pattern from test_login.py (see there for
why the lifespan is skipped and google_outcome is overridden).
"""

import os
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
from app.main import GoogleOutcome, Identity, create_app, google_outcome  # noqa: E402

get_settings.cache_clear()


def fake_api(parents: list[dict[str, Any]]) -> AdminApi:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/admin/parents"
        return httpx.Response(200, json=parents)

    return AdminApi(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handle),
            base_url="http://api.test/api/admin",
            headers={"Authorization": "Bearer test-admin-token"},
        )
    )


async def signed_in_client(parents: list[dict[str, Any]]) -> AsyncClient:
    """A logged-in owner session, backed by a fake API answering the given rows."""
    app = create_app()
    app.state.api = fake_api(parents)
    app.dependency_overrides[google_outcome] = lambda: GoogleOutcome(
        Identity("owner@example.com", verified=True)
    )
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")
    await client.get("/admin/login/callback?code=x&state=y")
    return client


async def test_parent_without_a_name_or_children() -> None:
    rows = [
        {
            "id": 1,
            "telegram_id": 5902117648,
            "name": None,
            "created_at": "2026-08-02T09:00:00",
            "last_study_date": None,
            "children": [],
        }
    ]
    client = await signed_in_client(rows)
    r = await client.get("/admin/")
    await client.aclose()
    assert r.status_code == 200
    assert "— без имени" in r.text
    assert "5902117648" in r.text
    assert "детей нет" in r.text


async def test_parent_with_two_children_and_a_cap() -> None:
    rows = [
        {
            "id": 2,
            "telegram_id": 318552904,
            "name": "Нино Беридзе",
            "created_at": "2026-08-12T09:00:00",
            "last_study_date": "2026-09-27",
            "children": [
                {
                    "id": 10,
                    "name": "Сандро",
                    "learned_words": 42,
                    "last_study_date": "2026-09-27",
                    "this_week": {
                        "id": 1,
                        "week_start": "2026-09-28",
                        "week_end": "2026-10-04",
                        "coins": 600,
                        "status": "open",
                        "lari_due": 30.0,
                        "lari_paid": None,
                        "paid_at": None,
                    },
                    "last_week": {
                        "id": 2,
                        "week_start": "2026-09-21",
                        "week_end": "2026-09-27",
                        "coins": 300,
                        "status": "paid",
                        "lari_due": 15.0,
                        "lari_paid": 15.0,
                        "paid_at": "2026-09-28T08:00:00",
                    },
                    "cap_reached": True,
                },
                {
                    "id": 11,
                    "name": "Мариам",
                    "learned_words": 17,
                    "last_study_date": None,
                    "this_week": None,
                    "last_week": None,
                    "cap_reached": False,
                },
            ],
        }
    ]
    client = await signed_in_client(rows)
    r = await client.get("/admin/")
    await client.aclose()
    assert r.status_code == 200
    assert "Нино Беридзе" in r.text
    assert "Сандро" in r.text and "Мариам" in r.text
    assert "потолок" in r.text
    assert "30,0 ₾" in r.text
    assert "выдано 15,0 ₾" in r.text
    assert "не занимался" in r.text


async def test_empty_parents_list() -> None:
    client = await signed_in_client([])
    r = await client.get("/admin/")
    await client.aclose()
    assert r.status_code == 200
    assert "Родителей пока нет" in r.text
