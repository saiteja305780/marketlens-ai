"""CSV export: formula-injection protection and the two download endpoints."""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.scrapers.base import ScrapeResult
from app.scrapers.registry import StoreConfig
from app.schemas.listing import Availability, ScrapedListing
from app.services.csv_export import cell, safe_text, to_csv
from app.services.ingest import run_collection

pytestmark = pytest.mark.integration
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
EVIL = '=HYPERLINK("http://evil.example")'


@pytest.mark.parametrize("text", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx", "\nx", EVIL])
def test_safe_text_neutralises_formula_starts(text):
    assert safe_text(text) == "'" + text


def test_safe_text_leaves_normal_text_alone():
    assert safe_text("Noise Buds") == "Noise Buds" and safe_text("") == "" and safe_text("a=b") == "a=b"


def test_cell_does_not_mangle_numbers():
    assert cell(Decimal("-5.00")) == "-5.00" and cell(Decimal("1999.00")) == "1999.00"
    assert cell(None) == "" and cell(True) == "true"


def test_to_csv_quotes_commas_and_quotes():
    out = to_csv(["a", "b"], [["x,y", 'say "hi"']])
    assert list(csv.reader(io.StringIO(out))) == [["a", "b"], ["x,y", 'say "hi"']]


@pytest.fixture
def client(session_factory):
    def override():
        with session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = override
    config = StoreConfig("shop", "https://shop.example.com", "INR", "fixture")
    listings = [ScrapedListing(source="shop", source_listing_id=str(i), title=title,
                               url=f"https://shop.example.com/p/{i}", price=Decimal(price), currency="INR",
                               availability=Availability.IN_STOCK, collected_at=T0)
                for i, (title, price) in enumerate([(EVIL, "100.00"), ("Normal Buds", "250.00")], 1)]
    result = ScrapeResult("shop", listings=listings)
    run_collection(session_factory, config, lambda: result)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _rows(response):
    return list(csv.DictReader(io.StringIO(response.text)))


def test_listings_export_is_csv_and_neutralises_formulas(client):
    r = client.get("/api/v1/exports/listings.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = _rows(r)
    assert len(rows) == 2
    assert {row["title"] for row in rows} == {"'" + EVIL, "Normal Buds"}
    assert not any(row["title"].startswith("=") for row in rows)
    assert {row["title"]: row["price"] for row in rows}["Normal Buds"] == "250.00"


def test_listings_export_honours_filters(client):
    rows = _rows(client.get("/api/v1/exports/listings.csv?q=Normal"))
    assert [row["title"] for row in rows] == ["Normal Buds"]


def test_history_export(client):
    listing_id = next(r["id"] for r in _rows(client.get("/api/v1/exports/listings.csv?q=Normal")))
    r = client.get(f"/api/v1/exports/listings/{listing_id}/history.csv")
    assert r.status_code == 200
    rows = _rows(r)
    assert len(rows) == 1 and rows[0]["price"] == "250.00" and rows[0]["currency"] == "INR"


def test_history_export_unknown_listing_is_404(client):
    assert client.get("/api/v1/exports/listings/999999/history.csv").status_code == 404
