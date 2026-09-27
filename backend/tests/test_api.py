"""End-to-end HTTP tests: pairing, auth, lesson flow. The clock is a mutable holder."""

import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_now
from app.main import create_app
from app.models import Child, Parent
from app.services import pairing
from tests.helpers import at

DAY1 = date(2026, 9, 22)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment


@pytest.fixture
def clock() -> Clock:
    return Clock(at(DAY1))


@pytest.fixture
async def client(db: AsyncSession, clock: Clock) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_now] = lambda: clock.moment
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def parent(db: AsyncSession, child: Child) -> Parent:
    parent = Parent(telegram_id=1000 + child.id, name="Папа")
    parent.children.append(child)
    db.add(parent)
    await db.flush()
    return parent


async def pair(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> dict[str, str]:
    code = await pairing.create_pair_code(db, parent, child, clock.moment)
    response = await client.post(f"/api/pair/{code.code}", json={"device_name": "iPad"})
    assert response.status_code == 200, response.text
    token: str = response.json()["device_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_pair_code_works_once_and_expires(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    code = await pairing.create_pair_code(db, parent, child, clock.moment)
    first = await client.post(f"/api/pair/{code.code}")
    assert first.status_code == 200
    assert first.json()["child"] == {"id": child.id, "name": "Сандро"}
    assert len(first.json()["device_token"]) > 30

    second = await client.post(f"/api/pair/{code.code}")
    assert second.status_code == 404

    stale = await pairing.create_pair_code(db, parent, child, clock.moment)
    clock.moment += timedelta(minutes=16)
    assert (await client.post(f"/api/pair/{stale.code}")).status_code == 404
    assert (await client.post("/api/pair/garbage")).status_code == 404


async def test_requests_need_a_valid_device_token(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    assert (await client.get("/api/me")).status_code == 401
    assert (
        await client.get("/api/me", headers={"Authorization": "Bearer nope"})
    ).status_code == 401

    headers = await pair(db, client, parent, child, clock)
    assert (await client.get("/api/me", headers=headers)).status_code == 200

    (device,) = await pairing.active_devices(db, child.id)
    await pairing.revoke_device(db, device.id, clock.moment)
    assert (await client.get("/api/me", headers=headers)).status_code == 401


async def test_full_lesson_flow_over_http(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    headers = await pair(db, client, parent, child, clock)

    me = (await client.get("/api/me", headers=headers)).json()
    assert me["settings"] == {"rate": 10, "cap_lari": 15, "show_hint": True}
    assert me["week"] == {
        "week_start": "2026-09-21",
        "today": "2026-09-22",
        "coins": 0,
        "lari": 0.0,
        "study_days": [],
    }
    slugs = [t["slug"] for t in me["topics"]]
    assert slugs[:5] == ["letters-1", "letters-2", "letters-3", "letters-4", "syllables"]
    assert len(slugs) == 18
    colors = next(t for t in me["topics"] if t["slug"] == "colors")
    assert (colors["total"], colors["learned"], colors["has_lesson"]) == (10, 0, True)
    assert len(me["stickers"]) == 225

    started = await client.post("/api/sessions", json={"topic_slug": "colors"}, headers=headers)
    assert started.status_code == 200
    session_id, steps = started.json()["session_id"], started.json()["steps"]
    assert [s["type"] for s in steps] == ["intro"] * 3 + ["listen"] * 3

    listen_index = 3
    step = steps[listen_index]
    wrong = next(o["slug"] for o in step["options"] if o["slug"] != step["word"]["slug"])
    bad = await client.post(
        f"/api/sessions/{session_id}/answers",
        json={
            "step_index": listen_index,
            "word_slug": wrong,
            "attempt": 1,
            "client_answer_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert bad.json()["correct"] is False and bad.json()["coins_gained"] == 0

    answer_id = str(uuid.uuid4())
    payload = {
        "step_index": 4,
        "word_slug": steps[4]["word"]["slug"],
        "attempt": 1,
        "client_answer_id": answer_id,
    }
    good = await client.post(f"/api/sessions/{session_id}/answers", json=payload, headers=headers)
    assert good.json() == {
        "correct": True,
        "coins_gained": 1,
        "word_learned": False,
        "week_coins": 1,
        "week_lari": 0.1,
    }
    retry = await client.post(f"/api/sessions/{session_id}/answers", json=payload, headers=headers)
    assert retry.json() == good.json()

    invalid = await client.post(
        f"/api/sessions/{session_id}/answers",
        json={
            "step_index": 0,
            "word_slug": "red",
            "attempt": 1,
            "client_answer_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert invalid.status_code == 400

    finished = await client.post(f"/api/sessions/{session_id}/finish", headers=headers)
    assert finished.status_code == 200
    assert finished.json()["coins_gained"] == 1

    after_finish = await client.post(
        f"/api/sessions/{session_id}/answers",
        json={
            "step_index": 5,
            "word_slug": steps[5]["word"]["slug"],
            "attempt": 1,
            "client_answer_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert after_finish.status_code == 409

    me = (await client.get("/api/me", headers=headers)).json()
    assert me["week"]["coins"] == 1 and me["week"]["study_days"] == ["2026-09-22"]

    foreign = await client.post(f"/api/sessions/{uuid.uuid4()}/finish", headers=headers)
    assert foreign.status_code == 404
