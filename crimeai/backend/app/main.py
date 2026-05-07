"""
CrimeAI FastAPI application entry point.
Configures middleware, routers, lifespan, exception handlers, and health endpoints.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.middleware.audit_log import AuditLogMiddleware
from app.api.middleware.error_handler import (
    domain_exception_handler,
    unhandled_exception_handler,
)
from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.exceptions import CrimeAIError
from app.core.logging import get_logger, setup_logging
from app.db.redis import close_redis_pool, get_redis_pool
from app.db.session import check_db_connection, engine

# ── Logging (must be first) ──────────────────────────────────────────────────
setup_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
logger = get_logger(__name__)

# ── Sentry (error tracking) ──────────────────────────────────────────────────
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        release=settings.APP_VERSION,
        traces_sample_rate=0.1,
    )
    logger.info("sentry_initialised")

# ── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Startup: verify DB + Redis connectivity, warm ML models.
    Shutdown: close connection pools cleanly.
    """
    logger.info("application_starting", version=settings.APP_VERSION, env=settings.APP_ENV)

    # Verify database
    if not await check_db_connection():
        logger.error("startup_failed_db_unreachable")
        raise RuntimeError("Database unreachable at startup")
    logger.info("database_connected")

    # Verify Redis
    redis = await get_redis_pool()
    try:
        await redis.ping()
        logger.info("redis_connected")
    except Exception as exc:
        logger.error("startup_failed_redis_unreachable", error=str(exc))
        raise RuntimeError("Redis unreachable at startup") from exc

    logger.info("application_ready")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("application_shutting_down")
    await close_redis_pool()
    await engine.dispose()
    logger.info("application_stopped")


# ── FastAPI instance ──────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Crime Analysis & Predictive Policing Platform",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    lifespan=lifespan,
)

# ── Rate limiter state ────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# ── Trusted hosts (prevent Host header injection) ─────────────────────────────
if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.crimeai.app", "crimeai.app"],
    )

# ── Custom middleware (order matters: last added = first executed) ─────────────
app.add_middleware(AuditLogMiddleware)

# ── Exception handlers ────────────────────────────────────────────────────────
app.add_exception_handler(CrimeAIError, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


# ── Health & readiness endpoints ──────────────────────────────────────────────
@app.get("/health", tags=["observability"], summary="Liveness probe")
async def health() -> dict:
    """Returns 200 if application process is alive."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "timestamp": time.time(),
    }


@app.get("/ready", tags=["observability"], summary="Readiness probe")
async def ready() -> JSONResponse:
    """
    Returns 200 if application is ready to serve traffic.
    Checks database and Redis connectivity.
    """
    db_ok = await check_db_connection()
    redis = await get_redis_pool()
    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    all_ok = db_ok and redis_ok
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if all_ok else "degraded",
            "checks": {
                "database": "ok" if db_ok else "fail",
                "redis": "ok" if redis_ok else "fail",
            },
        },
    )
