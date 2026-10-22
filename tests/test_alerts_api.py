from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.core.config import get_settings
from app.database.models import Alert, DataSource, ProductListing
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


def seed(factory):
    with factory() as s:
        src = DataSource(name="boat", base_url="https://example.test", currency="INR")
        s.add(src)
        s.flush()
        listing = ProductListing(source_id=src.id, source_listing_id="v1", title="Test Earbuds",
                                 url="https://example.test/p")
        s.add(listing)
        s.commit()
        return listing.id


def test_no_key_is_401(client):
    r = client.get("/api/v1/alerts")
    assert r.status_code == 401 and r.json()["error"]["code"] == "http_401"


def test_wrong_key_is_401(client):
    assert client.get("/api/v1/alerts", headers={"X-API-Key": "nope"}).status_code == 401


def test_unconfigured_key_is_503(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    assert client.get("/api/v1/alerts", headers=H).status_code == 503


def test_create_price_rule_takes_currency_from_source(client, session_factory):
    lid = seed(session_factory)
    r = client.post("/api/v1/alert-rules", headers=H,
                    json={"listing_id": lid, "rule_type": "price_below", "threshold": "1999.00"})
    assert r.status_code == 201
    body = r.json()
    assert body["currency"] == "INR" and body["threshold"] == "1999.00"
    assert body["active"] is True and body["condition_met"] is None


def test_price_rule_requires_threshold(client, session_factory):
    lid = seed(session_factory)
    r = client.post("/api/v1/alert-rules", headers=H, json={"listing_id": lid, "rule_type": "price_below"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "http_422"


def test_back_in_stock_rejects_threshold(client, session_factory):
    lid = seed(session_factory)
    r = client.post("/api/v1/alert-rules", headers=H,
                    json={"listing_id": lid, "rule_type": "back_in_stock", "threshold": "100"})
    assert r.status_code == 422


def test_unknown_listing_is_404(client):
    r = client.post("/api/v1/alert-rules", headers=H,
                    json={"listing_id": 999, "rule_type": "back_in_stock"})
    assert r.status_code == 404


def test_unknown_rule_type_is_validation_error(client, session_factory):
    lid = seed(session_factory)
    r = client.post("/api/v1/alert-rules", headers=H, json={"listing_id": lid, "rule_type": "nonsense"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_list_and_deactivate_rules(client, session_factory):
    lid = seed(session_factory)
    rid = client.post("/api/v1/alert-rules", headers=H,
                      json={"listing_id": lid, "rule_type": "back_in_stock"}).json()["id"]
    assert client.get("/api/v1/alert-rules?active=true", headers=H).json()["total"] == 1
    assert client.delete(f"/api/v1/alert-rules/{rid}", headers=H).json()["active"] is False
    assert client.get("/api/v1/alert-rules?active=true", headers=H).json()["total"] == 0
    assert client.get("/api/v1/alert-rules", headers=H).json()["total"] == 1
    assert client.delete("/api/v1/alert-rules/999", headers=H).status_code == 404


def test_alerts_unread_filter_and_mark_read(client, session_factory):
    lid = seed(session_factory)
    rid = client.post("/api/v1/alert-rules", headers=H,
                      json={"listing_id": lid, "rule_type": "back_in_stock"}).json()["id"]
    with session_factory() as s:
        s.add(Alert(rule_id=rid, listing_id=lid, message="Test Earbuds: back in stock"))
        s.commit()
        aid = s.scalar(select(Alert.id))
    assert client.get("/api/v1/alerts?unread_only=true", headers=H).json()["total"] == 1
    assert client.post(f"/api/v1/alerts/{aid}/read", headers=H).json()["is_read"] is True
    assert client.get("/api/v1/alerts?unread_only=true", headers=H).json()["total"] == 0
    assert client.get("/api/v1/alerts", headers=H).json()["total"] == 1


def test_mark_read_unknown_alert_is_404(client):
    assert client.post("/api/v1/alerts/999/read", headers=H).status_code == 404