from datetime import timedelta
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.core.config import get_settings
from app.main import create_app
from app.schemas.listing import Availability, ScrapedListing
from app.scrapers.base import ScrapeResult
from app.scrapers.registry import STORES
from app.services.ingest import LOCK_NAMESPACE, lock_key
from app.services.scheduler import build_scheduler, collect_source, start_scheduler_if_enabled


@pytest.fixture(autouse=True)
def fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeScraper:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def collect(self, query):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        r = ScrapeResult(source="boat")
        r.listings.append(ScrapedListing(
            source="boat", source_listing_id="v1", title="Test Earbuds",
            url="https://example.test/p?variant=v1", price=D("999"), currency="INR",
            availability=Availability.IN_STOCK))
        return r


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    assert start_scheduler_if_enabled() is None


def test_one_single_instance_job_per_store(monkeypatch):
    monkeypatch.setenv("COLLECT_INTERVAL_HOURS", "6")
    jobs = build_scheduler().get_jobs()  # never started: no thread, no requests
    assert sorted(j.id for j in jobs) == sorted(f"collect-{n}" for n, c in STORES.items() if c.status == "approved")
    assert all(j.max_instances == 1 for j in jobs)
    assert all(j.trigger.interval == timedelta(hours=6) for j in jobs)


def test_interval_below_one_hour_is_refused(monkeypatch):
    monkeypatch.setenv("COLLECT_INTERVAL_HOURS", "0.5")
    with pytest.raises(ValidationError):
        get_settings()


def test_collect_source_stores_data(session_factory):
    job = collect_source("boat", session_factory, lambda n: FakeScraper())
    assert job.status == "succeeded"


def test_failed_collection_is_recorded_not_raised(session_factory):
    job = collect_source("boat", session_factory, lambda n: FakeScraper(fail=True))
    assert job.status == "failed"


def test_busy_source_is_skipped_without_fetching(session_factory):
    holder = session_factory()
    assert holder.scalar(text("SELECT pg_try_advisory_xact_lock(:ns, :key)"),
                         {"ns": LOCK_NAMESPACE, "key": lock_key("boat")})
    scraper = FakeScraper()
    try:
        assert collect_source("boat", session_factory, lambda n: scraper) is None
        assert scraper.calls == 0
    finally:
        holder.close()


def test_app_starts_with_lifespan_and_scheduler_off(monkeypatch):
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200


def test_blocked_source_is_never_scheduled(monkeypatch):
    monkeypatch.setenv("COLLECT_INTERVAL_HOURS", "6")
    ids = [j.id for j in build_scheduler().get_jobs()]
    assert "collect-boat" not in ids
    assert "collect-noise" in ids
