from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.database.models import DataSource, PriceObservation, ProductListing
from app.main import create_app


@pytest.fixture
def client(session_factory):
    app = create_app()

    def override():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def seed(factory, enabled=True):
    with factory() as s:
        src = DataSource(name="noise", base_url="https://example.test", currency="INR", enabled=enabled)
        s.add(src)
        s.flush()
        ids = []
        for n, price in enumerate(["1500.00", "1200.00"], start=1):
            listing = ProductListing(source_id=src.id, source_listing_id=f"v{n}", title=f"Item {n}",
                                     url="https://example.test/p")
            s.add(listing)
            s.flush()
            s.add(PriceObservation(listing_id=listing.id, observed_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
                                   price=Decimal(price), currency="INR", availability="in_stock"))
            ids.append(listing.id)
        s.commit()
        return ids


def test_compare_two_listings(client, session_factory):
    a, b = seed(session_factory)
    r = client.get(f"/api/v1/compare?ids={a}&ids={b}")
    assert r.status_code == 200
    body = r.json()
    assert body["cheapest_listing_id"] == b and body["price_spread"] == "300.00"
    assert body["currency"] == "INR" and len(body["items"]) == 2


def test_one_id_is_a_validation_error(client, session_factory):
    a, _ = seed(session_factory)
    r = client.get(f"/api/v1/compare?ids={a}")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_more_than_five_ids_is_a_validation_error(client):
    r = client.get("/api/v1/compare?ids=1&ids=2&ids=3&ids=4&ids=5&ids=6")
    assert r.status_code == 422


def test_duplicate_ids_are_rejected(client, session_factory):
    a, _ = seed(session_factory)
    assert client.get(f"/api/v1/compare?ids={a}&ids={a}").status_code == 422


def test_unknown_id_is_404(client, session_factory):
    a, _ = seed(session_factory)
    r = client.get(f"/api/v1/compare?ids={a}&ids=99999")
    assert r.status_code == 404 and "99999" in r.json()["error"]["message"]


def test_disabled_source_is_treated_as_not_found(client, session_factory):
    a, b = seed(session_factory, enabled=False)
    assert client.get(f"/api/v1/compare?ids={a}&ids={b}").status_code == 404
