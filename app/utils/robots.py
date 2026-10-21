import logging
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)


class RobotsGuard:
    """Checks robots.txt before fetching. Conservative by design:
    missing robots.txt (404/410) -> allowed (the standard's convention);
    unreadable (403, 5xx, network error) -> NOT allowed."""

    def __init__(self, session: requests.Session, agent_token: str = "MarketLensAI",
                 timeout: float = 15.0) -> None:
        self._session = session
        self._token = agent_token
        self._timeout = timeout
        self._cache: dict[str, tuple[str, RobotFileParser | None]] = {}

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def _load(self, url: str) -> tuple[str, RobotFileParser | None]:
        origin = self._origin(url)
        if origin in self._cache:
            return self._cache[origin]
        try:
            resp = self._session.get(f"{origin}/robots.txt", timeout=self._timeout)
        except requests.RequestException as exc:
            logger.warning("robots.txt unreachable for %s (%s)", origin, type(exc).__name__)
            entry: tuple[str, RobotFileParser | None] = ("unreadable", None)
        else:
            if resp.status_code == 200:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                entry = ("loaded", parser)
            elif resp.status_code in (404, 410):
                entry = ("missing", None)
            else:
                entry = ("unreadable", None)
        self._cache[origin] = entry
        return entry

    def policy(self, url: str) -> str:
        """'loaded' | 'missing' | 'unreadable'"""
        return self._load(url)[0]

    def allowed(self, url: str) -> bool:
        kind, parser = self._load(url)
        if kind == "missing":
            return True
        if kind == "unreadable" or parser is None:
            return False
        return parser.can_fetch(self._token, url)

    def crawl_delay(self, url: str) -> float | None:
        _, parser = self._load(url)
        if parser is None:
            return None
        delay = parser.crawl_delay(self._token)
        return float(delay) if delay is not None else None