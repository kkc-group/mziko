"""HTTP tests of /api/admin/*: the back office token and the parents overview."""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, CoinReason, Device, Parent, WordProgress
from app.services import coins, login_codes
from app.services.learning import LEARNED_STAGE
from tests.conftest import ADMIN_API_TOKEN, DAY1, Clock
from tests.helpers import at, play_day

ADMIN = {"Authorization": f"Bearer {ADMIN_API_TOKEN}"}


async def test_admin_token_is_required(client: AsyncClient) -> None:
    assert (await client.get("/api/admin/parents")).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert (await client.get("/api/admin/parents", headers=bad)).status_code == 401
    assert (await client.get("/api/admin/parents", headers=ADMIN)).status_code == 200


async def test_parents_overview_summarises_every_child(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    # Last week: 40 coins, never paid out. This week: one lesson played.
    last_week = await coins.get_or_create_week(db, child.id, DAY1 - timedelta(days=7))
    await coins.add_coins(db, child, last_week, 40, CoinReason.answer)
    await play_day(db, child, "colors", at(DAY1))
    childless = Parent(telegram_id=777_000 + child.id)
    db.add(childless)
    await db.flush()
    clock.moment = at(DAY1, 18)

    r = await client.get("/api/admin/parents", headers=ADMIN)
    assert r.status_code == 200, r.text
    rows = {row["telegram_id"]: row for row in r.json()}
    assert set(rows) >= {parent.telegram_id, childless.telegram_id}

    empty = rows[childless.telegram_id]
    assert empty["name"] is None and empty["photo_url"] is None
    assert empty["children"] == [] and empty["last_study_date"] is None

    row = rows[parent.telegram_id]
    assert row["name"] == "Папа" and row["last_study_date"] == str(DAY1)
    (summary,) = row["children"]
    assert summary["id"] == child.id and summary["name"] == "Сандро"
    # play_day skips ahead to "colors", so every word of the earlier lessons counts as learned.
    learned = await db.scalar(
        select(func.count()).where(
            WordProgress.child_id == child.id, WordProgress.stage >= LEARNED_STAGE
        )
    )
    assert learned and summary["learned_words"] == learned
    assert summary["last_study_date"] == str(DAY1)
    assert summary["this_week"]["coins"] > 0 and summary["cap_reached"] is False
    assert summary["last_week"]["coins"] == 40
    assert summary["last_week"]["status"] == "open" and summary["last_week"]["lari_due"] == 4.0


async def test_child_without_lessons_has_no_weeks(client: AsyncClient, parent: Parent) -> None:
    r = await client.get("/api/admin/parents", headers=ADMIN)
    row = next(row for row in r.json() if row["telegram_id"] == parent.telegram_id)
    (summary,) = row["children"]
    assert summary["this_week"] is None and summary["last_week"] is None
    assert summary["last_study_date"] is None and summary["learned_words"] == 0


async def test_parent_card_gathers_everything_per_child(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    await login_codes.ensure_code(db, child, at(DAY1))
    device = Device(child_id=child.id, token_hash="x" * 64, name="iPad")
    db.add(device)
    await play_day(db, child, "colors", at(DAY1))
    clock.moment = at(DAY1, 18)

    r = await client.get(f"/api/admin/parents/{parent.id}", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["telegram_id"] == parent.telegram_id and body["name"] == "Папа"
    (card,) = body["children"]
    assert card["name"] == "Сандро" and card["rate"] == 10 and card["cap_lari"] == 15
    assert card["code"] == f"{child.code_word}-{child.code_pin}"
    assert card["login_url"].endswith(f"/c/{card['code']}")

    topics = {t["slug"]: t for t in card["topics"]}
    colors = topics["colors"]
    assert colors["started"] is True and colors["total"] > 0
    # Earlier lessons were skipped as learned; the sum matches the per-topic counts.
    assert card["learned_words"] == sum(t["learned"] for t in card["topics"])
    assert card["learned_words"] > 0
    untouched = next(t for t in card["topics"] if not t["started"])
    assert untouched["learned"] == 0

    assert card["study_days"] == [{"day": str(DAY1), "finished": True}]
    assert card["first_try_pct"] == 100
    assert card["weeks"][0]["coins"] > 0 and card["weeks"][0]["status"] == "open"
    (dev,) = card["devices"]
    assert dev["name"] == "iPad" and dev["revoked_at"] is None


async def test_parent_card_for_a_fresh_child_and_a_stranger(
    client: AsyncClient, parent: Parent
) -> None:
    r = await client.get(f"/api/admin/parents/{parent.id}", headers=ADMIN)
    (card,) = r.json()["children"]
    assert card["code"] is None and card["login_url"] is None
    assert card["study_days"] == [] and card["first_try_pct"] is None
    assert card["weeks"] == [] and card["devices"] == []
    assert card["learned_words"] == 0 and not any(t["started"] for t in card["topics"])

    assert (await client.get("/api/admin/parents/0", headers=ADMIN)).status_code == 404
    assert (await client.get(f"/api/admin/parents/{parent.id}")).status_code == 401
