"""
Periodic scheduler — re-scrapes web sources on their configured frequency.
Backed by APScheduler in-process. Started/stopped from server lifespan.
"""
from datetime import datetime, timezone, timedelta
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import web_sources_col
from app.routes.web_source_routes import _scrape_source

_scheduler: AsyncIOScheduler | None = None


def _due(last_scraped_at, frequency: str) -> bool:
    if not last_scraped_at:
        return True
    try:
        last = datetime.fromisoformat(last_scraped_at) if isinstance(last_scraped_at, str) else last_scraped_at
    except Exception:
        return True
    now = datetime.now(timezone.utc)
    delta = {
        "daily": timedelta(days=1),
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
    }.get(frequency, timedelta(days=7))
    return (now - last) >= delta


async def _tick():
    try:
        cursor = web_sources_col().find({"is_active": True}, {"_id": 0})
        n_scraped = 0
        async for ws in cursor:
            if not _due(ws.get("last_scraped_at"), ws.get("scrape_frequency", "weekly")):
                continue
            try:
                logger.info(f"[scheduler] scraping {ws['url']}")
                await _scrape_source(ws["id"])
                n_scraped += 1
            except Exception as e:
                logger.warning(f"[scheduler] scrape failed for {ws.get('url')}: {e}")
        if n_scraped:
            logger.info(f"[scheduler] completed: {n_scraped} sources scraped")
    except Exception as e:
        logger.error(f"[scheduler] tick error: {e}")


def start_scheduler():
    global _scheduler
    if _scheduler:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    # Run hourly — each source has its own due-check
    _scheduler.add_job(_tick, "interval", hours=1, id="web_source_rescrape", next_run_time=None)
    _scheduler.start()
    logger.info("Scheduler started (web-source re-scrape every hour, per-source due-check)")


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
