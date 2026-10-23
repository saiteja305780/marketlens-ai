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


def day(n):
    return datetime(2026, 10, n, tzinfo=timezone.utc)


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
def ids(session_factory):
    with session_factory() as s:
        src = DataSource(name="noise", base_url="https://example.test", currency="INR")
        s.add(src)
        s.flush()
        out = {}
        rows = [("A", "Noise Buds Pro", "1500.00", "in_stock", ["1600.00"]),
                ("B", "Noise Buds Air", "1200.00", "in_stock", []),
                ("C", "Noise Watch", "3000.00", "out_of_stock", [])]
        for key, title, price, avail, earlier in rows:
            listing = ProductListing(source_id=src.id, source_listing_id=key, title=title,
                                     url="https://example.test/p")
            s.add(listing)
            s.flush()
            for old in earlier:
                s.add(PriceObservation(listing_id=listing.id, observed_at=day(1), price=Decimal(old),
                                       currency="INR", availability="in_stock"))
            s.add(PriceObservation(listing_id=listing.id, observed_at=day(2), price=Decimal(price),
                                   currency="INR", availability=avail))
            out[key] = listing.id
        s.commit()
    return out


def ask(client, question):
    return client.post("/api/v1/assistant/ask", headers=H, json={"question": question})


def test_requires_api_key(client):
    assert client.post("/api/v1/assistant/ask", json={"question": "alerts"}).status_code == 401


def test_empty_question_is_validation_error(client):
    r = ask(client, "")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_search_with_price_and_stock(client, ids):
    body = ask(client, "noise buds under 1500 in stock").json()
    assert body["understood"] is True and body["tool"] == "search_listings"
    assert body["arguments"]["currency"] == "INR"
    assert "Found 2 listings" in body["answer"]


def test_cheapest_comes_first(client, ids):
    answer = ask(client, "cheapest noise buds").json()["answer"]
    assert answer.index("Noise Buds Air") < answer.index("Noise Buds Pro")


def test_words_need_not_be_adjacent(client, ids):
    answer = ask(client, "noise pro buds").json()["answer"]
    assert "Found 1 listing" in answer and "Noise Buds Pro" in answer


def test_history_with_trend(client, ids):
    answer = ask(client, f"price history of listing {ids['A']}").json()["answer"]
    assert "-100.00" in answer and "-6.25" in answer


def test_history_with_one_point_is_insufficient(client, ids):
    answer = ask(client, f"price history of listing {ids['B']}").json()["answer"]
    assert "not enough" in answer


def test_compare(client, ids):
    answer = ask(client, f"compare {ids['A']} and {ids['B']}").json()["answer"]
    assert "Lowest price" in answer and f"#{ids['B']}" in answer and "not verified" in answer


def test_sql_looking_text_is_just_search_words(client, ids):
    body = ask(client, "drop table products").json()
    assert body["tool"] == "search_listings" and "no listings" in body["answer"].lower()
    assert client.get("/api/v1/alerts", headers=H).status_code == 200
