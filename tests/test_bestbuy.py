import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.listing import Availability, ScrapedListing
from app.scrapers.base import SourceConfigError, SourceFetchError, SourceParseError
from app.scrapers.sources.bestbuy import BestBuySource

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "bestbuy_products_sample.json"


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response

    def get(self, url, params=None, timeout=None):
        return self.response


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def source():
    return BestBuySource(api_key="secret-key-123", session=FakeSession(FakeResponse(payload={"products": []})))


def test_parse_counts(source, payload):
    result = source.parse(payload)
    assert len(result.listings) == 3
    assert len(result.rejected) == 1
    assert result.rejected[0].source_listing_id == "1000004"
    assert "price" in result.rejected[0].reason
    assert not result.is_degraded


def test_price_is_decimal_and_fields_mapped(source, payload):
    laptop = source.parse(payload).listings[0]
    assert laptop.price == Decimal("649.99")
    assert laptop.currency == "USD"
    assert laptop.availability is Availability.IN_STOCK
    assert laptop.category == "Laptops"
    assert laptop.gtin == "012345678905"


def test_missing_price_stays_missing_not_zero(source, payload):
    monitor = source.parse(payload).listings[2]
    assert monitor.price is None
    assert monitor.currency is None
    assert monitor.availability is Availability.UNKNOWN
    assert monitor.gtin is None  # "not-a-gtin" normalized to missing


def test_unexpected_shape_raises_parse_error(source):
    with pytest.raises(SourceParseError):
        source.parse({"error": "something changed"})


def test_price_without_currency_rejected():
    with pytest.raises(ValidationError):
        ScrapedListing(source="x", source_listing_id="1", title="t",
                       url="https://example.com/a", price=Decimal("5"))


def test_fetch_requires_api_key():
    with pytest.raises(SourceConfigError):
        BestBuySource(api_key=None).fetch("laptop")


def test_fetch_rejects_unsafe_query(source):
    with pytest.raises(SourceConfigError):
        source.fetch("laptop)&apiKey=evil")


def test_http_401_error_does_not_leak_key():
    src = BestBuySource(api_key="secret-key-123", session=FakeSession(FakeResponse(status_code=401)))
    with pytest.raises(SourceFetchError) as exc_info:
        src.fetch("laptop")
    assert "secret-key-123" not in str(exc_info.value)


def test_fetch_failure_is_error_not_empty_result():
    src = BestBuySource(api_key="k", session=FakeSession(FakeResponse(status_code=503)))
    with pytest.raises(SourceFetchError):
        src.collect("laptop")