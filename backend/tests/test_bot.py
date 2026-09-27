"""The bot side: its API client against the real app, its texts, and the import boundary."""

import re
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_now
from app.main import create_app
from app.models import Child, CoinReason, Parent
from app.services import coins
from bot import keyboards, texts
from bot.api import ApiError, ParentApi, make_client
from tests.conftest import BOT_API_TOKEN, DAY1, Clock
from tests.helpers import at, play_day

BOT_DIR = Path(__file__).resolve().parents[1] / "bot"

# What the bot may import from the app: the wire contract and process settings, nothing else.
FORBIDDEN_IMPORTS = re.compile(
    r"^\s*(from|import)\s+(app\.models|app\.services|app\.core\.db|app\.seed|sqlalchemy|alembic)\b",
    re.MULTILINE,
)


def test_bot_never_imports_the_database_side() -> None:
    offenders = {
        path.name: FORBIDDEN_IMPORTS.findall(path.read_text(encoding="utf-8"))
        for path in BOT_DIR.glob("*.py")
    }
    assert {name: hits for name, hits in offenders.items() if hits} == {}


def api_for(db: AsyncSession, clock: Clock, telegram_id: int | None) -> ParentApi:
    """The bot's client wired to the app in-process, sharing the test's session and clock."""
    app = create_app()

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_now] = lambda: clock.moment
    client = make_client("http://test", BOT_API_TOKEN)
    client._transport = httpx.ASGITransport(app=app)
    return ParentApi(client, telegram_id)


async def test_client_round_trip_children_report_and_payout(
    db: AsyncSession, parent: Parent, child: Child, clock: Clock
) -> None:
    api = api_for(db, clock, parent.telegram_id)
    await play_day(db, child, "colors", at(DAY1))
    clock.moment = at(DAY1, 18)

    children = await api.children()
    assert [c.name for c in children] == ["Сандро"]
    assert await api.child(child.id) == children[0]
    assert await api.child(child.id + 1_000_000) is None

    r = await api.report(child.id)
    assert r.days_studied == 1 and r.week.status == "open"
    assert "Выдайте наличные" in texts.report_text(r)
    assert keyboards.report_kb(r).inline_keyboard[0][0].callback_data == f"pay:{r.week.id}"

    clock.moment = at(DAY1 + timedelta(days=6), 20)
    paid = await api.pay(r.week.id)
    assert paid.already_paid is False and paid.report.week.status == "paid"
    assert "✅ Выплачено" in texts.report_text(paid.report)
    assert (await api.pay(r.week.id)).already_paid is True

    updated = await api.update_settings(child.id, rate=20, show_hint=False)
    assert (updated.rate, updated.show_hint) == (20, False)
    # Hint is off now, so the toggle button offers to turn it on.
    hint_button = keyboards.settings_kb(updated).inline_keyboard[-1][0]
    assert hint_button.callback_data == f"set:{child.id}:hint:1"

    progress = await api.progress(child.id)
    assert "●○○ წითელი · красный" in texts.progress_text(progress.child, progress.topics)


async def test_client_maps_api_errors(
    db: AsyncSession, parent: Parent, child: Child, clock: Clock
) -> None:
    stranger = api_for(db, clock, 424_242)
    try:
        await stranger.children()
    except ApiError as exc:
        assert exc.status == 403
    else:
        raise AssertionError("a stranger must get 403")

    mine = api_for(db, clock, parent.telegram_id)
    try:
        await mine.report(child.id + 1_000_000)
    except ApiError as exc:
        assert exc.status == 404
    else:
        raise AssertionError("someone else's child must look missing")

    unbound = api_for(db, clock, None)
    week = await coins.get_or_create_week(db, child.id, DAY1)
    await coins.add_coins(db, child, week, 5, CoinReason.answer)
    due = await unbound.reports_due()
    ours = next(d for d in due if d.report.child.id == child.id)
    assert ours.telegram_ids == [parent.telegram_id] and ours.report.week.coins == 5
