from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class Availability(str, Enum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"  # source did not say. Never guess.


class ScrapedListing(BaseModel):
    """One retailer listing as observed at one moment (not a real-world product)."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    source: str
    source_listing_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    url: HttpUrl
    price: Decimal | None = Field(default=None, gt=0)  # None = missing; 0 is invalid
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    availability: Availability = Availability.UNKNOWN
    brand: str | None = None
    model_number: str | None = None
    gtin: str | None = None
    source_sku: str | None = None  # the retailer's own SKU, NOT a manufacturer or GTIN identifier
    parent_product_id: str | None = None  # groups variants (colours etc.) of one retailer product
    list_price: Decimal | None = Field(default=None, gt=0)  # retailer's "compare at" price; not proof of a real discount
    category: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    image_url: HttpUrl | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("gtin")
    @classmethod
    def gtin_must_look_like_gtin(cls, v: str | None) -> str | None:
        # GTINs are 8, 12, 13 or 14 digits. Anything else becomes "missing"
        # rather than polluting product matching later.
        if v is None:
            return None
        return v if v.isdigit() and len(v) in (8, 12, 13, 14) else None

    @model_validator(mode="after")
    def price_requires_currency(self) -> "ScrapedListing":
        if (self.price is not None or self.list_price is not None) and self.currency is None:
            raise ValueError("a price without a currency is not comparable")
        return self