"""API integration tests against a real PostgreSQL (need TEST_DATABASE_URL)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.database.models import PriceObservation
from app.main import app
from app.scrapers.base import RejectedRecord, ScrapeResult, SourceFetchError
from app.scrapers.registry import StoreConfig
from app.schemas.listing import Availability, ScrapedListing
from app.services.ingest import run_collection

pytestmark = pytest.mark.integration
CONFIG = StoreConfig("shop", "https://shop.example.com", "INR", "fixture")
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def make(i, title, price="100.00", avail=Availability.IN_STOCK, at=T0, category=None, brand=None):
    return ScrapedListing(
        source="shop", source_listing_id=str(i), title=title, url=f"https://shop.example.com/p/{i}",
        price=Decimal(price) if price is not None else None, currency="INR" if price is not None else None,
        availability=avail, collected_at=at, category=category, brand=brand)


def collect(factory, listings, **kw):
    result = ScrapeResult("shop", listings=list(listings), **kw)
    return run_collection(factory, CONFIG, lambda: result)


@pytest.fixture
def client(session_factory):
    def override():
        with session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(session_factory, client):
    collect(session_factory, [
        make(1, "Alpha Earbuds", "1999.00", category="Audio", brand="Alpha"),
        make(2, "Beta Watch", "4999.00", category="Wearables", brand="Beta"),
        make(3, "Gamma 100% Speaker", None, Availability.OUT_OF_STOCK, category="Audio"),
    ])
    return client


def test_listings_pagination(seeded):
    page1 = seeded.get("/api/v1/listings?page_size=2").json()
    assert page1["total"] == 3 and len(page1["items"]) == 2 and page1["page"] == 1
    page2 = seeded.get("/api/v1/listings?page_size=2&page=2").json()
    assert len(page2["items"]) == 1
    titles = [i["title"] for i in page1["items"] + page2["items"]]
    assert titles == sorted(titles)  # default sort by title, stable across pages


def test_listing_contains_latest_price_and_freshness(seeded):
    item = seeded.get("/api/v1/listings?q=alpha").json()["items"][0]
    assert item["latest"]["price"] == "1999.00" and item["latest"]["currency"] == "INR"
    assert item["source"] == "shop" and item["is_stale"] is False


def test_search_treats_percent_literally(seeded):
    assert seeded.get("/api/v1/listings?q=%25").json()["total"] == 1  # only "100% Speaker"


def test_filters(seeded):
    assert seeded.get("/api/v1/listings?category=Audio").json()["total"] == 2
    assert seeded.get("/api/v1/listings?brand=Beta").json()["total"] == 1
    assert seeded.get("/api/v1/listings?source=shop").json()["total"] == 3
    assert seeded.get("/api/v1/listings?source=other").json()["total"] == 0
    assert seeded.get("/api/v1/listings?availability=out_of_stock").json()["total"] == 1


def test_sort_by_price_puts_missing_prices_last_both_ways(seeded):
    asc = [i["title"] for i in seeded.get("/api/v1/listings?sort=price&order=asc").json()["items"]]
    desc = [i["title"] for i in seeded.get("/api/v1/listings?sort=price&order=desc").json()["items"]]
    assert asc == ["Alpha Earbuds", "Beta Watch", "Gamma 100% Speaker"]
    assert desc == ["Beta Watch", "Alpha Earbuds", "Gamma 100% Speaker"]


def test_listing_detail_and_404(seeded):
    first_id = seeded.get("/api/v1/listings?q=alpha").json()["items"][0]["id"]
    assert seeded.get(f"/api/v1/listings/{first_id}").status_code == 200
    r = seeded.get("/api/v1/listings/999999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "http_404"


def test_history_with_stats(session_factory, client):
    collect(session_factory, [make(1, "Alpha", "100.00", at=T0)])
    collect(session_factory, [make(1, "Alpha", "90.00", at=T0 + timedelta(days=1))])
    collect(session_factory, [make(1, "Alpha", "120.00", at=T0 + timedelta(days=2))])
    lid = client.get("/api/v1/listings").json()["items"][0]["id"]
    body = client.get(f"/api/v1/listings/{lid}/history").json()
    assert [o["price"] for o in body["observations"]] == ["100.00", "90.00", "120.00"]
    stats = body["stats"]
    assert stats["lowest_price"] == "90.00" and stats["highest_price"] == "120.00"
    assert stats["absolute_change"] == "20.00" and stats["percent_change"] == "20.00"


def test_history_date_range_and_validation(session_factory, client):
    for d, p in [(0, "100.00"), (1, "90.00"), (2, "120.00")]:
        collect(session_factory, [make(1, "Alpha", p, at=T0 + timedelta(days=d))])
    lid = client.get("/api/v1/listings").json()["items"][0]["id"]
    since = (T0 + timedelta(days=1)).isoformat()
    r = client.get(f"/api/v1/listings/{lid}/history", params={"date_from": since})
    assert [o["price"] for o in r.json()["observations"]] == ["90.00", "120.00"]
    bad = client.get(f"/api/v1/listings/{lid}/history",
                     params={"date_from": (T0 + timedelta(days=5)).isoformat(), "date_to": T0.isoformat()})
    assert bad.status_code == 422


def test_history_mixed_currency_gives_warning_not_numbers(session_factory, client):
    collect(session_factory, [make(1, "Alpha", "100.00")])
    with session_factory() as s:
        base = s.scalars(select(PriceObservation)).one()
        s.add(PriceObservation(listing_id=base.listing_id, observed_at=T0 + timedelta(days=1),
                               price=Decimal("2.00"), currency="USD", availability="in_stock"))
        s.commit()
    lid = client.get("/api/v1/listings").json()["items"][0]["id"]
    body = client.get(f"/api/v1/listings/{lid}/history").json()
    assert body["stats"] is None and "currencies" in body["warnings"][0]


def test_history_of_unknown_listing_is_404(client):
    assert client.get("/api/v1/listings/12345/history").status_code == 404


def test_sources_endpoint(seeded):
    src = seeded.get("/api/v1/sources").json()[0]
    assert src["name"] == "shop" and src["listing_count"] == 3
    assert src["last_job_status"] == "succeeded" and src["last_success_at"] is not None


def test_jobs_list_and_failed_job_details(session_factory, client):
    collect(session_factory, [make(1, "Alpha")], excluded=[RejectedRecord("9", "test item")])

    def boom():
        raise SourceFetchError("HTTP 503 from shop.example.com")
    run_collection(session_factory, CONFIG, boom)

    all_jobs = client.get("/api/v1/jobs").json()
    assert all_jobs["total"] == 2 and all_jobs["items"][0]["status"] == "failed"  # newest first
    failed = client.get("/api/v1/jobs?status=failed").json()["items"][0]
    assert failed["error_type"] == "SourceFetchError" and "503" in failed["error_message"]
    ok = client.get("/api/v1/jobs?status=succeeded").json()["items"][0]
    assert ok["excluded"] == 1 and ok["duration_seconds"] is not None
    assert client.get(f"/api/v1/jobs/{ok['id']}").status_code == 200
    assert client.get("/api/v1/jobs/9999").status_code == 404
    assert client.get("/api/v1/jobs?status=weird").status_code == 422
