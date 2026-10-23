import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import alerts, exports, jobs, listings, sources
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.scheduler import start_scheduler_if_enabled

logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    scheduler = start_scheduler_if_enabled()  # None unless SCHEDULER_ENABLED=true
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    setup_logging(get_settings().log_level)
    app = FastAPI(
        title="MarketLens AI",
        version="0.1.0",
        description="Product intelligence API: listings, observed price history and collection jobs.",
        lifespan=_lifespan,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, f"http_{exc.status_code}", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"where": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]} for e in exc.errors()]
        return _error(422, "validation_error", "request validation failed", details)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        logger.exception("unhandled error")  # full detail goes to the log, never to the client
        return _error(500, "internal_error", "internal server error")

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    for router in (sources.router, listings.router, jobs.router, alerts.router, exports.router):
        app.include_router(router, prefix="/api/v1")
    from app.api.routes import compare
    app.include_router(compare.router, prefix="/api/v1")
    return app


app = create_app()
