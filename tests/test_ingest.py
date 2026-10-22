"""Integration tests for the ingestion service (need TEST_DATABASE_URL)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.database.models import DataSource, PriceObservation, ProductListing, ScrapeJob
from app.scrapers.base import RejectedRecord, ScrapeResult, SourceFetchError
from app.scrapers.registry import StoreConfig
from app.schemas.listing import Availability, ScrapedListing
from app.services.ingest import IngestError, SourceDisabledError, run_collection

pytestmark = pytest.mark.integration
CONFIG = StoreConfig("s", "https://shop.example.com", "INR", "fixture")
T0 = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)


def make(i="1", price="100.00", avail=Availability.IN_STOCK, list_price=None, at=T0, title="Item"):
    has_money = price is not None or list_price is not None
    return ScrapedListing(
        source="s", source_listing_id=i, title=title, url=f"https://shop.example.com/p/{i}",
        price=Decimal(price) if price is not None else None,
        currency="INR" if has_money else None, availability=avail,
        list_price=Decimal(list_price) if list_price else None, collected_at=at)


def run(factory, listings, rejected=(), excluded=()):
    result = ScrapeResult("s", listings=list(listings), rejected=list(rejected), excluded=list(excluded))
    return run_collection(factory, CONFIG, lambda: result)


def count(factory, model):
    with factory() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_first_run_stores_listings_observations_and_job(session_factory):
    job = run(session_factory, [make("1"), make("2", price="250.50")])
    assert job.status == "succeeded"
    assert (job.discovered, job.accepted, job.observations_written) == (2, 2, 2)
    assert count(session_factory, ProductListing) == 2
    assert count(session_factory, PriceObservation) == 2


def test_identical_second_run_adds_no_observation_but_updates_last_seen(session_factory):
    run(session_factory, [make("1")])
    with session_factory() as s:
        first_seen = s.scalar(select(ProductListing.last_seen_at))
    job = run(session_factory, [make("1", at=T0 + timedelta(hours=1))])
    assert job.observations_written == 0
    assert count(session_factory, PriceObservation) == 1
    with session_factory() as s:
        assert s.scalar(select(ProductListing.last_seen_at)) > first_seen


def test_price_change_appends_history_instead_of_overwriting(session_factory):
    run(session_factory, [make("1", price="100.00")])
    run(session_factory, [make("1", price="90.00", at=T0 + timedelta(days=1))])
    with session_factory() as s:
        prices = list(s.scalars(select(PriceObservation.price).order_by(PriceObservation.observed_at)))
    assert prices == [Decimal("100.00"), Decimal("90.00")]


def test_availability_only_change_is_recorded(session_factory):
    run(session_factory, [make("1")])
    job = run(session_factory, [make("1", avail=Availability.OUT_OF_STOCK, at=T0 + timedelta(hours=2))])
    assert job.observations_written == 1


def test_sub_cent_price_does_not_create_repeat_observations(session_factory):
    run(session_factory, [make("1", price="1499.005")])
    job = run(session_factory, [make("1", price="1499.005", at=T0 + timedelta(hours=1))])
    assert job.observations_written == 0
    assert count(session_factory, PriceObservation) == 1


def test_failed_fetch_is_recorded_and_stores_nothing(session_factory):
    run(session_factory, [make("1")])

    def boom():
        raise SourceFetchError("HTTP 503 from shop.example.com")

    job = run_collection(session_factory, CONFIG, boom)
    assert job.status == "failed" and job.error_type == "SourceFetchError"
    assert job.observations_written == 0
    assert count(session_factory, ProductListing) == 1  # nothing was deleted or "emptied"


def test_degraded_result_is_failed_and_stores_nothing(session_factory):
    bad = [RejectedRecord(str(n), "price: Input should be greater than 0") for n in range(3)]
    job = run(session_factory, [make("1")], rejected=bad)
    assert job.status == "failed" and job.degraded is True
    assert job.error_type == "DegradedResultError"
    assert (job.accepted, job.rejected) == (1, 3)
    assert count(session_factory, ProductListing) == 0


def test_rejected_and_excluded_counts_are_stored(session_factory):
    job = run(session_factory, [make("1"), make("2"), make("3")],
              rejected=[RejectedRecord("9", "bad")], excluded=[RejectedRecord("8", "test item")])
    assert (job.discovered, job.accepted, job.rejected, job.excluded) == (5, 3, 1, 1)


def test_duplicate_ids_in_one_result_are_stored_once(session_factory):
    job = run(session_factory, [make("1", price="10.00"), make("1", price="20.00")])
    assert job.status == "succeeded"
    assert count(session_factory, ProductListing) == 1
    assert count(session_factory, PriceObservation) == 1


def test_list_price_is_stored_as_advertised_value(session_factory):
    run(session_factory, [make("1", price="80.00", list_price="100.00")])
    with session_factory() as s:
        obs = s.scalars(select(PriceObservation)).one()
    assert (obs.price, obs.list_price) == (Decimal("80.00"), Decimal("100.00"))


def test_currency_change_for_a_source_is_refused(session_factory):
    run(session_factory, [make("1")])
    usd = StoreConfig("s", "https://shop.example.com", "USD", "fixture")
    with pytest.raises(IngestError):
        run_collection(session_factory, usd, lambda: ScrapeResult("s"))


def test_disabled_source_is_refused(session_factory):
    run(session_factory, [make("1")])
    with session_factory() as s:
        s.scalar(select(DataSource)).enabled = False
        s.commit()
    with pytest.raises(SourceDisabledError):
        run(session_factory, [make("1")])
    assert count(session_factory, ScrapeJob) == 1
