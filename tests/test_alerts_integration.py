from decimal import Decimal as D

from sqlalchemy import select

from app.database.models import Alert, AlertRule, ProductListing
from app.schemas.listing import Availability, ScrapedListing
from app.scrapers.base import ScrapeResult
from app.scrapers.registry import StoreConfig
from app.services.ingest import run_collection

CONFIG = StoreConfig("boat", "https://example.test", "INR", "candidate")


def collect(factory, price, availability=Availability.IN_STOCK):
    item = ScrapedListing(
        source="boat", source_listing_id="v1", title="Test Earbuds",
        url="https://example.test/products/x?variant=v1",
        price=None if price is None else D(price),
        currency=None if price is None else "INR",
        availability=availability)
    result = ScrapeResult(source="boat")
    result.listings.append(item)
    job = run_collection(factory, CONFIG, lambda: result)
    assert job.status == "succeeded"
    return job


def add_rule(factory, **kw):
    with factory() as s:
        listing_id = s.scalar(select(ProductListing.id))
        rule = AlertRule(listing_id=listing_id, **kw)
        s.add(rule)
        s.commit()
        return rule.id


def alert_count(factory):
    with factory() as s:
        return len(s.scalars(select(Alert)).all())


def state(factory, rule_id):
    with factory() as s:
        return s.get(AlertRule, rule_id).condition_met


def test_price_rule_fires_once_per_transition(session_factory):
    collect(session_factory, "2500")
    rid = add_rule(session_factory, rule_type="price_below", threshold=D("2000"), currency="INR")
    collect(session_factory, "2500")
    assert state(session_factory, rid) is False and alert_count(session_factory) == 0
    collect(session_factory, "1500")
    assert alert_count(session_factory) == 1
    collect(session_factory, "1500")
    collect(session_factory, "1400")
    assert alert_count(session_factory) == 1          # still true: no repeat
    collect(session_factory, "2500")
    assert state(session_factory, rid) is False
    collect(session_factory, "1500")
    assert alert_count(session_factory) == 2          # left and returned: fires again


def test_missing_price_never_fires_and_keeps_state(session_factory):
    collect(session_factory, "2500")
    rid = add_rule(session_factory, rule_type="price_below", threshold=D("2000"), currency="INR")
    collect(session_factory, "2500")
    collect(session_factory, None)
    assert state(session_factory, rid) is False and alert_count(session_factory) == 0


def test_back_in_stock_fires_on_transition(session_factory):
    collect(session_factory, "2500", Availability.OUT_OF_STOCK)
    rid = add_rule(session_factory, rule_type="back_in_stock")
    collect(session_factory, "2500", Availability.OUT_OF_STOCK)
    assert state(session_factory, rid) is False
    collect(session_factory, "2500", Availability.IN_STOCK)
    assert alert_count(session_factory) == 1
    collect(session_factory, "2500", Availability.IN_STOCK)
    assert alert_count(session_factory) == 1