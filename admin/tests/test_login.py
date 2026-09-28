"""The access boundary: only the owner's verified Google email gets a session."""

import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
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

PARENTS: list[dict[str, Any]] = [
    {
        "id": 1,
        "telegram_id": 42,
        "name": "Папа",
        "created_at": "2026-08-01T00:00:00",
        "last_study_date": None,
        "children": [],
    }
]


def fake_api() -> AdminApi:
    """An API that answers only with the shared token, like the real one."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != "Bearer test-admin-token":
            return httpx.Response(401, json={"detail": "admin token required"})
        assert request.url.path == "/api/admin/parents"
        return httpx.Response(200, json=PARENTS)

    return AdminApi(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handle),
            base_url="http://api.test/api/admin",
            headers={"Authorization": "Bearer test-admin-token"},
        )
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.state.api = fake_api()  # the lifespan (and Google metadata fetch) is not started
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as c:
        c.app = app  # type: ignore[attr-defined]
        yield c


def pretend_google(client: AsyncClient, outcome: GoogleOutcome) -> None:
    client.app.dependency_overrides[google_outcome] = lambda: outcome  # type: ignore[attr-defined]


async def test_anonymous_is_sent_to_login(client: AsyncClient) -> None:
    r = await client.get("/admin/")
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"
    login = await client.get("/admin/login")
    assert login.status_code == 200 and "Войти через Google" in login.text
    assert "Сессия закончилась" not in login.text


async def test_owner_gets_a_session_and_the_list(client: AsyncClient) -> None:
    pretend_google(client, GoogleOutcome(Identity("owner@example.com", verified=True)))
    r = await client.get("/admin/login/callback?code=x&state=y")
    assert r.status_code == 303 and r.headers["location"] == "/admin/"
    assert "mziko_admin" in r.cookies

    lst = await client.get("/admin/")
    assert lst.status_code == 200, lst.text
    assert "owner@example.com" in lst.text and "Папа" in lst.text

    out = await client.get("/admin/logout")
    assert out.status_code == 303
    # Logout drops the cookie: a plain login page, no "session ended" notice.
    again = await client.get("/admin/")
    assert again.status_code == 303 and again.headers["location"] == "/admin/login"


async def test_stale_cookie_explains_that_the_session_ended(client: AsyncClient) -> None:
    # A cookie the server can no longer read (expired signature, rotated secret).
    r = await client.get("/admin/", cookies={"mziko_admin": "stale"})
    assert r.status_code == 303 and r.headers["location"] == "/admin/login?expired=1"
    assert "Сессия закончилась" in (await client.get("/admin/login?expired=1")).text


@pytest.mark.parametrize(
    "identity",
    [
        Identity("someone@gmail.com", verified=True),
        Identity("owner@example.com", verified=False),
    ],
)
async def test_other_or_unverified_email_is_denied(client: AsyncClient, identity: Identity) -> None:
    pretend_google(client, GoogleOutcome(identity))
    r = await client.get("/admin/login/callback?code=x&state=y")
    assert r.status_code == 200
    assert "Доступ не выдан" in r.text and identity.email in r.text
    assert (await client.get("/admin/")).status_code == 303


async def test_google_error_shows_retry(client: AsyncClient) -> None:
    r = await client.get("/admin/login/callback?error=access_denied")
    assert r.status_code == 200 and "Вход не завершён" in r.text
    assert (await client.get("/admin/")).status_code == 303


async def test_api_failure_is_shown_not_raised(client: AsyncClient) -> None:
    pretend_google(client, GoogleOutcome(Identity("owner@example.com", verified=True)))
    await client.get("/admin/login/callback?code=x&state=y")

    def down(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("api is down")

    client.app.state.api = AdminApi(  # type: ignore[attr-defined]
        httpx.AsyncClient(transport=httpx.MockTransport(down), base_url="http://api.test/api/admin")
    )
    r = await client.get("/admin/")
    assert r.status_code == 200 and "Не удалось загрузить список" in r.text
