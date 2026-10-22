"""A disabled source is hidden from every read path and cannot get new alert rules."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.api.deps import get_db
from app.database.models import DataSource
from app.main import app
from app.scrapers.base import ScrapeResult
from app.scrapers.registry import StoreConfig
from app.schemas.alerts import AlertRuleCreate
from app.schemas.listing import Availability, ScrapedListing
from app.services import alert_service, query_service
from app.services.ingest import run_collection

pytestmark = pytest.mark.integration
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def _collect(factory, name, title):
    config = StoreConfig(name, f"https://{name}.example.com", "INR", "fixture")
    listing = ScrapedListing(source=name, source_listing_id="1", title=title,
                             url=f"https://{name}.example.com/p/1", price=Decimal("999.00"),
                             currency="INR", availability=Availability.IN_STOCK, collected_at=T0)
    result = ScrapeResult(name, listings=[listing])
    run_collection(factory, config, lambda: result)


@pytest.fixture
def world(session_factory):
    def override():
        with session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    _collect(session_factory, "shop", "Visible Phone")
    _collect(session_factory, "hidden", "Hidden Phone")
    ids = {name: client.get(f"/api/v1/listings?source={name}").json()["items"][0]["id"]
           for name in ("shop", "hidden")}
    with session_factory() as s:
        jobs, _ = query_service.list_jobs(s, source="hidden", status=None, page=1, page_size=25)
        ids["hidden_job"] = jobs[0].id
        s.execute(update(DataSource).where(DataSource.name == "hidden").values(enabled=False))
        s.commit()
    yield client, session_factory, ids
    app.dependency_overrides.clear()


def test_listing_list_hides_disabled_source(world):
    client, _, _ = world
    body = client.get("/api/v1/listings").json()
    assert [i["title"] for i in body["items"]] == ["Visible Phone"] and body["total"] == 1
    assert client.get("/api/v1/listings?source=hidden").json()["total"] == 0


def test_detail_and_history_hide_disabled_source(world):
    client, _, ids = world
    assert client.get(f"/api/v1/listings/{ids['hidden']}").status_code == 404
    assert client.get(f"/api/v1/listings/{ids['hidden']}/history").status_code == 404
    assert client.get(f"/api/v1/listings/{ids['shop']}").status_code == 200
    assert client.get(f"/api/v1/listings/{ids['shop']}/history").status_code == 200


def test_sources_hide_disabled_source(world):
    _, factory, _ = world
    with factory() as s:
        assert [x.name for x in query_service.list_sources(s)] == ["shop"]


def test_jobs_hide_disabled_source(world):
    _, factory, ids = world
    with factory() as s:
        items, total = query_service.list_jobs(s, source=None, status=None, page=1, page_size=25)
        assert total == 1 and items[0].source == "shop"
        assert query_service.get_job(s, ids["hidden_job"]) is None


def test_cannot_create_alert_rule_on_disabled_source(world):
    _, factory, ids = world
    with factory() as s:
        with pytest.raises(alert_service.NotFoundError):
            alert_service.create_rule(s, AlertRuleCreate(listing_id=ids["hidden"], rule_type="back_in_stock"))


def test_rule_and_alert_lists_hide_disabled_source(world):
    from app.database.models import Alert, AlertRule
    _, factory, ids = world
    with factory() as s:
        for key in ("shop", "hidden"):
            rule = AlertRule(listing_id=ids[key], rule_type="back_in_stock")
            s.add(rule)
            s.flush()
            s.add(Alert(rule_id=rule.id, listing_id=ids[key], message=f"{key} alert"))
        s.commit()
    with factory() as s:
        rules, rule_total = alert_service.list_rules(s, None, 1, 25)
        alerts, alert_total = alert_service.list_alerts(s, False, 1, 25)
        assert rule_total == 1 and [r.listing_id for r in rules] == [ids["shop"]]
        assert alert_total == 1 and [a.listing_id for a in alerts] == [ids["shop"]]
