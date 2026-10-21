import logging
import re
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import requests
from pydantic import ValidationError

from app.schemas.listing import Availability, ScrapedListing
from app.scrapers.base import (
    BaseSource,
    RejectedRecord,
    ScrapeResult,
    SourceConfigError,
    SourceFetchError,
    SourceParseError,
)
from app.utils.money import to_decimal
from app.utils.robots import RobotsGuard

logger = logging.getLogger(__name__)

# Collection handles go into the URL path, so allow a conservative character set.
_SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,79}$")


class ShopifyStoreSource(BaseSource):
    """Reads a Shopify store's public catalog JSON (/products.json).
    `query` is an optional collection handle; empty means the whole catalog.
    Each VARIANT becomes one listing, because variants have their own price and stock."""

    def __init__(self, config, session: requests.Session, robots: RobotsGuard,
                 timeout: float = 15.0, page_size: int = 50, min_delay: float = 2.0) -> None:
        self.name = config.name
        self._base = config.base_url.rstrip("/")
        self._host = urlsplit(self._base).netloc
        self._currency = config.currency
        self._session = session
        self._robots = robots
        self._timeout = timeout
        self._page_size = page_size
        self._min_delay = min_delay
        self._last_request: float | None = None

    def _wait_turn(self, url: str) -> None:
        delay = max(self._min_delay, self._robots.crawl_delay(url) or 0.0)
        if self._last_request is not None:
            remaining = delay - (time.monotonic() - self._last_request)
            if remaining > 0:
                time.sleep(remaining)

    def fetch(self, query: str = "", page: int = 1) -> Any:
        scope = query.strip().lower()
        if scope and not _SCOPE_RE.match(scope):
            raise SourceConfigError("collection handle may contain only a-z, 0-9 and '-'")
        path = f"/collections/{scope}/products.json" if scope else "/products.json"
        url = f"{self._base}{path}"

        if not self._robots.allowed(url):
            raise SourceFetchError(
                f"{self.name}: robots.txt disallows {path} (or could not be read); not fetching"
            )
        self._wait_turn(url)
        logger.info("fetching %s %s page=%d", self.name, path, page)
        try:
            resp = self._session.get(url, params={"limit": self._page_size, "page": page},
                                     timeout=self._timeout)
        except requests.RequestException as exc:
            raise SourceFetchError(f"request failed: {type(exc).__name__}") from None
        finally:
            self._last_request = time.monotonic()

        if urlsplit(resp.url).netloc != self._host:
            raise SourceFetchError("redirected to a different host; refusing to follow")
        if resp.status_code in (401, 403, 429):
            raise SourceFetchError(
                f"access refused (HTTP {resp.status_code}); we do not retry or work around this"
            )
        if resp.status_code == 404:
            raise SourceFetchError("endpoint not available (store may not expose products.json)")
        if resp.status_code != 200:
            raise SourceFetchError(f"unexpected HTTP status {resp.status_code}")
        if "json" not in resp.headers.get("Content-Type", "").lower():
            raise SourceParseError("response is not JSON (possibly an HTML block or login page)")
        try:
            return resp.json()
        except ValueError:
            raise SourceParseError("response was not valid JSON") from None

    def parse(self, payload: Any) -> ScrapeResult:
        if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
            raise SourceParseError("response has no 'products' list; the format may have changed")
        result = ScrapeResult(source=self.name)
        for product in payload["products"]:
            if not isinstance(product, dict):
                result.rejected.append(RejectedRecord(None, "product entry is not an object"))
                continue
            variants = product.get("variants")
            if not isinstance(variants, list) or not variants:
                result.rejected.append(RejectedRecord(str(product.get("id")), "product has no variants"))
                continue
            for variant in variants:
                vid = str(variant.get("id")) if isinstance(variant, dict) else None
                try:
                    result.listings.append(self._build(product, variant))
                except ValidationError as exc:
                    reason = "; ".join(
                        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
                    )
                    result.rejected.append(RejectedRecord(vid, reason))
                except (ValueError, AttributeError) as exc:
                    result.rejected.append(RejectedRecord(vid, str(exc)))
        if result.is_degraded:
            logger.warning("%s: %d of %d records rejected, possible format change",
                           self.name, len(result.rejected), result.discovered)
        return result

    @staticmethod
    def _optional_price(value: Any) -> Decimal | None:
        """Auxiliary price field: unusable values become missing instead of rejecting the listing."""
        try:
            parsed = to_decimal(value)
        except ValueError:
            return None
        if parsed is None or not parsed.is_finite() or parsed <= 0:
            return None
        return parsed

    def _build(self, product: dict, variant: dict) -> ScrapedListing:
        handle, vid = product.get("handle"), variant.get("id")
        if handle is None or vid is None:
            raise ValueError("missing product handle or variant id")

        title = product.get("title") or ""
        variant_title = variant.get("title")
        if variant_title and variant_title != "Default Title":
            title = f"{title} - {variant_title}"

        price = to_decimal(variant.get("price"))
        list_price = self._optional_price(variant.get("compare_at_price"))
        available = variant.get("available")
        if isinstance(available, bool):
            availability = Availability.IN_STOCK if available else Availability.OUT_OF_STOCK
        else:
            availability = Availability.UNKNOWN

        images = product.get("images")
        image = images[0].get("src") if isinstance(images, list) and images and isinstance(images[0], dict) else None

        return ScrapedListing(
            source=self.name,
            source_listing_id=str(vid),
            title=title,
            url=f"{self._base}/products/{handle}?variant={vid}",
            price=price,
            currency=self._currency if (price is not None or list_price is not None) else None,
            list_price=list_price,
            availability=availability,
            brand=product.get("vendor") or None,
            source_sku=str(variant.get("sku") or "").strip() or None,
            parent_product_id=str(product["id"]) if product.get("id") is not None else None,
            category=(product.get("product_type") or "").strip() or None,
            image_url=image,
        )