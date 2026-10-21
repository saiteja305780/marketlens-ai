import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session(user_agent: str) -> requests.Session:
    """Session with bounded retries and backoff on transient errors only."""
    retry = Retry(
        total=3,
        backoff_factor=1.0,  # sleeps ~1s, 2s, 4s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,  # we handle the final status ourselves
    )
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session