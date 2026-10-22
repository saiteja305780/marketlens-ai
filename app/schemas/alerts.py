from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AlertRuleCreate(BaseModel):
    listing_id: int
    rule_type: Literal["price_below", "back_in_stock"]
    threshold: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2,
        description="Required for price_below, in the listing's source currency. Not allowed for back_in_stock.")


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    listing_id: int
    rule_type: str
    threshold: Decimal | None = None
    currency: str | None = None
    active: bool
    condition_met: bool | None = Field(
        default=None, description="Last known state; null until the rule has been checked against data.")
    created_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    listing_id: int
    job_id: int | None = None
    created_at: datetime
    message: str
    price: Decimal | None = None
    currency: str | None = None
    is_read: bool