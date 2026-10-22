"""Response/request shapes for the HTTP API. Decimals are serialized as strings
(e.g. "1499.00") so no precision is lost in JSON."""
from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observed_at: datetime
    price: Decimal | None = None
    list_price: Decimal | None = Field(
        default=None, description="Price the retailer advertises as the 'compare at' price. "
                                  "Not proof of a real discount.")
    currency: str | None = None
    availability: str


class ListingOut(BaseModel):
    id: int
    source: str
    source_listing_id: str
    title: str
    url: str
    brand: str | None = None
    category: str | None = None
    model_number: str | None = None
    gtin: str | None = None
    source_sku: str | None = Field(default=None, description="The retailer's own SKU, not a manufacturer ID.")
    parent_product_id: str | None = None
    image_url: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    is_stale: bool = Field(description="True if the listing has not been seen recently (see STALE_AFTER_HOURS).")
    latest: ObservationOut | None = None


class HistoryStats(BaseModel):
    currency: str
    observation_count: int
    first_observed_at: datetime
    latest_observed_at: datetime
    first_price: Decimal
    latest_price: Decimal
    lowest_price: Decimal = Field(description="Lowest price we observed. Not necessarily an advertised discount.")
    highest_price: Decimal
    absolute_change: Decimal | None = Field(default=None, description="latest - first, same currency only.")
    percent_change: Decimal | None = Field(default=None, description="(latest - first) / first * 100.")


class HistoryOut(BaseModel):
    listing_id: int
    observations: list[ObservationOut]
    stats: HistoryStats | None = None
    warnings: list[str] = []


class SourceOut(BaseModel):
    name: str
    base_url: str
    currency: str
    enabled: bool
    listing_count: int
    last_job_status: str | None = None
    last_success_at: datetime | None = None


class JobOut(BaseModel):
    id: int
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    discovered: int
    accepted: int
    rejected: int
    excluded: int
    observations_written: int
    degraded: bool
    error_type: str | None = None
    error_message: str | None = None
