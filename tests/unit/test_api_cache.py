"""Tests for ApiResponseCache."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from dazzle_back.runtime.api_cache import ApiResponseCache


def _run(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Disabled / no-op behaviour
# ---------------------------------------------------------------------------


class TestDisabledCache:
    def test_enabled_false_get_returns_none(self) -> None:
        cache = ApiResponseCache(enabled=False)
        assert _run(cache.get("scope", "http://x")) is None

    def test_enabled_false_put_is_noop(self) -> None:
        cache = ApiResponseCache(enabled=False)
        _run(cache.put("scope", "http://x", {"a": 1}))
        assert _run(cache.get("scope", "http://x")) is None

    def test_enabled_false_lock_returns_true(self) -> None:
        cache = ApiResponseCache(enabled=False)
        assert _run(cache.acquire_lock("scope", "http://x")) is True

    def test_no_redis_url_get_returns_none(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            cache = ApiResponseCache(redis_url="")
        assert _run(cache.get("scope", "http://x")) is None

    def test_available_false_when_disabled(self) -> None:
        cache = ApiResponseCache(enabled=False)
        assert cache.available is False


# ---------------------------------------------------------------------------
# Connected behaviour (mocked Redis)
# ---------------------------------------------------------------------------


def _make_connected_cache() -> tuple[ApiResponseCache, MagicMock]:
    """Build a cache with a mocked async Redis client already injected."""
    cache = ApiResponseCache(redis_url="redis://localhost:6379", enabled=True)
    mock_redis = MagicMock()
    mock_redis.ping = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock()
    mock_redis.aclose = AsyncMock()
    cache._redis = mock_redis
    cache._connected = True
    return cache, mock_redis


class TestCacheGetPut:
    def test_get_returns_none_on_miss(self) -> None:
        cache, mock_redis = _make_connected_cache()
        mock_redis.get = AsyncMock(return_value=None)
        assert _run(cache.get("ch_api:lookup", "http://api/company/123")) is None

    def test_put_get_roundtrip(self) -> None:
        cache, mock_redis = _make_connected_cache()
        data = {"company_name": "Acme"}

        _run(cache.put("ch_api:lookup", "http://api/company/123", data))
        mock_redis.setex.assert_called_once()

        # Simulate cache hit
        mock_redis.get = AsyncMock(return_value=json.dumps(data))
        result = _run(cache.get("ch_api:lookup", "http://api/company/123"))
        assert result == data

    def test_put_with_custom_ttl(self) -> None:
        cache, mock_redis = _make_connected_cache()
        _run(cache.put("scope", "http://x", {"a": 1}, ttl=300))
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 300  # TTL argument

    def test_get_failure_returns_none(self) -> None:
        cache, mock_redis = _make_connected_cache()
        mock_redis.get = AsyncMock(side_effect=Exception("connection lost"))
        assert _run(cache.get("scope", "http://x")) is None


# ---------------------------------------------------------------------------
# Lock behaviour
# ---------------------------------------------------------------------------


class TestLocking:
    def test_acquire_lock_success(self) -> None:
        cache, mock_redis = _make_connected_cache()
        mock_redis.set = AsyncMock(return_value=True)
        assert _run(cache.acquire_lock("scope", "http://x")) is True

    def test_acquire_lock_already_held(self) -> None:
        cache, mock_redis = _make_connected_cache()
        mock_redis.set = AsyncMock(return_value=None)  # NX failed
        assert _run(cache.acquire_lock("scope", "http://x")) is False

    def test_release_lock(self) -> None:
        cache, mock_redis = _make_connected_cache()
        _run(cache.release_lock("scope", "http://x"))
        mock_redis.delete.assert_called_once()

    def test_lock_failure_returns_true(self) -> None:
        """Fail-open: if Redis errors during lock, allow the request."""
        cache, mock_redis = _make_connected_cache()
        mock_redis.set = AsyncMock(side_effect=Exception("timeout"))
        assert _run(cache.acquire_lock("scope", "http://x")) is True


# ---------------------------------------------------------------------------
# Scoped keys
# ---------------------------------------------------------------------------


class TestScopedKeys:
    def test_different_scopes_different_keys(self) -> None:
        cache, _ = _make_connected_cache()
        key1 = cache._key("integration:ch_api:lookup", "http://api/123")
        key2 = cache._key("fragment:ch_api", "http://api/123")
        assert key1 != key2

    def test_lock_keys_include_scope(self) -> None:
        cache, _ = _make_connected_cache()
        lock_key = cache._lock_key("ch_api:lookup", "http://api/123")
        assert "ch_api:lookup" in lock_key
        assert lock_key.startswith("api_cache:lock:")


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


class TestConnectionLifecycle:
    def test_lazy_connect_on_first_get(self) -> None:
        """Connection is not attempted in __init__, only on first use."""
        cache = ApiResponseCache(redis_url="redis://localhost:6379")
        assert cache.available is False
        assert cache._redis is None

    def test_connection_failure_degrades_gracefully(self) -> None:
        cache = ApiResponseCache(redis_url="redis://nonexistent:6379")
        mock_mod = MagicMock()
        mock_client = MagicMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("refused"))
        mock_mod.from_url.return_value = mock_client
        with patch.dict("sys.modules", {"redis": MagicMock(), "redis.asyncio": mock_mod}):
            result = _run(cache.get("scope", "http://x"))
        assert result is None
        assert cache.available is False

    def test_close(self) -> None:
        cache, mock_redis = _make_connected_cache()
        _run(cache.close())
        mock_redis.aclose.assert_called_once()
        assert cache.available is False
