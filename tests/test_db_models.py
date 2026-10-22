"""Integration tests: need a real PostgreSQL. Set TEST_DATABASE_URL to a database whose
name ends in _test (its tables are DROPPED after the run). Skipped otherwise."""
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import Base, DataSource, PriceObservation, ProductListing, ScrapeJob

pytestmark = pytest.mark.integration
URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def session():
    if not URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    engine = create_engine(URL)
    if not engine.url.database.endswith("_test"):
        pytest.fail("refusing to run: TEST_DATABASE_URL database name must end with _test")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)
    engine.dispose()


def _listing(session, lid="1"):
    src = session.query(DataSource).filter_by(name="s").first() or DataSource(
        name="s", base_url="https://shop.example.com", currency="INR")
    session.add(src)
    listing = ProductListing(source=src, source_listing_id=lid, title="T", url="https://shop.example.com/p")
    session.add(listing)
    session.flush()
    return listing


def _obs(listing, **kw):
    base = dict(listing_id=listing.id, observed_at=datetime.now(timezone.utc),
                price=Decimal("10.00"), currency="INR", availability="in_stock")
    return PriceObservation(**{**base, **kw})


def test_price_keeps_exact_decimal(session):
    listing = _listing(session)
    session.add(_obs(listing, price=Decimal("1499.10")))
    session.commit()
    assert session.query(PriceObservation).one().price == Decimal("1499.10")


def test_same_listing_id_unique_per_source(session):
    _listing(session, "1")
    session.commit()
    with pytest.raises(IntegrityError):
        _listing(session, "1")
        session.commit()


@pytest.mark.parametrize("kw", [
    {"price": Decimal("0")},                       # zero is never a valid price
    {"price": Decimal("-5")},
    {"list_price": Decimal("0")},
    {"currency": None},                            # price without currency is not comparable
    {"availability": "maybe"},
])
def test_bad_observations_rejected_by_database(session, kw):
    listing = _listing(session)
    session.add(_obs(listing, **kw))
    with pytest.raises(IntegrityError):
        session.commit()


def test_missing_price_is_allowed_when_availability_known(session):
    listing = _listing(session)
    session.add(_obs(listing, price=None, currency=None, availability="out_of_stock"))
    session.commit()
    assert session.query(PriceObservation).one().price is None


def test_scrape_job_status_constrained(session):
    src = DataSource(name="s", base_url="https://shop.example.com", currency="INR")
    session.add(src)
    session.flush()
    session.add(ScrapeJob(source_id=src.id, status="weird"))
    with pytest.raises(IntegrityError):
        session.commit()
