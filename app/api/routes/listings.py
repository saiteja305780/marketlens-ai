from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession, PageNumber, PageSize
from app.schemas.api import HistoryOut, ListingOut, Page
from app.services import price_service, query_service

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("", response_model=Page[ListingOut])
def list_listings(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100, description="case-insensitive title search")] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
    category: Annotated[str | None, Query(max_length=200)] = None,
    brand: Annotated[str | None, Query(max_length=200)] = None,
    availability: Literal["in_stock", "out_of_stock", "unknown"] | None = None,
    sort: Literal["title", "price", "last_seen_at", "first_seen_at"] = "title",
    order: Literal["asc", "desc"] = "asc",
    page: PageNumber = 1,
    page_size: PageSize = 25,
):
    """Retailer listings with their latest observed price. Listings without a price sort last."""
    items, total = query_service.list_listings(
        db, q=q, source=source, category=category, brand=brand, availability=availability,
        sort=sort, order=order, page=page, page_size=page_size)
    return Page[ListingOut](items=items, total=total, page=page, page_size=page_size)


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: int, db: DbSession):
    listing = query_service.get_listing(db, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return listing


@router.get("/{listing_id}/history", response_model=HistoryOut)
def get_history(listing_id: int, db: DbSession,
                date_from: Annotated[datetime | None, Query(description="ISO 8601, inclusive")] = None,
                date_to: Annotated[datetime | None, Query(description="ISO 8601, inclusive")] = None):
    """Observed price history plus summary numbers. Numbers are only produced from a single
    currency, and are 'observed' prices: they do not prove the retailer advertised a discount."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if not query_service.listing_exists(db, listing_id):
        raise HTTPException(status_code=404, detail="listing not found")
    observations = query_service.get_observations(db, listing_id, date_from, date_to)
    stats, warnings = price_service.compute_history_stats(observations)
    return HistoryOut(listing_id=listing_id, observations=observations, stats=stats, warnings=warnings)
