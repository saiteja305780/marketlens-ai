from typing import Annotated, Iterator

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_session_factory


def get_db() -> Iterator[Session]:
    """One read session per request. Tests replace this dependency."""
    with get_session_factory()() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
PageNumber = Annotated[int, Query(ge=1, description="1-based page number")]
PageSize = Annotated[int, Query(ge=1, le=100, description="items per page (max 100)")]
