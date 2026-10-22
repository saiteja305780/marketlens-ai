"""Read-side database queries used by the API. Routes stay thin; SQL lives here."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.database.models import DataSource, PriceObservation, ProductListing, ScrapeJob
from app.schemas.api import JobOut, ListingOut, ObservationOut, SourceOut

SortField = Literal["title", "price", "last_seen_at", "first_seen_at"]


def _latest_obs_subquery():
    return (select(PriceObservation)
            .ext(distinct_on(PriceObservation.listing_id))
            .order_by(PriceObservation.listing_id, PriceObservation.observed_at.desc(),
                      PriceObservation.id.desc())
            .subquery())


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _to_listing_out(listing: ProductListing, source_name: str, latest, stale_before: datetime) -> ListingOut:
    return ListingOut(
        id=listing.id, source=source_name, source_listing_id=listing.source_listing_id,
        title=listing.title, url=listing.url, brand=listing.brand, category=listing.category,
        model_number=listing.model_number, gtin=listing.gtin, source_sku=listing.source_sku,
        parent_product_id=listing.parent_product_id, image_url=listing.image_url,
        first_seen_at=listing.first_seen_at, last_seen_at=listing.last_seen_at,
        is_stale=listing.last_seen_at < stale_before,
        latest=ObservationOut.model_validate(latest) if latest is not None and latest.id is not None else None)


def list_listings(session: Session, *, q: str | None, source: str | None, category: str | None,
                  brand: str | None, availability: str | None, sort: SortField, order: str,
                  page: int, page_size: int) -> tuple[list[ListingOut], int]:
    latest_sq = _latest_obs_subquery()
    Latest = aliased(PriceObservation, latest_sq)

    stmt = (select(ProductListing, DataSource.name, Latest)
            .join(DataSource, DataSource.id == ProductListing.source_id)
            .outerjoin(Latest, Latest.listing_id == ProductListing.id))
    stmt = stmt.where(DataSource.enabled.is_(True))
    if q:
        stmt = stmt.where(ProductListing.title.ilike(f"%{_escape_like(q)}%", escape="\\"))
    if source:
        stmt = stmt.where(DataSource.name == source)
    if category:
        stmt = stmt.where(ProductListing.category == category)
    if brand:
        stmt = stmt.where(ProductListing.brand == brand)
    if availability:
        stmt = stmt.where(Latest.availability == availability)

    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0

    columns = {"title": ProductListing.title, "price": Latest.price,
               "last_seen_at": ProductListing.last_seen_at, "first_seen_at": ProductListing.first_seen_at}
    col = columns[sort]
    ordered = col.desc() if order == "desc" else col.asc()
    if sort == "price":
        ordered = ordered.nulls_last()  # listings without a price never win a price sort
    stmt = stmt.order_by(ordered, ProductListing.id).limit(page_size).offset((page - 1) * page_size)

    stale_before = datetime.now(timezone.utc) - timedelta(hours=get_settings().stale_after_hours)
    items = [_to_listing_out(l, name, latest, stale_before) for l, name, latest in session.execute(stmt)]
    return items, total


def get_listing(session: Session, listing_id: int) -> ListingOut | None:
    latest_sq = _latest_obs_subquery()
    Latest = aliased(PriceObservation, latest_sq)
    row = session.execute(
        select(ProductListing, DataSource.name, Latest)
        .join(DataSource, DataSource.id == ProductListing.source_id)
        .outerjoin(Latest, Latest.listing_id == ProductListing.id)
        .where(ProductListing.id == listing_id, DataSource.enabled.is_(True))).first()
    if row is None:
        return None
    stale_before = datetime.now(timezone.utc) - timedelta(hours=get_settings().stale_after_hours)
    return _to_listing_out(row[0], row[1], row[2], stale_before)


def listing_exists(session: Session, listing_id: int) -> bool:
    return session.scalar(select(ProductListing.id).join(DataSource, DataSource.id == ProductListing.source_id).where(ProductListing.id == listing_id, DataSource.enabled.is_(True))) is not None


def get_observations(session: Session, listing_id: int, date_from: datetime | None,
                     date_to: datetime | None) -> list[ObservationOut]:
    stmt = select(PriceObservation).where(PriceObservation.listing_id == listing_id)
    if date_from:
        stmt = stmt.where(PriceObservation.observed_at >= date_from)
    if date_to:
        stmt = stmt.where(PriceObservation.observed_at <= date_to)
    stmt = stmt.order_by(PriceObservation.observed_at, PriceObservation.id)
    return [ObservationOut.model_validate(o) for o in session.scalars(stmt)]


def list_sources(session: Session) -> list[SourceOut]:
    counts = dict(session.execute(
        select(ProductListing.source_id, func.count()).group_by(ProductListing.source_id)).all())
    last_ok = dict(session.execute(
        select(ScrapeJob.source_id, func.max(ScrapeJob.finished_at))
        .where(ScrapeJob.status == "succeeded").group_by(ScrapeJob.source_id)).all())
    last_status = dict(session.execute(
        select(ScrapeJob.source_id, ScrapeJob.status)
        .ext(distinct_on(ScrapeJob.source_id))
        .order_by(ScrapeJob.source_id, ScrapeJob.started_at.desc(), ScrapeJob.id.desc())).all())
    return [SourceOut(name=s.name, base_url=s.base_url, currency=s.currency, enabled=s.enabled,
                      listing_count=counts.get(s.id, 0), last_job_status=last_status.get(s.id),
                      last_success_at=last_ok.get(s.id))
            for s in session.scalars(select(DataSource).where(DataSource.enabled.is_(True)).order_by(DataSource.name))]


def _job_out(job: ScrapeJob, source_name: str) -> JobOut:
    duration = (job.finished_at - job.started_at).total_seconds() if job.finished_at else None
    return JobOut(id=job.id, source=source_name, status=job.status, started_at=job.started_at,
                  finished_at=job.finished_at, duration_seconds=duration, discovered=job.discovered,
                  accepted=job.accepted, rejected=job.rejected, excluded=job.excluded,
                  observations_written=job.observations_written, degraded=job.degraded,
                  error_type=job.error_type, error_message=job.error_message)


def list_jobs(session: Session, *, source: str | None, status: str | None,
              page: int, page_size: int) -> tuple[list[JobOut], int]:
    stmt = select(ScrapeJob, DataSource.name).join(DataSource, DataSource.id == ScrapeJob.source_id)
    if source:
        stmt = stmt.where(DataSource.name == source)
    stmt = stmt.where(DataSource.enabled.is_(True))
    if status:
        stmt = stmt.where(ScrapeJob.status == status)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    stmt = stmt.order_by(ScrapeJob.started_at.desc(), ScrapeJob.id.desc()).limit(page_size).offset((page - 1) * page_size)
    return [_job_out(j, name) for j, name in session.execute(stmt)], total


def get_job(session: Session, job_id: int) -> JobOut | None:
    row = session.execute(select(ScrapeJob, DataSource.name)
                          .join(DataSource, DataSource.id == ScrapeJob.source_id)
                          .where(ScrapeJob.id == job_id, DataSource.enabled.is_(True))).first()
    return _job_out(*row) if row else None
