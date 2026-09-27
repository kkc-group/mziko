"""Sunday 20:00 Asia/Tbilisi: weekly report to every parent of every child."""

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core import clock
from app.core.db import get_sessionmaker
from app.services import report
from bot import keyboards, texts

log = logging.getLogger(__name__)


async def send_weekly_reports(bot: Bot) -> None:
    from app.services.parents import all_children

    now = clock.now()
    async with get_sessionmaker()() as db:
        for child in await all_children(db):
            r = await report.week_report(db, child, now)
            for parent in child.parents:
                try:
                    await bot.send_message(
                        parent.telegram_id,
                        texts.report_text(r),
                        reply_markup=keyboards.report_kb(r),
                    )
                except Exception:  # one blocked parent must not stop the others
                    log.exception("weekly report to %s failed", parent.telegram_id)
        await db.commit()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=clock.TBILISI)
    scheduler.add_job(
        send_weekly_reports,
        CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=clock.TBILISI),
        args=[bot],
        id="weekly_report",
        misfire_grace_time=3600,
        coalesce=True,
    )
    return scheduler
