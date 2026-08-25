from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import get_settings
from .runner import run_scout

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _scheduled_job():
    settings = get_settings()
    logger.info("Starting scheduled scout for geo=%s", settings.scout_geo)
    await run_scout()


def start_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    if not scheduler.running:
        scheduler.add_job(
            _scheduled_job,
            trigger="cron",
            hour=settings.scout_cron_hour,
            minute=settings.scout_cron_minute,
            id="nightly_scout",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(
            "Scheduler started: daily at %02d:%02d",
            settings.scout_cron_hour,
            settings.scout_cron_minute,
        )
    return scheduler


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
