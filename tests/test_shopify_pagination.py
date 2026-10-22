import pytest

from app.scrapers.base import SourceFetchError
from app.scrapers.registry import StoreConfig
from app.scrapers.sources.shopify import ShopifyStoreSource

CONFIG = StoreConfig("noise", "https://www.gonoise.com", "INR", "candidate",
                     exclude_tags=("kwikcart-freebie",), exclude_title_suffixes=("Installation",))


def prod(i, title=None, tags=None):
    return {"id": i, "handle": f"p{i}", "title": title or f"Item {i}", "vendor": "X", "product_type": "",
            "tags": tags or [], "images": [],
            "variants": [{"id": i * 10, "title": "Default Title", "price": "999.00",
                          "compare_at_price": None, "available": True, "sku": f"s{i}"}]}


class Resp:
    def __init__(self, url, products, status=200):
        self.url, self.status_code = url, status
        self.headers = {"Content-Type": "application/json"}
        self._body = {"products": products}

    def json(self):
        return self._body


class Session:
    def __init__(self, pages_fn, fail_on=None):
        self.pages_fn, self.fail_on, self.calls = pages_fn, fail_on, []

    def get(self, url, params=None, timeout=None):
        page = params["page"]
        self.calls.append(page)
        return Resp(url, self.pages_fn(page), 429 if page == self.fail_on else 200)


class Robots:
    def allowed(self, url):
        return True

    def crawl_delay(self, url):
        return None


def source(session, **kw):
    return ShopifyStoreSource(CONFIG, session, Robots(), min_delay=0.0, **kw)


def test_paginates_until_empty_page():
    pages = {1: [prod(1), prod(2)], 2: [prod(3), prod(4)]}
    s = Session(lambda p: pages.get(p, []))
    payload = source(s, page_size=2).fetch()
    assert [p["id"] for p in payload["products"]] == [1, 2, 3, 4]
    assert s.calls == [1, 2, 3]


def test_stops_when_store_ignores_page_parameter():
    s = Session(lambda p: [prod(1), prod(2)])
    src = source(s, page_size=2)
    assert len(src.fetch()["products"]) == 2
    assert s.calls == [1, 2]
    assert src.truncated is False


def test_page_cap_sets_truncated():
    s = Session(lambda p: [prod(p * 10 + 1), prod(p * 10 + 2)])
    src = source(s, page_size=2, max_pages=3)
    assert len(src.fetch()["products"]) == 6
    assert s.calls == [1, 2, 3]
    assert src.truncated is True


def test_failure_on_later_page_fails_the_whole_fetch():
    s = Session(lambda p: [prod(p * 10 + 1)], fail_on=2)
    with pytest.raises(SourceFetchError):
        source(s, page_size=1).fetch()


def test_noise_exclusions_are_reported_not_dropped():
    products = [prod(1, "Noise Buds"), prod(2, "Noise Lanyard", ["kwikcart-freebie"]),
                prod(3, "Noise Homestage 2.1 90W Installation"),
                prod(4, "Noise Installation Kit Pro")]  # contains the word but does not END with it
    result = source(Session(lambda p: [])).parse({"products": products})
    assert sorted(l.parent_product_id for l in result.listings) == ["1", "4"]
    assert sorted(e.source_listing_id for e in result.excluded) == ["2", "3"]
