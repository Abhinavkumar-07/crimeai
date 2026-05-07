# ==============================================================================
# CrimeAI – Redis Cache Layer
# app/db/cache.py
#
# Provides:
#   - Async Redis connection pool
#   - get/set/delete/invalidate helpers with automatic serialisation
#   - cache_key builder
#   - FastAPI dependency
#   - Health check
#   - Pub/sub for WebSocket alert broadcasting
# ==============================================================================

from __future__ import annotations

import functools
import hashlib
import json
from datetime import timedelta
from typing import Any, Callable, TypeVar

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ==============================================================================
# Connection Pool
# ==============================================================================

def _build_pool() -> ConnectionPool:
    """Build a Redis connection pool from the configured URL."""
    return ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=50,
        decode_responses=True,         # All values returned as str
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )


_pool: ConnectionPool = _build_pool()


def get_redis_client() -> Redis:
    """Return a Redis client using the shared connection pool."""
    return Redis(connection_pool=_pool)


# ==============================================================================
# Cache Helpers
# ==============================================================================

class CacheClient:
    """
    Thin async wrapper around Redis with typed serialisation.
    All values are stored as JSON strings.
    """

    def __init__(self, client: Redis) -> None:
        self._r = client

    def _serialise(self, value: Any) -> str:
        return json.dumps(value, default=str)

    def _deserialise(self, raw: str | None) -> Any:
        if raw is None:
            return None
        return json.loads(raw)

    async def get(self, key: str) -> Any:
        """Get a cached value. Returns None on miss."""
        try:
            raw = await self._r.get(key)
            return self._deserialise(raw)
        except Exception as e:
            logger.warning("cache_get_error", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Set a cached value with optional TTL in seconds.
        Defaults to settings.REDIS_CACHE_TTL.
        """
        try:
            serialised = self._serialise(value)
            expire = ttl if ttl is not None else settings.REDIS_CACHE_TTL
            await self._r.set(key, serialised, ex=expire)
            return True
        except Exception as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete a single key."""
        try:
            await self._r.delete(key)
            return True
        except Exception as e:
            logger.warning("cache_delete_error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a glob pattern.
        Use carefully – SCAN-based, not KEYS.
        Returns count of deleted keys.
        """
        try:
            deleted = 0
            async for key in self._r.scan_iter(match=pattern, count=100):
                await self._r.delete(key)
                deleted += 1
            logger.info("cache_pattern_deleted", pattern=pattern, count=deleted)
            return deleted
        except Exception as e:
            logger.warning("cache_delete_pattern_error", pattern=pattern, error=str(e))
            return 0

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        try:
            return bool(await self._r.exists(key))
        except Exception:
            return False

    async def ttl(self, key: str) -> int:
        """Return remaining TTL in seconds. -1 = no expiry. -2 = not found."""
        try:
            return await self._r.ttl(key)
        except Exception:
            return -2

    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter. Useful for rate limiting counters."""
        try:
            return await self._r.incrby(key, amount)
        except Exception:
            return 0

    async def health(self) -> dict:
        """Ping Redis and return status."""
        import time
        start = time.monotonic()
        try:
            await self._r.ping()
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            info = await self._r.info("server")
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "version": info.get("redis_version", "unknown"),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    # --------------------------------------------------------------------------
    # Pub/Sub (for WebSocket alert broadcasting)
    # --------------------------------------------------------------------------

    async def publish(self, channel: str, message: Any) -> None:
        """Publish a message to a Redis pub/sub channel."""
        try:
            await self._r.publish(channel, self._serialise(message))
        except Exception as e:
            logger.error("cache_publish_error", channel=channel, error=str(e))

    def pubsub(self) -> aioredis.client.PubSub:
        """Return a PubSub object for subscribing to channels."""
        return self._r.pubsub()


# ==============================================================================
# Cache Key Builder
# ==============================================================================

def build_cache_key(*parts: Any, prefix: str = "crimeai") -> str:
    """
    Build a structured, consistent cache key.

    Usage:
        build_cache_key("hotspots", city_id, "7d")
        → "crimeai:hotspots:city-uuid:7d"

        build_cache_key("crimes", {"lat": 28.6, "lon": 77.2}, prefix="ml")
        → "ml:crimes:<hash>"
    """
    segments: list[str] = [prefix]
    for part in parts:
        if isinstance(part, dict):
            # Hash complex objects to keep keys short
            hashed = hashlib.md5(
                json.dumps(part, sort_keys=True, default=str).encode()
            ).hexdigest()[:12]
            segments.append(hashed)
        else:
            segments.append(str(part))
    return ":".join(segments)


# ==============================================================================
# FastAPI Dependency
# ==============================================================================

async def get_cache() -> CacheClient:
    """
    FastAPI dependency that returns a CacheClient.

    Usage:
        @router.get("/hotspots")
        async def get_hotspots(cache: CacheClient = Depends(get_cache)):
            cached = await cache.get("hotspots:all")
            ...
    """
    client = get_redis_client()
    return CacheClient(client)


# ==============================================================================
# Singleton for use outside FastAPI (Celery tasks, startup)
# ==============================================================================

_cache_singleton: CacheClient | None = None


def get_cache_client() -> CacheClient:
    """Return a module-level singleton CacheClient."""
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = CacheClient(get_redis_client())
    return _cache_singleton


# ==============================================================================
# Lifecycle
# ==============================================================================

async def close_redis() -> None:
    """Close the Redis connection pool. Call on application shutdown."""
    await _pool.disconnect()
    logger.info("redis_connection_pool_closed")
