from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.schemas.listing import Availability, ScrapedListing
from app.scrapers.base import ScrapeResult
from app.scrapers.registry import StoreConfig
from app.services.ingest import LOCK_NAMESPACE, SourceBusyError, lock_key, run_collection

CONFIG = StoreConfig("boat", "https://example.test", "INR", "candidate")


def result():
    r = ScrapeResult(source="boat")
    r.listings.append(ScrapedListing(
        source="boat", source_listing_id="v1", title="Test Earbuds",
        url="https://example.test/products/x?variant=v1", price=D("999"),
        currency="INR", availability=Availability.IN_STOCK))
    return r


def test_run_is_refused_while_another_holds_the_lock(session_factory):
    holder = session_factory()
    assert holder.scalar(text("SELECT pg_try_advisory_xact_lock(:ns, :key)"),
                         {"ns": LOCK_NAMESPACE, "key": lock_key("boat")})
    try:
        def must_not_run():
            raise AssertionError("fetch must not run while the source is locked")
        with pytest.raises(SourceBusyError):
            run_collection(session_factory, CONFIG, must_not_run)
    finally:
        holder.close()


def test_lock_is_released_after_a_run(session_factory):
    assert run_collection(session_factory, CONFIG, result).status == "succeeded"
    assert run_collection(session_factory, CONFIG, result).status == "succeeded"