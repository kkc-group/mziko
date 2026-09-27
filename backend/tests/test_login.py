"""Child login by the permanent code WORD-1234: attempts, the hour lock, parent re-issue."""

from datetime import timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child
from app.services import login_codes, pairing
from tests.conftest import Clock


async def with_code(db: AsyncSession, child: Child, clock: Clock) -> tuple[str, str]:
    await login_codes.ensure_code(db, child, clock.moment)
    assert child.code_word in login_codes.WORDS
    assert child.code_pin is not None and len(child.code_pin) == 4 and child.code_pin.isdigit()
    return child.code_word, child.code_pin


async def test_correct_code_logs_in_any_number_of_devices(
    db: AsyncSession, client: AsyncClient, child: Child, clock: Clock
) -> None:
    word, pin = await with_code(db, child, clock)

    first = await client.post(
        "/api/login", json={"word": word.lower(), "pin": pin, "device_name": "iPad"}
    )
    assert first.status_code == 200, first.text
    assert first.json()["child"] == {"id": child.id, "name": "Сандро"}
    headers = {"Authorization": f"Bearer {first.json()['device_token']}"}
    assert (await client.get("/api/me", headers=headers)).status_code == 200

    second = await client.post("/api/login", json={"word": word, "pin": pin})
    assert second.status_code == 200
    assert second.json()["device_token"] != first.json()["device_token"]
    assert len(await pairing.active_devices(db, child.id)) == 2

    assert (await client.get("/api/login/status")).json() == {
        "locked_until": None,
        "word": None,
        "pin_rotated": False,
    }


async def test_three_misses_lock_the_address_for_an_hour(
    db: AsyncSession, client: AsyncClient, child: Child, clock: Clock
) -> None:
    word, pin = await with_code(db, child, clock)
    wrong_pin = "0000" if pin != "0000" else "1111"

    miss = await client.post("/api/login", json={"word": word, "pin": wrong_pin})
    assert miss.status_code == 401
    assert miss.json()["detail"] == {"error": "wrong_code", "attempts_left": 2}

    # A word that exists for nobody costs an attempt too: no guessing the word either.
    miss = await client.post("/api/login", json={"word": "XXXX", "pin": pin})
    assert miss.json()["detail"] == {"error": "wrong_code", "attempts_left": 1}

    locked_until = (clock.moment + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    third = await client.post("/api/login", json={"word": word, "pin": wrong_pin})
    assert third.status_code == 423
    assert third.json()["detail"] == {"error": "locked", "locked_until": locked_until}

    # Even the right code waits while the lock lasts.
    clock.moment += timedelta(minutes=30)
    right = await client.post("/api/login", json={"word": word, "pin": pin})
    assert right.status_code == 423

    status = (await client.get("/api/login/status")).json()
    assert status == {"locked_until": locked_until, "word": word, "pin_rotated": False}

    clock.moment += timedelta(minutes=31)
    status = (await client.get("/api/login/status")).json()
    assert status == {"locked_until": None, "word": word, "pin_rotated": False}
    assert (await client.post("/api/login", json={"word": word, "pin": pin})).status_code == 200


async def test_a_success_resets_the_miss_count(
    db: AsyncSession, client: AsyncClient, child: Child, clock: Clock
) -> None:
    word, pin = await with_code(db, child, clock)
    wrong_pin = "0000" if pin != "0000" else "1111"
    for _ in range(2):
        assert (
            await client.post("/api/login", json={"word": word, "pin": wrong_pin})
        ).status_code == 401
    assert (await client.post("/api/login", json={"word": word, "pin": pin})).status_code == 200
    miss = await client.post("/api/login", json={"word": word, "pin": wrong_pin})
    assert miss.json()["detail"]["attempts_left"] == 2


async def test_parent_reissuing_the_pin_lifts_the_lock_early(
    db: AsyncSession, client: AsyncClient, child: Child, clock: Clock
) -> None:
    word, pin = await with_code(db, child, clock)
    wrong_pin = "0000" if pin != "0000" else "1111"
    for _ in range(3):
        await client.post("/api/login", json={"word": word, "pin": wrong_pin})
    assert (await client.get("/api/login/status")).json()["locked_until"] is not None

    clock.moment += timedelta(minutes=5)
    await login_codes.rotate_pin(db, child, clock.moment)
    assert child.code_word == word and child.code_pin != pin

    status = (await client.get("/api/login/status")).json()
    assert status == {"locked_until": None, "word": word, "pin_rotated": True}
    assert (await client.post("/api/login", json={"word": word, "pin": pin})).status_code == 401
    assert (
        await client.post("/api/login", json={"word": word, "pin": child.code_pin})
    ).status_code == 200


async def test_reissuing_another_childs_pin_changes_nothing(
    db: AsyncSession, client: AsyncClient, child: Child, clock: Clock
) -> None:
    word, pin = await with_code(db, child, clock)
    other = Child(name="Нино")
    db.add(other)
    await db.flush()
    await login_codes.ensure_code(db, other, clock.moment)
    assert other.code_word != word

    wrong_pin = "9999" if pin != "9999" else "8888"
    for _ in range(3):
        await client.post("/api/login", json={"word": word, "pin": wrong_pin})
    await login_codes.rotate_pin(db, other, clock.moment + timedelta(minutes=1))

    status = (await client.get("/api/login/status")).json()
    assert status["locked_until"] is not None and status["pin_rotated"] is False


async def test_login_body_is_validated(client: AsyncClient) -> None:
    bad_pin = await client.post("/api/login", json={"word": "LOMI", "pin": "12a4"})
    bad_word = await client.post("/api/login", json={"word": "LOMIS", "pin": "1234"})
    assert (bad_pin.status_code, bad_word.status_code) == (422, 422)


async def test_misses_are_recorded_even_though_the_request_fails(
    database_url: str, clock: Clock
) -> None:
    """A miss ends in an error response; it must still be committed (real session per request)."""
    from app.api.deps import get_now
    from app.core.db import get_sessionmaker
    from app.main import create_app
    from app.models import LoginLock

    app = create_app()
    app.dependency_overrides[get_now] = lambda: clock.moment
    sessions = get_sessionmaker()
    async with sessions() as db:
        child = Child(name="Лука")
        db.add(child)
        await db.flush()
        await login_codes.ensure_code(db, child, clock.moment)
        word, pin = child.code_word, child.code_pin
        child_id = child.id
        await db.commit()
    assert word is not None and pin is not None
    wrong_pin = "0000" if pin != "0000" else "1111"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post("/api/login", json={"word": word, "pin": wrong_pin})
            second = await client.post("/api/login", json={"word": word, "pin": wrong_pin})
        assert first.json()["detail"]["attempts_left"] == 2
        assert second.json()["detail"]["attempts_left"] == 1
    finally:
        async with sessions() as db:
            await db.execute(delete(LoginLock))
            await db.execute(delete(Child).where(Child.id == child_id))
            await db.commit()
