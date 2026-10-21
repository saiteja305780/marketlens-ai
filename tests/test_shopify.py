import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.scrapers.base import SourceConfigError, SourceFetchError, SourceParseError
from app.scrapers.registry import StoreConfig
from app.scrapers.sources.shopify import ShopifyStoreSource
from tests.fakes import AllowAll, DenyAll, FakeResponse, FakeSession

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic" / "shopify_products_sample.json"
CONFIG = StoreConfig("fixture-store", "https://shop.example.com", "INR", "fixture")


def make(response=None, robots=None):
    return ShopifyStoreSource(CONFIG, FakeSession(response or FakeResponse()), robots or AllowAll(), min_delay=0)


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_counts(payload):
    result = make().parse(payload)
    assert len(result.listings) == 3  # 2 earbud variants + speaker
    assert len(result.rejected) == 1  # zero-price watch
    assert "price" in result.rejected[0].reason
    assert not result.is_degraded


def test_variant_title_and_url(payload):
    black, white, speaker = make().parse(payload).listings
    assert black.title == "TEST-FIXTURE Wireless Earbuds - Black"
    assert speaker.title == "TEST-FIXTURE Speaker"  # "Default Title" is not appended
    assert str(black.url) == "https://shop.example.com/products/test-fixture-earbuds?variant=9001"


def test_price_currency_availability(payload):
    black, white, _ = make().parse(payload).listings
    assert black.price == Decimal("1999.00") and black.currency == "INR"
    assert black.availability.value == "in_stock"
    assert white.availability.value == "out_of_stock"


def test_empty_product_type_is_missing(payload):
    assert make().parse(payload).listings[2].category is None


def test_unexpected_shape_raises():
    with pytest.raises(SourceParseError):
        make().parse({"errors": "x"})


def test_blocked_by_robots_makes_no_request():
    src = make(robots=DenyAll())
    with pytest.raises(SourceFetchError):
        src.fetch()
    assert src._session.calls == []


def test_403_is_an_error_not_empty():
    with pytest.raises(SourceFetchError):
        make(FakeResponse(status_code=403)).fetch()


def test_non_json_response_rejected():
    with pytest.raises(SourceParseError):
        make(FakeResponse(content_type="text/html", text="<html>captcha</html>")).fetch()


def test_redirect_to_other_host_refused():
    with pytest.raises(SourceFetchError):
        make(FakeResponse(payload={"products": []}, url="https://evil.example.net/products.json")).fetch()


def test_invalid_collection_handle_rejected():
    with pytest.raises(SourceConfigError):
        make().fetch("../admin")