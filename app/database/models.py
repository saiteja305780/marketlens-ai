from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index,
    Integer, MetaData, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Explicit constraint names keep Alembic migrations predictable.
NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


TZ = DateTime(timezone=True)
MONEY = Numeric(14, 2)  # exact decimal, never float


class DataSource(Base):
    """A configured store we are allowed to collect from."""
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    base_url: Mapped[str] = mapped_column(String(300))
    currency: Mapped[str] = mapped_column(String(3))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())

    listings: Mapped[list["ProductListing"]] = relationship(back_populates="source")


class ProductListing(Base):
    """One retailer listing (e.g. one colour variant). NOT a real-world product:
    cross-store product identity is a later, separate concept."""
    __tablename__ = "product_listings"
    __table_args__ = (
        UniqueConstraint("source_id", "source_listing_id"),
        Index("ix_product_listings_source_id_last_seen_at", "source_id", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_listing_id: Mapped[str] = mapped_column(String(64))
    parent_product_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(200))
    model_number: Mapped[str | None] = mapped_column(String(100))
    gtin: Mapped[str | None] = mapped_column(String(14))
    source_sku: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())

    source: Mapped[DataSource] = relationship(back_populates="listings")
    observations: Mapped[list["PriceObservation"]] = relationship(back_populates="listing")


class ScrapeJob(Base):
    """One collection run for one source."""
    __tablename__ = "scrape_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('running','succeeded','failed')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(TZ)
    discovered: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    accepted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rejected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    excluded: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    observations_written: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)  # sanitized text only, never secrets


class PriceObservation(Base):
    """Append-only history. A row is written only when something changed."""
    __tablename__ = "price_observations"
    __table_args__ = (
        CheckConstraint("price IS NULL OR price > 0", name="price_positive"),
        CheckConstraint("list_price IS NULL OR list_price > 0", name="list_price_positive"),
        CheckConstraint("(price IS NULL AND list_price IS NULL) OR currency IS NOT NULL",
                        name="price_needs_currency"),
        CheckConstraint("availability IN ('in_stock','out_of_stock','unknown')",
                        name="availability_valid"),
        Index("ix_price_observations_listing_id_observed_at", "listing_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("product_listings.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_jobs.id"))
    observed_at: Mapped[datetime] = mapped_column(TZ)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    list_price: Mapped[Decimal | None] = mapped_column(MONEY)  # advertised "compare at"; not proof of a discount
    currency: Mapped[str | None] = mapped_column(String(3))
    availability: Mapped[str] = mapped_column(String(16))

    listing: Mapped[ProductListing] = relationship(back_populates="observations")


class AlertRule(Base):
    """A user rule on one listing. `condition_met` is the last known state so alerts fire only on
    a transition; NULL means never evaluated."""
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("rule_type IN ('price_below','back_in_stock')", name="rule_type_valid"),
        CheckConstraint(
            "rule_type <> 'price_below' OR (threshold IS NOT NULL AND threshold > 0 AND currency IS NOT NULL)",
            name="price_below_needs_threshold"),
        Index("ix_alert_rules_listing_id_active", "listing_id", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("product_listings.id"))
    rule_type: Mapped[str] = mapped_column(String(24))
    threshold: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    condition_met: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class Alert(Base):
    """An in-app notification created when a rule's condition becomes true."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rules.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("product_listings.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_jobs.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    message: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(3))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")