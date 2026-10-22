"""API tests that need no database."""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_database():
    """These requests are rejected before any query runs, so a stub stands in for the database."""
    app.dependency_overrides[get_db] = lambda: None
    yield
    app.dependency_overrides.pop(get_db, None)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_unknown_route_uses_consistent_error_shape():
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_404"


def test_validation_errors_use_consistent_error_shape():
    r = client.get("/api/v1/listings?page=0")
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error" and body["details"][0]["where"].endswith("page")


def test_page_size_is_capped():
    assert client.get("/api/v1/listings?page_size=101").status_code == 422


def test_invalid_sort_field_rejected():
    assert client.get("/api/v1/listings?sort=password").status_code == 422


def test_openapi_docs_are_available():
    assert client.get("/openapi.json").status_code == 200
