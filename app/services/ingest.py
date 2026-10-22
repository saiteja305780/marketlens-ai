"""Turns a ScrapeResult into stored listings, price observations and a job record.

Rules this module enforces:
- A failed fetch or a degraded parse writes NO listings or observations. A failure is never
  treated as "the store has no products".
- A price_observations row is written only when price, list_price, currency or availability
  changed since the last observation. History stays compact and repeat runs add no duplicates.
- last_seen_at moves on every successful sighting, so data freshness is queryable without
  adding history rows.
- Every run is recorded in scrape_jobs, including failures.
"""
import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import DataSource, PriceObservation, ProductListing, ScrapeJob
from app.scrapers.base import ScrapeResult
from app.scrapers.registry import StoreConfig
from app.services.alerts import evaluate_rules

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")


class IngestError(Exception):
    pass


class SourceDisabledError(IngestError):
    pass


class DegradedResultError(IngestError):
    pass


def _money(value: Decimal | None) -> Decimal | None:
    """Round to the 2 decimals the database stores, so the same price never looks 'changed'
    just because of rounding. A value that rounds to zero is treated as missing."""
    if value is None:
        return None
    rounded = value.quantize(CENT, rounding=ROUND_HALF_UP)
    return rounded if rounded > 0 else None


def _chunks(items: list[Any], size: int = 5000) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def ensure_source(session: Session, config: StoreConfig) -> DataSource:
    source = session.scalar(select(DataSource).where(DataSource.name == config.name))
    if source is None:
        source = DataSource(name=config.name, base_url=config.base_url, currency=config.currency)
        session.add(source)
        session.flush()
    elif source.currency != config.currency:
        # Silently mixing currencies would corrupt every price comparison.
        raise IngestError(
            f"source {config.name!r} is stored as {source.currency} but configured as "
            f"{config.currency}; refusing to continue")
    return source


def run_collection(factory: sessionmaker[Session], config: StoreConfig,
                   fetch: Callable[[], ScrapeResult]) -> ScrapeJob:
    """Fetch (outside any DB transaction), then store the result in one transaction.
    Always returns the finished job row; failures are recorded, not raised."""
    with factory() as session:
        source = ensure_source(session, config)
        if not source.enabled:
            raise SourceDisabledError(f"source {config.name!r} is disabled")
        job = ScrapeJob(source_id=source.id, status="running")
        session.add(job)
        session.commit()
        job_id, source_id = job.id, source.id

    try:
        result = fetch()
    except Exception as exc:
        return _fail(factory, job_id, exc)

    if result.is_degraded:
        return _fail(factory, job_id, DegradedResultError(
            f"{len(result.rejected)} of {len(result.listings) + len(result.rejected)} records "
            "failed validation; the source layout may have changed. Nothing was stored."), result)

    try:
        with factory() as session:
            job = session.get(ScrapeJob, job_id)
            _store(session, job, source_id, result)
            session.commit()
            session.refresh(job)
            return job
    except Exception as exc:
        return _fail(factory, job_id, exc, result)


def _store(session: Session, job: ScrapeJob, source_id: int, result: ScrapeResult) -> None:
    now = datetime.now(timezone.utc)

    unique: dict[str, Any] = {}
    for item in result.listings:
        if item.source_listing_id in unique:
            logger.warning("duplicate listing id %s in one result; keeping the first",
                           item.source_listing_id)
        else:
            unique[item.source_listing_id] = item

    existing: dict[str, ProductListing] = {}
    for chunk in _chunks(list(unique)):
        for row in session.scalars(select(ProductListing).where(
                ProductListing.source_id == source_id,
                ProductListing.source_listing_id.in_(chunk))):
            existing[row.source_listing_id] = row

    rows: dict[str, ProductListing] = {}
    created = 0
    for sid, item in unique.items():
        attrs = dict(
            parent_product_id=item.parent_product_id, title=item.title, url=str(item.url),
            brand=item.brand, category=item.category, model_number=item.model_number,
            gtin=item.gtin, source_sku=item.source_sku,
            image_url=str(item.image_url) if item.image_url else None,
        )
        row = existing.get(sid)
        if row is None:
            row = ProductListing(source_id=source_id, source_listing_id=sid,
                                 first_seen_at=now, last_seen_at=now, **attrs)
            session.add(row)
            created += 1
        else:
            for key, value in attrs.items():
                if value is not None:  # a field missing from one scrape never erases a known value
                    setattr(row, key, value)
            row.last_seen_at = now
        rows[sid] = row
    session.flush()

    latest: dict[int, PriceObservation] = {}
    ids = [r.id for r in rows.values()]
    for chunk in _chunks(ids):
        query = (select(PriceObservation)
                 .ext(distinct_on(PriceObservation.listing_id))
                 .where(PriceObservation.listing_id.in_(chunk))
                 .order_by(PriceObservation.listing_id,
                           PriceObservation.observed_at.desc(), PriceObservation.id.desc()))
        for obs in session.scalars(query):
            latest[obs.listing_id] = obs

    written = 0
    current = {}
    for sid, item in unique.items():
        row = rows[sid]
        new = (_money(item.price), _money(item.list_price), item.currency, item.availability.value)
        current[row.id] = (new[0], new[2], new[3])
        prev = latest.get(row.id)
        if prev is not None and (prev.price, prev.list_price, prev.currency, prev.availability) == new:
            continue
        session.add(PriceObservation(
            listing_id=row.id, job_id=job.id, observed_at=item.collected_at,
            price=new[0], list_price=new[1], currency=new[2], availability=new[3]))
        written += 1

    evaluate_rules(session, job.id, current, {r.id: r.title for r in rows.values()})
    job.status = "succeeded"
    job.finished_at = now
    job.discovered = result.discovered
    job.accepted = len(result.listings)
    job.rejected = len(result.rejected)
    job.excluded = len(result.excluded)
    job.observations_written = written
    job.degraded = False
    logger.info("stored %s: %d listings (%d new), %d observations written",
                result.source, len(unique), created, written)


def _fail(factory: sessionmaker[Session], job_id: int, exc: Exception,
          result: ScrapeResult | None = None) -> ScrapeJob:
    with factory() as session:
        job = session.get(ScrapeJob, job_id)
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_type = type(exc).__name__
        lines = str(exc).splitlines()
        job.error_message = (lines[0] if lines else "")[:500]  # first line only; no connection details
        job.degraded = isinstance(exc, DegradedResultError)
        if result is not None:
            job.discovered = result.discovered
            job.accepted = len(result.listings)
            job.rejected = len(result.rejected)
            job.excluded = len(result.excluded)
        job.observations_written = 0
        session.commit()
        session.refresh(job)
        logger.error("collection job %s failed: %s", job_id, job.error_type)
        return job
