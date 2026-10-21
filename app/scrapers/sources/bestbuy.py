import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

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
from app.utils.http import build_session

logger = logging.getLogger(__name__)

SOURCE_NAME = "bestbuy"
BASE_URL = "https://api.bestbuy.com/v1/products"
CURRENCY = "USD"  # Best Buy US catalog
SHOW_FIELDS = ",".join([
    "sku", "name", "url", "salePrice", "onlineAvailability", "upc",
    "modelNumber", "manufacturer", "categoryPath.name",
    "customerReviewAverage", "customerReviewCount", "image",
])
# Query goes into the URL path, so allow only a conservative character set.
_QUERY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-]{0,59}$")


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))  # str() avoids float artifacts like 0.1+0.2
    except InvalidOperation:
        raise ValueError(f"unparseable price: {value!r}") from None


def _build_listing(raw: dict[str, Any]) -> ScrapedListing:
    sku = raw.get("sku")
    if sku is None:
        raise ValueError("missing sku")

    price = _to_decimal(raw.get("salePrice"))
    online = raw.get("onlineAvailability")
    if isinstance(online, bool):
        availability = Availability.IN_STOCK if online else Availability.OUT_OF_STOCK
    else:
        availability = Availability.UNKNOWN

    path = raw.get("categoryPath")
    category = path[-1].get("name") if isinstance(path, list) and path else None

    return ScrapedListing(
        source=SOURCE_NAME,
        source_listing_id=str(sku),
        title=raw.get("name") or "",
        url=raw.get("url"),
        price=price,
        currency=CURRENCY if price is not None else None,
        availability=availability,
        brand=raw.get("manufacturer"),
        model_number=raw.get("modelNumber"),
        gtin=raw.get("upc"),
        category=category,
        rating=raw.get("customerReviewAverage"),
        review_count=raw.get("customerReviewCount"),
        image_url=raw.get("image"),
    )


class BestBuySource(BaseSource):
    name = SOURCE_NAME

    def __init__(
        self,
        api_key: str | None,
        user_agent: str = "MarketLensAI/0.1",
        timeout: float = 15.0,
        page_size: int = 25,
        session: requests.Session | None = None,  # injectable for tests
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._page_size = page_size
        self._session = session or build_session(user_agent)

    def fetch(self, query: str, page: int = 1) -> Any:
        if not self._api_key:
            raise SourceConfigError("BESTBUY_API_KEY is not configured")
        if not _QUERY_RE.match(query):
            raise SourceConfigError("query contains unsupported characters")

        terms = "&".join(f"search={t}" for t in query.split())
        url = f"{BASE_URL}({terms})"
        params = {
            "apiKey": self._api_key,
            "format": "json",
            "show": SHOW_FIELDS,
            "pageSize": self._page_size,
            "page": page,
        }
        logger.info("fetching %s query=%r page=%d", SOURCE_NAME, query, page)
        try:
            resp = self._session.get(url, params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            # `from None` + type name only: the exception text and traceback
            # contain the full URL, which includes the API key.
            raise SourceFetchError(f"request failed: {type(exc).__name__}") from None

        if resp.status_code in (401, 403):
            raise SourceFetchError(f"API key rejected (HTTP {resp.status_code})")
        if resp.status_code != 200:
            raise SourceFetchError(f"unexpected HTTP status {resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            raise SourceParseError("response was not valid JSON") from None

    def parse(self, payload: Any) -> ScrapeResult:
        if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
            raise SourceParseError(
                "response has no 'products' list; the API shape may have changed"
            )
        result = ScrapeResult(source=SOURCE_NAME)
        for raw in payload["products"]:
            raw_id = str(raw.get("sku")) if isinstance(raw, dict) and raw.get("sku") is not None else None
            try:
                result.listings.append(_build_listing(raw))
            except ValidationError as exc:
                reason = "; ".join(
                    f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
                )
                result.rejected.append(RejectedRecord(raw_id, reason))
            except (ValueError, AttributeError) as exc:
                result.rejected.append(RejectedRecord(raw_id, str(exc)))
        if result.is_degraded:
            logger.warning(
                "%s: %d of %d records rejected, possible schema change",
                SOURCE_NAME, len(result.rejected), result.discovered,
            )
        return result