"""Async Redis cache for external API responses.

Provides cache-through with dedup locking for any external HTTP call site.
Gracefully degrades to no-op when Redis is unavailable or disabled.

Cache key structure::

    api_cache:{scope}:{url_hash}           → JSON response
    api_cache:lock:{scope}:{url_hash}      → "1" (dedup)

Usage::

    cache = ApiResponseCache()  # reads REDIS_URL, disabled if empty
    data = await cache.get("ch_api:fetch_company", url)
    if data is None:
        data = ...  # HTTP call
        await cache.put("ch_api:fetch_company", url, data, ttl=86400)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 86400  # 24 hours
_LOCK_TTL = 60  # 1 minute


class ApiResponseCache:
    """Async Redis-backed cache for external API responses.

    All methods are async and fail-open: if Redis is unavailable,
    operations silently degrade to no-ops.

    Args:
        redis_url: Explicit Redis URL.  ``None`` → read ``REDIS_URL`` env var.
        enabled: Set ``False`` to force-disable (all ops become no-ops).
    """

    def __init__(self, redis_url: str | None = None, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "")
        self._redis: Any = None
        self._connected = False

    async def _ensure_connected(self) -> bool:
        """Lazy-connect to Redis on first use.  Returns True if connected."""
        if not self._enabled or not self._redis_url:
            return False
        if self._connected:
            return True
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
            )
            await self._redis.ping()
            self._connected = True
            logger.info("ApiResponseCache connected to Redis")
            return True
        except Exception as e:
            logger.info("ApiResponseCache disabled (Redis unavailable: %s)", e)
            self._redis = None
            self._connected = False
            return False

    @property
    def available(self) -> bool:
        """Whether the cache backend is connected."""
        return self._connected

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _key(self, scope: str, url: str) -> str:
        return f"api_cache:{scope}:{self._url_hash(url)}"

    def _lock_key(self, scope: str, url: str) -> str:
        return f"api_cache:lock:{scope}:{self._url_hash(url)}"

    async def get(self, scope: str, url: str) -> dict[str, Any] | None:
        """Return cached response data, or ``None`` on miss."""
        if not await self._ensure_connected():
            return None
        try:
            raw = await self._redis.get(self._key(scope, url))
            if raw:
                result: dict[str, Any] = json.loads(raw)
                return result
        except Exception as e:
            logger.debug("Cache get failed: %s", e)
        return None

    async def put(
        self,
        scope: str,
        url: str,
        data: dict[str, Any],
        ttl: int = _DEFAULT_TTL,
    ) -> None:
        """Cache a response with an expiry."""
        if not await self._ensure_connected():
            return
        try:
            await self._redis.setex(
                self._key(scope, url),
                ttl,
                json.dumps(data, default=str),
            )
        except Exception as e:
            logger.debug("Cache put failed: %s", e)

    async def acquire_lock(self, scope: str, url: str) -> bool:
        """Acquire a dedup lock for an in-flight request.

        Returns ``True`` if the lock was acquired (caller should proceed).
        """
        if not await self._ensure_connected():
            return True  # no Redis → no dedup, proceed
        try:
            return bool(
                await self._redis.set(
                    self._lock_key(scope, url),
                    "1",
                    nx=True,
                    ex=_LOCK_TTL,
                )
            )
        except Exception:
            return True  # fail-open

    async def release_lock(self, scope: str, url: str) -> None:
        """Release the dedup lock after an HTTP response is received."""
        if not self._connected or not self._redis:
            return
        try:
            await self._redis.delete(self._lock_key(scope, url))
        except Exception as e:
            logger.debug("Lock release failed: %s", e)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
            self._connected = False
