from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.api import SourceOut
from app.services import query_service

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
def list_sources(db: DbSession):
    """Configured sources with listing counts and last collection status."""
    return query_service.list_sources(db)
