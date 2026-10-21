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


STORES: dict[str, StoreConfig] = {
    # UNVERIFIED candidates. The platform and currency are assumptions until preflight confirms.
    "boat": StoreConfig("boat", "https://www.boat-lifestyle.com", "INR", "candidate"),
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