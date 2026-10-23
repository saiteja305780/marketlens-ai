from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.database.models import DataSource, PriceObservation, ProductListing
from app.services.demo_data import SOURCE, DemoDataExists, seed_demo

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def test_creates_a_labelled_demo_source(session_factory):
    counts = seed_demo(session_factory, now=NOW)
    with session_factory() as s:
        src = s.scalar(select(DataSource).where(DataSource.name == SOURCE))
        assert src is not None and src.currency == "INR"
        assert s.scalar(select(func.count()).select_from(ProductListing)) == counts["listings"] == 40
        assert counts["observations"] > counts["listings"]


def test_history_is_change_only(session_factory):
    seed_demo(session_factory, now=NOW)
    with session_factory() as s:
        rows = s.execute(select(PriceObservation.listing_id, PriceObservation.price,
                                PriceObservation.list_price, PriceObservation.availability)
                         .order_by(PriceObservation.listing_id, PriceObservation.observed_at)).all()
    last = {}
    for listing_id, price, list_price, availability in rows:
        assert last.get(listing_id) != (price, list_price, availability)
        last[listing_id] = (price, list_price, availability)


def test_refuses_to_run_twice_without_reset(session_factory):
    seed_demo(session_factory, now=NOW)
    with pytest.raises(DemoDataExists):
        seed_demo(session_factory, now=NOW)


def test_reset_recreates_demo_and_leaves_real_sources_alone(session_factory):
    with session_factory() as s:
        real = DataSource(name="noise", base_url="https://example.test", currency="INR")
        s.add(real)
        s.flush()
        s.add(ProductListing(source_id=real.id, source_listing_id="x", title="Real Item",
                             url="https://example.test/p"))
        s.commit()
    seed_demo(session_factory, now=NOW)
    seed_demo(session_factory, reset=True, now=NOW)
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(ProductListing)
                        .where(ProductListing.title == "Real Item")) == 1
        demo = s.scalar(select(DataSource).where(DataSource.name == SOURCE))
        assert s.scalar(select(func.count()).select_from(ProductListing)
                        .where(ProductListing.source_id == demo.id)) == 40
