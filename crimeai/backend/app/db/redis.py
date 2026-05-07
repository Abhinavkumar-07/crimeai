"""
Redis client factory with connection pooling.
Used for caching, Celery broker/backend, and WebSocket pub/sub.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Shared connection pool — one pool for the entire application
_redis_pool: Redis | None = None


async def get_redis_pool() -> Redis:
    """Return (and lazily create) the shared Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        logger.info("redis_pool_created", url=settings.REDIS_URL)
    return _redis_pool


async def close_redis_pool() -> None:
    """Close the pool on application shutdown."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("redis_pool_closed")


async def get_redis() -> AsyncGenerator[Redis, None]:
    """
    FastAPI dependency that provides a Redis client.

    Usage:
        @router.get("/")
        async def endpoint(redis: Redis = Depends(get_redis)):
            ...
    """
    pool = await get_redis_pool()
    yield pool


class CacheManager:
    """
    High-level cache helper.
    Handles JSON serialisation, TTL, and key namespacing.
    """

    def __init__(self, redis: Redis, namespace: str = "crimeai") -> None:
        self.redis = redis
        self.namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    async def get(self, key: str) -> Any | None:
        raw = await self.redis.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(
        self, key: str, value: Any, ttl: int | None = None
    ) -> None:
        ttl = ttl or settings.REDIS_CACHE_TTL
        serialised = json.dumps(value, default=str)
        await self.redis.setex(self._key(key), ttl, serialised)

    async def delete(self, key: str) -> None:
        await self.redis.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        return bool(await self.redis.exists(self._key(key)))

    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns count deleted."""
        full_pattern = self._key(pattern)
        keys = await self.redis.keys(full_pattern)
        if keys:
            return await self.redis.delete(*keys)
        return 0

    async def check_connection(self) -> bool:
        """Health check."""
        try:
            await self.redis.ping()
            return True
        except Exception as exc:
            logger.error("redis_health_check_failed", error=str(exc))
            return False
