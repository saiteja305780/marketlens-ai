"""CSV downloads. Read-only and open like the other read endpoints. They reuse the same queries,
so sources that are disabled stay hidden."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import DbSession
from app.services import query_service
from app.services.csv_export import to_csv

router = APIRouter(prefix="/exports", tags=["exports"])

MAX_ROWS = 50_000
BATCH = 500

LISTING_HEADER = ["id", "source", "source_listing_id", "title", "url", "brand", "category", "source_sku",
                  "price", "list_price", "currency", "availability", "observed_at",
                  "first_seen_at", "last_seen_at", "is_stale"]
HISTORY_HEADER = ["observed_at", "price", "list_price", "currency", "availability"]


def _csv(text: str, filename: str) -> Response:
    return Response(content=text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _listing_row(i) -> list:
    latest = i.latest
    return [i.id, i.source, i.source_listing_id, i.title, i.url, i.brand, i.category, i.source_sku,
            latest.price if latest else None, latest.list_price if latest else None,
            latest.currency if latest else None, latest.availability if latest else None,
            latest.observed_at if latest else None, i.first_seen_at, i.last_seen_at, i.is_stale]


@router.get("/listings.csv")
def export_listings(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
    category: Annotated[str | None, Query(max_length=200)] = None,
    brand: Annotated[str | None, Query(max_length=200)] = None,
    availability: Literal["in_stock", "out_of_stock", "unknown"] | None = None,
    sort: Literal["title", "price", "last_seen_at", "first_seen_at"] = "title",
    order: Literal["asc", "desc"] = "asc",
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    currency: Annotated[str | None, Query(max_length=8)] = None,
    exclude_plans: bool = False,
):
    """All listings matching the filters (same filters as /listings), latest price included."""
    rows, page = [], 1
    while True:
        items, total = query_service.list_listings(
            db, q=q, source=source, category=category, brand=brand, availability=availability,
            sort=sort, order=order, page=page, page_size=BATCH,
            min_price=min_price, max_price=max_price, currency=currency, exclude_plans=exclude_plans)
        if total > MAX_ROWS:
            raise HTTPException(status_code=413, detail=f"{total} rows match; narrow the filters (limit {MAX_ROWS})")
        rows.extend(items)
        if not items or len(rows) >= total:
            break
        page += 1
    return _csv(to_csv(LISTING_HEADER, [_listing_row(i) for i in rows]), "listings.csv")


@router.get("/listings/{listing_id}/history.csv")
def export_history(listing_id: int, db: DbSession,
                   date_from: Annotated[datetime | None, Query(description="ISO 8601, inclusive")] = None,
                   date_to: Annotated[datetime | None, Query(description="ISO 8601, inclusive")] = None):
    """Observed price history of one listing."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if not query_service.listing_exists(db, listing_id):
        raise HTTPException(status_code=404, detail="listing not found")
    obs = query_service.get_observations(db, listing_id, date_from, date_to)
    rows = [[o.observed_at, o.price, o.list_price, o.currency, o.availability] for o in obs]
    return _csv(to_csv(HISTORY_HEADER, rows), f"listing-{listing_id}-history.csv")
