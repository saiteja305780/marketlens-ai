"""Scheduled collection. Off unless SCHEDULER_ENABLED=true. One job per configured store, one run at a time per store (the advisory lock in ingest also guards this). Failures are logged and recorded as failed jobs; they never stop the scheduler."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.scrapers.registry import STORES, build_source
from app.services.ingest import IngestError, run_collection

logger = logging.getLogger(__name__)


def collect_source(name: str, factory=None, build=None):
    """Run one collection. Returns the job, or None if it was skipped or crashed."""
    factory = factory or get_session_factory()
    build = build or build_source
    try:
        scraper = build(name)
        job = run_collection(factory, STORES[name], lambda: scraper.collect(""))
    except IngestError as exc:  # source busy or disabled
        logger.warning("scheduled collection of %s skipped: %s", name, exc)
        return None
    except Exception as exc:
        logger.error("scheduled collection of %s crashed: %s", name, type(exc).__name__)
        return None
    logger.info("scheduled collection of %s finished: %s", name, job.status)
    return job



def build_scheduler() -> BackgroundScheduler:
    hours = get_settings().collect_interval_hours
    scheduler = BackgroundScheduler(timezone="UTC")
    for name in STORES:
        scheduler.add_job(collect_source, "interval", hours=hours, args=[name], id=f"collect-{name}",
                          max_instances=1, coalesce=True, misfire_grace_time=600, jitter=300)
    return scheduler


def start_scheduler_if_enabled() -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("scheduler is disabled (set SCHEDULER_ENABLED=true to enable)")
        return None
    scheduler = build_scheduler()
    scheduler.start()
    logger.warning("scheduler enabled: collecting %s every %s hours", sorted(STORES),
                   settings.collect_interval_hours)
    return scheduler

