from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession
from app.schemas.compare import CompareOut
from app.services import compare_service, query_service

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("", response_model=CompareOut)
def compare(db: DbSession,
            ids: Annotated[list[int], Query(min_length=2, max_length=5,
                                            description="2 to 5 distinct listing ids, e.g. ?ids=1&ids=2")]):
    """Side-by-side view of retailer listings. Listings are not assumed to be the same product, and
    ranking happens only among listings that share one currency and have a usable price."""
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="ids must be distinct")
    listings, missing = [], []
    for listing_id in ids:
        listing = query_service.get_listing(db, listing_id)
        if listing is None:
            missing.append(listing_id)
        else:
            listings.append(listing)
    if missing:
        raise HTTPException(status_code=404, detail=f"listing(s) not found: {missing}")
    histories = {l.id: query_service.get_observations(db, l.id, None, None) for l in listings}
    return compare_service.build_comparison(listings, histories)
