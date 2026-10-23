from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.config import get_settings
from app.database.models import DataSource, PriceObservation, ProductListing
from app.main import create_app

KEY = "test-key-123"
H = {"X-API-Key": KEY}


@pytest.fixture
def client(session_factory, monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    get_settings.cache_clear()
    app = create_app()

    def override():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    get_settings.cache_clear()


@pytest.fixture
def seeded(session_factory):
    with session_factory() as s:
        src = DataSource(name="noise", base_url="https://example.test", currency="INR")
        s.add(src)
        s.flush()
        rows = [("A", "Noise Buds Pro", "1500.00"), ("B", "Noise Buds Air", "1200.00"),
                ("C", "Noise Watch", "3000.00"),
                ("P", "1-Year Extended Warranty Plan (Rs.0 - Rs.499 Device Range)", "99.00")]
        for key, title, price in rows:
            listing = ProductListing(source_id=src.id, source_listing_id=key, title=title,
                                     url="https://example.test/p")
            s.add(listing)
            s.flush()
            s.add(PriceObservation(listing_id=listing.id, observed_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
                                   price=Decimal(price), currency="INR", availability="in_stock"))
        s.commit()


def listings(client, **params):
    r = client.get("/api/v1/listings", headers=H, params=params)
    assert r.status_code == 200
    return r.json()


def test_plans_are_included_by_default(client, seeded):
    assert listings(client)["total"] == 4


def test_exclude_plans_removes_them_before_paging(client, seeded):
    body = listings(client, exclude_plans="true", page_size=2)
    assert body["total"] == 3 and len(body["items"]) == 2
    assert all("Warranty Plan" not in i["title"] for i in body["items"])


def test_price_range_filters_latest_price(client, seeded):
    body = listings(client, min_price="1300", max_price="2000", currency="INR")
    assert body["total"] == 1 and body["items"][0]["title"] == "Noise Buds Pro"


def test_negative_price_is_rejected(client, seeded):
    r = client.get("/api/v1/listings", headers=H, params={"min_price": "-5"})
    assert r.status_code == 422


def test_export_respects_price_filters(client, seeded):
    r = client.get("/api/v1/exports/listings.csv", headers=H,
                   params={"min_price": "1300", "max_price": "2000", "currency": "INR"})
    assert r.status_code == 200
    assert "Noise Buds Pro" in r.text
    assert "Noise Buds Air" not in r.text and "Noise Watch" not in r.text


def test_export_can_exclude_plans(client, seeded):
    with_plans = client.get("/api/v1/exports/listings.csv", headers=H).text
    without = client.get("/api/v1/exports/listings.csv", headers=H, params={"exclude_plans": "true"}).text
    assert "Warranty Plan" in with_plans
    assert "Warranty Plan" not in without
