from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.api import HistoryStats, ListingOut


class CompareItem(BaseModel):
    listing: ListingOut
    stats: HistoryStats | None = None
    stats_warnings: list[str] = []
    price_rank: int | None = Field(
        default=None, description="1 = lowest latest price among listings sharing one currency; ties share a rank.")


class CompareOut(BaseModel):
    items: list[CompareItem]
    currency: str | None = Field(
        default=None, description="The single currency used for ranking; null when no ranking was possible.")
    cheapest_listing_id: int | None = None
    price_spread: Decimal | None = Field(
        default=None, description="Highest minus lowest latest price, same currency only.")
    warnings: list[str] = []
