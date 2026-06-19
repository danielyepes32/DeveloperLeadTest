"""Application entrypoint — wiring, middleware, error handling, observability."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app import __version__, models  # noqa: F401  (import models to register tables)
from app.config import get_settings
from app.database import Base, engine
from app.errors import DomainError
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestContextMiddleware
from app.routers import auth, health, negotiations, requests

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("app.main")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # For this exercise the schema is bootstrapped here; production uses Alembic
    # migrations (versioned, reviewable, reversible) — see Arquitectura/.
    Base.metadata.create_all(bind=engine)
    logger.info("startup", extra={"context": {"env": settings.app_env, "version": __version__}})
    yield
    logger.info("shutdown")


app = FastAPI(
    title="Procurement Negotiation API",
    version=__version__,
    summary="Product requests, supplier offers, counteroffers and decisions.",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)

# CORS — locked down by default; enable explicit origins via CORS_ORIGINS.
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Prometheus metrics at /metrics (observability).
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    """Map domain errors to consistent JSON without leaking internals."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(requests.router)
app.include_router(negotiations.offers_router)
app.include_router(negotiations.router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


# Lightweight static SPA (HTML + vanilla JS) that drives the API — demonstrates
# the full negotiation flow end to end.
app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
