from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schemas.listing import ScrapedListing


class SourceError(Exception):
    """Base class: a source could not deliver trustworthy data."""


class SourceConfigError(SourceError):
    """Missing or invalid configuration (e.g. no API key)."""


class SourceFetchError(SourceError):
    """Network or HTTP failure. This is NOT an empty listing."""


class SourceParseError(SourceError):
    """Response shape is not what we expect. The source may have changed."""


@dataclass(frozen=True)
class RejectedRecord:
    source_listing_id: str | None
    reason: str


@dataclass
class ScrapeResult:
    source: str
    listings: list[ScrapedListing] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)  # failed validation: data problem
    excluded: list[RejectedRecord] = field(default_factory=list)  # skipped on purpose by store config

    @property
    def discovered(self) -> int:
        return len(self.listings) + len(self.rejected) + len(self.excluded)

    @property
    def rejection_rate(self) -> float:
        # Deliberate exclusions are not failures, so they stay out of this rate.
        considered = len(self.listings) + len(self.rejected)
        return len(self.rejected) / considered if considered else 0.0

    @property
    def is_degraded(self) -> bool:
        """Most records failing validation usually means a layout/schema change."""
        return (len(self.listings) + len(self.rejected)) > 0 and self.rejection_rate > 0.5


class BaseSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, query: str, page: int = 1) -> Any:
        """Network I/O only. Return the raw payload or raise SourceError."""

    @abstractmethod
    def parse(self, payload: Any) -> ScrapeResult:
        """Pure function: raw payload -> validated records. No network."""

    def collect(self, query: str, page: int | None = None) -> ScrapeResult:
        return self.parse(self.fetch(query) if page is None else self.fetch(query, page))
