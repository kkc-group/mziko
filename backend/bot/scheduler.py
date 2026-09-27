"""Sunday 20:00 Asia/Tbilisi: weekly report to every parent of every child."""

import logging
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot import keyboards, texts
from bot.api import ParentApi

log = logging.getLogger(__name__)


async def send_weekly_reports(bot: Bot, api: ParentApi) -> None:
    for due in await api.reports_due():
        for telegram_id in due.telegram_ids:
            try:
                await bot.send_message(
                    telegram_id,
                    texts.report_text(due.report),
                    reply_markup=keyboards.report_kb(due.report),
                )
            except Exception:  # one blocked parent must not stop the others
                log.exception("weekly report to %s failed", telegram_id)


def setup_scheduler(bot: Bot, api: ParentApi, timezone: str) -> AsyncIOScheduler:
    tz = ZoneInfo(timezone)
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(
        send_weekly_reports,
        CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=tz),
        args=[bot, api],
        id="weekly_report",
        misfire_grace_time=3600,
        coalesce=True,
    )
    return scheduler
