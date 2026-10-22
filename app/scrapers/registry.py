from dataclasses import dataclass

from app.core.config import get_settings
from app.scrapers.base import SourceConfigError
from app.scrapers.sources.shopify import ShopifyStoreSource
from app.utils.http import build_session
from app.utils.robots import RobotsGuard


@dataclass(frozen=True)
class StoreConfig:
    name: str
    base_url: str   # https only, no trailing slash
    currency: str   # products.json carries no currency, so it must be configured explicitly
    status: str     # "candidate" until `scripts.preflight` passes and you confirm currency
    # Items the store itself marks as non-products. Matched case-insensitively and reported
    # as "excluded", never silently dropped.
    exclude_tags: tuple[str, ...] = ()
    exclude_product_types: tuple[str, ...] = ()


STORES: dict[str, StoreConfig] = {
    # UNVERIFIED candidates. The platform and currency are assumptions until preflight confirms.
    # Preflight passed on 2026-10-22 (robots allows /products.json, JSON 200, meta.json says INR).
    # Still "candidate": Terms of Service not yet reviewed.
    # Exclusions come from tags seen on live data: 'Developer_Test' (a test item) and
    # 'AI_Subscr' / product_type 'VAS' (a digital subscription, not hardware).
    "boat": StoreConfig("boat", "https://www.boat-lifestyle.com", "INR", "candidate",
                        exclude_tags=("Developer_Test", "AI_Subscr"),
                        exclude_product_types=("VAS",)),
    # Preflight passed on 2026-10-22 as above. No exclusions known yet: inspect before adding any.
    "noise": StoreConfig("noise", "https://www.gonoise.com", "INR", "candidate"),
}


def build_source(name: str) -> ShopifyStoreSource:
    config = STORES.get(name)
    if config is None:
        raise SourceConfigError(f"unknown source {name!r}; configured: {sorted(STORES)}")
    settings = get_settings()
    session = build_session(settings.http_user_agent)
    robots = RobotsGuard(session, timeout=settings.http_timeout_seconds)
    return ShopifyStoreSource(config, session, robots, timeout=settings.http_timeout_seconds)