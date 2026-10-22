"""API key check for write and alert endpoints. Fails closed: with no key configured the
endpoints answer 503 instead of being open to everyone."""
import secrets
from typing import Annotated

from fastapi import Header, HTTPException

from app.core.config import get_settings


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().api_key
    if not expected:
        raise HTTPException(status_code=503, detail="API key is not configured on the server")
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="missing or invalid API key")