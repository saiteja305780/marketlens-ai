from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.assistant.tools import TOOLS, ToolError, run_tool, tool_specs
from app.database.models import DataSource, PriceObservation, ProductListing


def day(n):
    return datetime(2026, 10, n, tzinfo=timezone.utc)


@pytest.fixture
def seeded(session_factory):
    with session_factory() as s:
        src = DataSource(name="noise", base_url="https://example.test", currency="INR")
        s.add(src)
        s.flush()
        ids = {}
        rows = [("A", "Noise Buds Pro", "1500.00", "in_stock", [("1600.00", 1)]),
                ("B", "Noise Buds Air", "1200.00", "in_stock", []),
                ("C", "Noise Watch", "3000.00", "out_of_stock", [])]
        for key, title, price, avail, earlier in rows:
            listing = ProductListing(source_id=src.id, source_listing_id=key, title=title, brand="Noise",
                                     url="https://example.test/p")
            s.add(listing)
            s.flush()
            for old_price, d in earlier:
                s.add(PriceObservation(listing_id=listing.id, observed_at=day(d), price=Decimal(old_price),
                                       currency="INR", availability="in_stock"))
            s.add(PriceObservation(listing_id=listing.id, observed_at=day(2), price=Decimal(price),
                                   currency="INR", availability=avail))
            ids[key] = listing.id
        s.commit()
    return session_factory, ids


def call(seeded, name, args):
    factory, _ = seeded
    with factory() as db:
        return run_tool(db, name, args)["result"]


def test_search_by_text(seeded):
    out = call(seeded, "search_listings", {"text": "buds"})
    assert out["total_matches"] == 2 and out["returned"] == 2


def test_search_price_range_sorted(seeded):
    out = call(seeded, "search_listings", {"min_price": "1000", "max_price": "2000", "currency": "INR",
                                           "sort": "price", "order": "asc"})
    assert [l["title"] for l in out["listings"]] == ["Noise Buds Air", "Noise Buds Pro"]


def test_search_availability_filter(seeded):
    out = call(seeded, "search_listings", {"availability": "out_of_stock"})
    assert [l["title"] for l in out["listings"]] == ["Noise Watch"]


def test_price_filter_without_currency_is_refused(seeded):
    with pytest.raises(ToolError, match="currency is required"):
        call(seeded, "search_listings", {"max_price": "2000"})


def test_unknown_tool_is_refused(seeded):
    with pytest.raises(ToolError, match="unknown tool"):
        call(seeded, "run_sql", {"query": "select 1"})


def test_extra_arguments_are_refused(seeded):
    with pytest.raises(ToolError, match="invalid arguments"):
        call(seeded, "search_listings", {"text": "buds", "sql": "drop table alerts"})


def test_limit_is_capped(seeded):
    with pytest.raises(ToolError, match="invalid arguments"):
        call(seeded, "search_listings", {"limit": 500})


def test_get_listing_found_and_missing(seeded):
    _, ids = seeded
    assert call(seeded, "get_listing", {"listing_id": ids["A"]})["found"] is True
    assert call(seeded, "get_listing", {"listing_id": 99999}) == {"found": False}


def test_history_with_two_points_has_stats(seeded):
    _, ids = seeded
    out = call(seeded, "get_price_history", {"listing_id": ids["A"]})
    assert out["observation_count"] == 2 and out["insufficient_data"] is False
    assert out["stats"]["latest_price"] == "1500.00" and out["stats"]["absolute_change"] == "-100.00"


def test_history_with_one_point_is_insufficient(seeded):
    _, ids = seeded
    out = call(seeded, "get_price_history", {"listing_id": ids["B"]})
    assert out["insufficient_data"] is True and out["stats"]["percent_change"] is None


def test_history_unknown_listing(seeded):
    assert call(seeded, "get_price_history", {"listing_id": 99999}) == {"found": False}


def test_compare_ranks_and_reports_missing(seeded):
    _, ids = seeded
    out = call(seeded, "compare_listings", {"listing_ids": [ids["A"], ids["B"]]})
    assert out["comparison"]["cheapest_listing_id"] == ids["B"]
    missing = call(seeded, "compare_listings", {"listing_ids": [ids["A"], 99999]})
    assert missing == {"found": False, "missing_listing_ids": [99999]}


def test_compare_needs_two_distinct_ids(seeded):
    _, ids = seeded
    with pytest.raises(ToolError):
        call(seeded, "compare_listings", {"listing_ids": [ids["A"]]})
    with pytest.raises(ToolError, match="distinct"):
        call(seeded, "compare_listings", {"listing_ids": [ids["A"], ids["A"]]})


def test_alerts_start_empty(seeded):
    assert call(seeded, "list_alerts", {}) == {"total": 0, "alerts": []}


def test_specs_describe_every_tool():
    assert sorted(s["name"] for s in tool_specs()) == sorted(TOOLS)
