from datetime import datetime, timezone
from decimal import Decimal as D

from app.schemas.api import ListingOut, ObservationOut
from app.services.compare_service import build_comparison

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


def listing(id, price, currency="INR", availability="in_stock", stale=False):
    latest = None if price is None else ObservationOut(
        observed_at=NOW, price=D(price), currency=currency, availability=availability)
    return ListingOut(id=id, source="noise", source_listing_id=f"v{id}", title=f"Item {id}",
                      url="https://example.test/p", first_seen_at=NOW, last_seen_at=NOW,
                      is_stale=stale, latest=latest)


def has(out, text):
    return any(text in w for w in out.warnings)


def test_ranks_cheapest_and_spread():
    out = build_comparison([listing(1, "1500"), listing(2, "1200"), listing(3, "1800")], {})
    assert [i.price_rank for i in out.items] == [2, 1, 3]
    assert out.cheapest_listing_id == 2 and out.currency == "INR" and out.price_spread == D("600")


def test_always_warns_not_verified_same_product():
    assert has(build_comparison([listing(1, "1500"), listing(2, "1200")], {}), "not verified")


def test_tie_has_no_single_cheapest():
    out = build_comparison([listing(1, "1200"), listing(2, "1200"), listing(3, "1500")], {})
    assert out.cheapest_listing_id is None
    assert [i.price_rank for i in out.items] == [1, 1, 3]
    assert has(out, "share the lowest price")


def test_mixed_currencies_are_never_ranked():
    out = build_comparison([listing(1, "1500"), listing(2, "20", currency="USD")], {})
    assert out.currency is None and out.cheapest_listing_id is None and out.price_spread is None
    assert all(i.price_rank is None for i in out.items) and has(out, "several currencies")


def test_listing_without_price_is_not_ranked():
    out = build_comparison([listing(1, "1500"), listing(2, None), listing(3, "1200")], {})
    assert out.items[1].price_rank is None and has(out, "no usable current price")
    assert out.cheapest_listing_id == 3


def test_zero_price_is_not_usable():
    out = build_comparison([listing(1, "1500"), listing(2, "0"), listing(3, "1200")], {})
    assert out.items[1].price_rank is None


def test_fewer_than_two_priced_gives_no_ranking():
    out = build_comparison([listing(1, "1500"), listing(2, None)], {})
    assert out.cheapest_listing_id is None and has(out, "fewer than two")


def test_cheapest_out_of_stock_is_flagged():
    out = build_comparison([listing(1, "1500"), listing(2, "1200", availability="out_of_stock")], {})
    assert out.cheapest_listing_id == 2 and has(out, "not shown as in stock")


def test_stale_listing_is_flagged():
    out = build_comparison([listing(1, "1500", stale=True), listing(2, "1200")], {})
    assert has(out, "not been seen recently")
