"""HTTP tests of /api/parent/*: the bot's token, the parent boundary, report and payout."""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Child, CoinReason, Parent
from app.services import coins
from tests.conftest import BOT_API_TOKEN, DAY1, Clock
from tests.helpers import at, play_day


def bot_headers(parent: Parent | int) -> dict[str, str]:
    telegram_id = parent if isinstance(parent, int) else parent.telegram_id
    return {"Authorization": f"Bearer {BOT_API_TOKEN}", "X-Telegram-Id": str(telegram_id)}


async def test_bot_token_and_parent_header_are_required(
    client: AsyncClient, parent: Parent, child: Child
) -> None:
    url = f"/api/parent/children/{child.id}/report"
    assert (await client.get(url)).status_code == 401
    bad = {"Authorization": "Bearer nope", "X-Telegram-Id": str(parent.telegram_id)}
    assert (await client.get(url, headers=bad)).status_code == 401
    no_parent = {"Authorization": f"Bearer {BOT_API_TOKEN}"}
    assert (await client.get(url, headers=no_parent)).status_code == 400
    assert (await client.get(url, headers=bot_headers(999_999_999))).status_code == 403
    assert (await client.get(url, headers=bot_headers(parent))).status_code == 200


async def test_report_and_week_stay_within_the_parent_link(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    await play_day(db, child, "colors", at(DAY1))
    clock.moment = at(DAY1, 18)

    r = await client.get(f"/api/parent/children/{child.id}/report", headers=bot_headers(parent))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["child"] == {
        "id": child.id,
        "name": "Сандро",
        "rate": 10,
        "cap_lari": 15,
        "show_hint": True,
    }
    assert body["days_studied"] == 1
    assert body["week"]["status"] == "open" and body["week"]["coins"] > 0
    assert body["week"]["lari_due"] == float(coins.lari_for(body["week"]["coins"], 10, 15))
    assert body["week"]["week_end"] == str(DAY1 + timedelta(days=6 - DAY1.weekday()))
    assert body["unpaid_past"] == []

    week_id = body["week"]["id"]
    same = await client.get(f"/api/parent/weeks/{week_id}", headers=bot_headers(parent))
    assert same.status_code == 200 and same.json()["week"]["id"] == week_id

    stranger = Parent(telegram_id=555_000 + child.id)
    db.add(stranger)
    await db.flush()
    for url in (f"/api/parent/children/{child.id}/report", f"/api/parent/weeks/{week_id}"):
        assert (await client.get(url, headers=bot_headers(stranger))).status_code == 404
    assert (
        await client.post(f"/api/parent/weeks/{week_id}/pay", headers=bot_headers(stranger))
    ).status_code == 404
    assert (await client.get("/api/parent/weeks/0", headers=bot_headers(parent))).status_code == 404


async def test_pay_closes_the_week_once(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    week = await coins.get_or_create_week(db, child.id, DAY1)
    await coins.add_coins(db, child, week, 23, CoinReason.answer)
    clock.moment = at(DAY1 + timedelta(days=6), 20)

    paid = await client.post(f"/api/parent/weeks/{week.id}/pay", headers=bot_headers(parent))
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["already_paid"] is False
    assert body["report"]["week"]["status"] == "paid"
    assert body["report"]["week"]["lari_paid"] == 2.3
    assert body["report"]["week"]["paid_at"] is not None

    again = await client.post(f"/api/parent/weeks/{week.id}/pay", headers=bot_headers(parent))
    assert again.status_code == 200
    assert again.json()["already_paid"] is True
    assert again.json()["report"]["week"]["lari_paid"] == 2.3

    # The next week's report lists nothing as unpaid: the payout closed it.
    clock.moment = at(DAY1 + timedelta(days=7), 12)
    nxt = await client.get(f"/api/parent/children/{child.id}/report", headers=bot_headers(parent))
    assert nxt.json()["unpaid_past"] == []


async def test_unpaid_previous_week_is_listed_with_its_due(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    week = await coins.get_or_create_week(db, child.id, DAY1)
    await coins.add_coins(db, child, week, 40, CoinReason.answer)
    clock.moment = at(DAY1 + timedelta(days=7), 12)

    r = await client.get(f"/api/parent/children/{child.id}/report", headers=bot_headers(parent))
    past = r.json()["unpaid_past"]
    assert [p["id"] for p in past] == [week.id]
    assert past[0]["coins"] == 40 and past[0]["lari_due"] == 4.0 and past[0]["status"] == "open"


async def test_children_list_and_create(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child
) -> None:
    blank = await client.post(
        "/api/parent/children", json={"name": "   "}, headers=bot_headers(parent)
    )
    assert blank.status_code == 422

    created = await client.post(
        "/api/parent/children", json={"name": "  Тако  "}, headers=bot_headers(parent)
    )
    assert created.status_code == 200, created.text
    assert created.json()["name"] == "Тако"
    new_id = created.json()["id"]

    listed = await client.get("/api/parent/children", headers=bot_headers(parent))
    assert {c["id"] for c in listed.json()} == {child.id, new_id}

    stranger = Parent(telegram_id=555_100 + child.id)
    db.add(stranger)
    await db.flush()
    stranger_list = await client.get("/api/parent/children", headers=bot_headers(stranger))
    assert stranger_list.json() == []


async def test_progress_shows_learned_words_and_stays_within_the_parent_link(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child
) -> None:
    await play_day(db, child, "colors", at(DAY1))

    r = await client.get(f"/api/parent/children/{child.id}/progress", headers=bot_headers(parent))
    assert r.status_code == 200, r.text
    colors = next(t for t in r.json()["topics"] if t["slug"] == "colors")
    assert colors["learned"] == 0
    assert any(w["stage"] == 1 for w in colors["words"])

    stranger = Parent(telegram_id=555_200 + child.id)
    db.add(stranger)
    await db.flush()
    assert (
        await client.get(f"/api/parent/children/{child.id}/progress", headers=bot_headers(stranger))
    ).status_code == 404


async def test_settings_are_validated_and_saved(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child
) -> None:
    url = f"/api/parent/children/{child.id}/settings"
    ok = await client.patch(url, json={"rate": 15}, headers=bot_headers(parent))
    assert ok.status_code == 200, ok.text
    assert ok.json()["rate"] == 15

    bad = await client.patch(url, json={"rate": 7}, headers=bot_headers(parent))
    assert bad.status_code == 422

    hint = await client.patch(url, json={"show_hint": False}, headers=bot_headers(parent))
    assert hint.status_code == 200
    assert hint.json()["show_hint"] is False

    stranger = Parent(telegram_id=555_300 + child.id)
    db.add(stranger)
    await db.flush()
    assert (
        await client.patch(url, json={"rate": 20}, headers=bot_headers(stranger))
    ).status_code == 404


async def test_child_code_is_issued_once_and_rotated(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child
) -> None:
    url = f"/api/parent/children/{child.id}/code"
    first = await client.get(url, headers=bot_headers(parent))
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["code"] == f"{body['word']}-{body['pin']}"
    assert body["url"].startswith(get_settings().public_url)
    assert "/c/" in body["url"]

    again = await client.get(url, headers=bot_headers(parent))
    assert again.json()["word"] == body["word"]
    assert again.json()["pin"] == body["pin"]

    login = await client.post("/api/login", json={"word": body["word"], "pin": body["pin"]})
    assert login.status_code == 200, login.text
    assert login.json()["child"]["id"] == child.id

    old_pin = body["pin"]
    rotated = await client.post(f"{url}/rotate", headers=bot_headers(parent))
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["word"] == body["word"]
    new_pin = rotated.json()["pin"]
    if new_pin == old_pin:  # 1-in-10000 collision: rotate once more
        rotated = await client.post(f"{url}/rotate", headers=bot_headers(parent))
        new_pin = rotated.json()["pin"]

    assert (
        await client.post("/api/login", json={"word": body["word"], "pin": old_pin})
    ).status_code == 401
    new_login = await client.post("/api/login", json={"word": body["word"], "pin": new_pin})
    assert new_login.status_code == 200
    assert new_login.json()["child"]["id"] == child.id

    stranger = Parent(telegram_id=555_500 + child.id)
    db.add(stranger)
    await db.flush()
    assert (await client.get(url, headers=bot_headers(stranger))).status_code == 404
    assert (await client.post(f"{url}/rotate", headers=bot_headers(stranger))).status_code == 404


async def test_devices_list_and_delete(client: AsyncClient, parent: Parent, child: Child) -> None:
    devices_url = f"/api/parent/children/{child.id}/devices"

    async def log_in(child_id: int) -> None:
        code = (
            await client.get(f"/api/parent/children/{child_id}/code", headers=bot_headers(parent))
        ).json()
        logged = await client.post("/api/login", json={"word": code["word"], "pin": code["pin"]})
        assert logged.status_code == 200, logged.text

    await log_in(child.id)
    listed = await client.get(devices_url, headers=bot_headers(parent))
    assert listed.status_code == 200, listed.text
    (device,) = listed.json()

    deleted = await client.delete(f"{devices_url}/{device['id']}", headers=bot_headers(parent))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == []

    again = await client.delete(f"{devices_url}/{device['id']}", headers=bot_headers(parent))
    assert again.status_code == 404

    other_child = (
        await client.post(
            "/api/parent/children", json={"name": "Другой"}, headers=bot_headers(parent)
        )
    ).json()
    await log_in(other_child["id"])
    (other_device,) = (
        await client.get(
            f"/api/parent/children/{other_child['id']}/devices", headers=bot_headers(parent)
        )
    ).json()

    assert (
        await client.delete(f"{devices_url}/{other_device['id']}", headers=bot_headers(parent))
    ).status_code == 404


async def test_reports_due_lists_every_child_with_its_parents(
    client: AsyncClient, parent: Parent, child: Child
) -> None:
    url = "/api/parent/reports/due"
    assert (await client.get(url)).status_code == 401

    r = await client.get(url, headers={"Authorization": f"Bearer {BOT_API_TOKEN}"})
    assert r.status_code == 200, r.text

    ours = next(d for d in r.json() if d["report"]["child"]["id"] == child.id)
    assert ours["telegram_ids"] == [parent.telegram_id]


async def test_reset_progress_forgets_learning_but_keeps_code_and_devices(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    await play_day(db, child, "colors", at(DAY1))
    clock.moment = at(DAY1, 18)
    headers = bot_headers(parent)
    code = (await client.get(f"/api/parent/children/{child.id}/code", headers=headers)).json()
    assert (
        await client.post("/api/login", json={"word": code["word"], "pin": code["pin"]})
    ).status_code == 200
    before = (await client.get(f"/api/parent/children/{child.id}/report", headers=headers)).json()
    assert before["days_studied"] == 1 and before["week"]["coins"] > 0

    reset = await client.post(f"/api/parent/children/{child.id}/reset", headers=headers)
    assert reset.status_code == 200, reset.text

    after = (await client.get(f"/api/parent/children/{child.id}/report", headers=headers)).json()
    assert after["days_studied"] == 0 and after["week"]["coins"] == 0
    progress = (
        await client.get(f"/api/parent/children/{child.id}/progress", headers=headers)
    ).json()
    assert all(t["learned"] == 0 for t in progress["topics"])
    same_code = (await client.get(f"/api/parent/children/{child.id}/code", headers=headers)).json()
    assert same_code["code"] == code["code"]
    assert (
        len((await client.get(f"/api/parent/children/{child.id}/devices", headers=headers)).json())
        == 1
    )

    stranger = Parent(telegram_id=666_000 + child.id)
    db.add(stranger)
    await db.flush()
    assert (
        await client.post(f"/api/parent/children/{child.id}/reset", headers=bot_headers(stranger))
    ).status_code == 404


async def test_detach_and_attach_by_code(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child
) -> None:
    headers = bot_headers(parent)
    code = (await client.get(f"/api/parent/children/{child.id}/code", headers=headers)).json()

    detached = await client.delete(f"/api/parent/children/{child.id}", headers=headers)
    assert detached.status_code == 200, detached.text
    assert detached.json() == []
    assert (
        await client.get(f"/api/parent/children/{child.id}/report", headers=headers)
    ).status_code == 404
    assert (
        await client.delete(f"/api/parent/children/{child.id}", headers=headers)
    ).status_code == 404

    other = Parent(telegram_id=777_000 + child.id)
    db.add(other)
    await db.flush()
    attached = await client.post(
        "/api/parent/children/attach",
        json={"code": code["code"].lower()},
        headers=bot_headers(other),
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["id"] == child.id
    twice = await client.post(
        "/api/parent/children/attach", json={"code": code["code"]}, headers=bot_headers(other)
    )
    assert twice.status_code == 200
    assert [
        c["id"]
        for c in (await client.get("/api/parent/children", headers=bot_headers(other))).json()
    ] == [child.id]

    wrong_pin = "0000" if code["pin"] != "0000" else "1111"
    missing = await client.post(
        "/api/parent/children/attach", json={"code": f"{code['word']}-{wrong_pin}"}, headers=headers
    )
    assert missing.status_code == 404
    malformed = await client.post(
        "/api/parent/children/attach", json={"code": "Сандро"}, headers=headers
    )
    assert malformed.status_code == 422


async def test_me_and_register_drive_the_wizard(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child
) -> None:
    newcomer = bot_headers(900_000 + child.id)
    assert (await client.get("/api/parent/me")).status_code == 401
    assert (await client.get("/api/parent/me", headers=newcomer)).status_code == 404
    # Registration is the only parent route a stranger may call.
    assert (await client.get("/api/parent/children", headers=newcomer)).status_code == 403

    blank = await client.put("/api/parent/me", json={"name": "  "}, headers=newcomer)
    assert blank.status_code == 422
    long = await client.put("/api/parent/me", json={"name": "x" * 101}, headers=newcomer)
    assert long.status_code == 422

    made = await client.put("/api/parent/me", json={"name": " Нино Церетели "}, headers=newcomer)
    assert made.status_code == 200, made.text
    assert made.json() == {
        "telegram_id": 900_000 + child.id,
        "name": "Нино Церетели",
        "children": [],
    }
    assert (await client.get("/api/parent/children", headers=newcomer)).json() == []

    renamed = await client.put("/api/parent/me", json={"name": "Нино"}, headers=newcomer)
    assert renamed.json()["name"] == "Нино"
    assert (await client.get("/api/parent/me", headers=newcomer)).json()["name"] == "Нино"

    mine = (await client.get("/api/parent/me", headers=bot_headers(parent))).json()
    assert mine["name"] == "Папа" and [c["id"] for c in mine["children"]] == [child.id]

    # A child's name is capped like the parent's, instead of failing inside the database.
    too_long = await client.post(
        "/api/parent/children", json={"name": "y" * 101}, headers=bot_headers(parent)
    )
    assert too_long.status_code == 422
