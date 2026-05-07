# ==============================================================================
# CrimeAI – Database Layer
# app/db/database.py
#
# Provides:
#   - Async SQLAlchemy engine with connection pooling
#   - AsyncSession factory
#   - FastAPI dependency for session injection
#   - Base declarative model with audit columns
# ==============================================================================

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import DateTime, String, text
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings
from app.core.logging import get_logger
logger = get_logger(__name__)


# ==============================================================================
# Engine
# ==============================================================================

def _build_engine() -> AsyncEngine:
    """
    Create the async SQLAlchemy engine with tuned connection pool settings.

    Pool configuration targets:
      - Render free tier: 1 instance, max ~100 DB connections from Supabase
      - Production: multiple Render instances, each with pool_size=10
    """
    engine_kwargs: dict = {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_pre_ping": True,          # Detect stale connections before use
        "pool_recycle": 1800,           # Recycle connections every 30 min
        "echo": settings.APP_DEBUG and settings.APP_ENV == "development",
    }

    # asyncpg doesn't support pool options via connect_args in the same way
    # as psycopg2. We configure everything at the engine level.
    engine = create_async_engine(
        settings.DATABASE_URL,
        **engine_kwargs,
    )

    logger.info(
        "database_engine_created",
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
    return engine


# Singleton engine – created once at module import
engine: AsyncEngine = _build_engine()

# Session factory – use this to create sessions
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # Don't expire objects after commit (important for async)
    autocommit=False,
    autoflush=False,
)


# ==============================================================================
# Base Model
# ==============================================================================

class Base(AsyncAttrs, DeclarativeBase):
    """
    Base class for all SQLAlchemy models.

    Provides:
      - UUID primary key (id)
      - created_at / updated_at audit timestamps (UTC)
      - __repr__ for debugging
    """
    pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UUIDMixin:
    """Mixin that adds a UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )


class AuditMixin(UUIDMixin, TimestampMixin):
    """Combines UUID PK + timestamps. Use as base for all domain models."""
    pass


# ==============================================================================
# Session Dependency (FastAPI)
# ==============================================================================

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a scoped async database session.

    Automatically:
      - Opens a session at the start of the request
      - Commits on success
      - Rolls back on any exception
      - Closes the session regardless

    Usage in endpoint:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ==============================================================================
# Context Manager (for Celery workers / scripts outside FastAPI)
# ==============================================================================

@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions outside of FastAPI's
    dependency injection (e.g., Celery tasks, startup scripts).

    Usage:
        async with get_db_context() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ==============================================================================
# Health Check
# ==============================================================================

async def check_db_health() -> dict:
    """
    Verify database connectivity. Used by /health and /ready endpoints.
    Returns a dict with status and latency information.
    """
    import time

    start = time.monotonic()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {"status": "unhealthy", "error": str(e)}


# ==============================================================================
# Lifecycle
# ==============================================================================

async def close_db() -> None:
    """Dispose the connection pool. Call on application shutdown."""
    await engine.dispose()
    logger.info("database_connection_pool_closed")
