from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession, PageNumber, PageSize
from app.schemas.api import JobOut, Page
from app.services import query_service

router = APIRouter(prefix="/jobs", tags=["collection jobs"])


@router.get("", response_model=Page[JobOut])
def list_jobs(db: DbSession, source: Annotated[str | None, Query(max_length=64)] = None,
              status: Literal["running", "succeeded", "failed"] | None = None,
              page: PageNumber = 1, page_size: PageSize = 25):
    """Collection runs, newest first. Failed jobs include a short error message."""
    items, total = query_service.list_jobs(db, source=source, status=status, page=page, page_size=page_size)
    return Page[JobOut](items=items, total=total, page=page, page_size=page_size)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: DbSession):
    job = query_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
