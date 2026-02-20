"""Tests for MappingExecutor + ApiResponseCache integration."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from dazzle.core.ir.integrations import (
    Expression,
    HttpMethod,
    HttpRequestSpec,
    IntegrationMapping,
    IntegrationSpec,
    MappingRule,
    MappingTriggerSpec,
    MappingTriggerType,
)
from dazzle_back.runtime.api_cache import ApiResponseCache
from dazzle_back.runtime.event_bus import EntityEventBus
from dazzle_back.runtime.mapping_executor import MappingExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_cache_mock() -> ApiResponseCache:
    """Create a cache mock with async methods."""
    cache = MagicMock(spec=ApiResponseCache)
    cache.get = AsyncMock(return_value=None)
    cache.put = AsyncMock()
    cache.acquire_lock = AsyncMock(return_value=True)
    cache.release_lock = AsyncMock()
    return cache


def _make_mapping(
    name: str = "lookup",
    method: HttpMethod = HttpMethod.GET,
    url_template: str = "/company/{self.company_number}",
    cache_ttl: int | None = None,
    response_mapping: list[MappingRule] | None = None,
) -> IntegrationMapping:
    return IntegrationMapping(
        name=name,
        entity_ref="Company",
        triggers=[MappingTriggerSpec(trigger_type=MappingTriggerType.MANUAL, label="Run")],
        request=HttpRequestSpec(method=method, url_template=url_template),
        response_mapping=response_mapping
        or [
            MappingRule(target_field="name", source=Expression(path="response.company_name")),
        ],
        cache_ttl=cache_ttl,
    )


def _make_integration(
    mappings: list[IntegrationMapping] | None = None,
) -> IntegrationSpec:
    return IntegrationSpec(
        name="ch_api",
        base_url="https://api.example.com",
        mappings=mappings or [],
    )


def _mock_http_response(data: dict[str, Any], status: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = data
    mock_resp.text = str(data)

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Cache integration tests
# ---------------------------------------------------------------------------


class TestCacheHit:
    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_get_cached_on_success(self, mock_client_cls: MagicMock) -> None:
        """Successful GET response is cached."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Acme"})
        cache = _make_cache_mock()

        mapping = _make_mapping()
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        result = _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        assert result.success is True
        cache.put.assert_called_once()
        # Verify scope and TTL
        put_args = cache.put.call_args
        assert put_args[0][0] == "ch_api:lookup"  # scope

    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_cache_hit_skips_http(self, mock_client_cls: MagicMock) -> None:
        """On cache hit, HTTP call is not made."""
        cache = _make_cache_mock()
        cache.get = AsyncMock(return_value={"company_name": "Cached"})

        mapping = _make_mapping()
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        result = _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        assert result.success is True
        assert result.cache_hit is True
        assert result.mapped_fields == {"name": "Cached"}
        mock_client_cls.return_value.request.assert_not_called()


class TestPostNotCached:
    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_post_request_not_cached(self, mock_client_cls: MagicMock) -> None:
        """POST requests are never cached."""
        mock_client_cls.return_value = _mock_http_response({"id": "new-1"}, status=201)
        cache = _make_cache_mock()

        mapping = _make_mapping(method=HttpMethod.POST, url_template="/resources")
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        result = _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        assert result.success is True
        cache.get.assert_not_called()
        cache.put.assert_not_called()


class TestForceRefresh:
    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_force_refresh_bypasses_cache(self, mock_client_cls: MagicMock) -> None:
        """force_refresh=True skips cache read."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Fresh"})
        cache = _make_cache_mock()
        cache.get = AsyncMock(return_value={"company_name": "Stale"})

        mapping = _make_mapping()
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        result = _run(
            executor.execute_manual(
                "ch_api", "lookup", {"company_number": "123"}, force_refresh=True
            )
        )

        assert result.success is True
        assert result.cache_hit is False
        # Cache get should NOT be called because force_refresh skips the check
        cache.get.assert_not_called()

    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_force_refresh_bypasses_dedup_lock(self, mock_client_cls: MagicMock) -> None:
        """force_refresh=True also bypasses the dedup lock."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Fresh"})
        cache = _make_cache_mock()
        cache.acquire_lock = AsyncMock(return_value=False)  # Lock held

        mapping = _make_mapping()
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        result = _run(
            executor.execute_manual(
                "ch_api", "lookup", {"company_number": "123"}, force_refresh=True
            )
        )

        assert result.success is True
        # Lock should not even be checked
        cache.acquire_lock.assert_not_called()


class TestLockRelease:
    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_lock_released_after_request(self, mock_client_cls: MagicMock) -> None:
        """Dedup lock is released after HTTP response."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Acme"})
        cache = _make_cache_mock()

        mapping = _make_mapping()
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        cache.release_lock.assert_called_once()

    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_lock_released_on_failure(self, mock_client_cls: MagicMock) -> None:
        """Dedup lock is released even if request fails."""
        mock_client_cls.return_value = _mock_http_response({"error": "not found"}, status=404)
        cache = _make_cache_mock()

        mapping = _make_mapping()
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        cache.release_lock.assert_called_once()


class TestCacheTtl:
    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_mapping_cache_ttl_used(self, mock_client_cls: MagicMock) -> None:
        """When mapping has cache_ttl, it should be passed to cache.put."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Acme"})
        cache = _make_cache_mock()

        mapping = _make_mapping(cache_ttl=300)  # 5 minutes
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        put_kwargs = cache.put.call_args
        assert put_kwargs[1]["ttl"] == 300

    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_default_ttl_when_no_cache_ttl(self, mock_client_cls: MagicMock) -> None:
        """When mapping has no cache_ttl, default 86400 is used."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Acme"})
        cache = _make_cache_mock()

        mapping = _make_mapping(cache_ttl=None)
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        put_kwargs = cache.put.call_args
        assert put_kwargs[1]["ttl"] == 86400


class TestPackTtlFallback:
    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_pack_ttl_used_when_mapping_has_none(self, mock_client_cls: MagicMock) -> None:
        """When mapping.cache_ttl is None, pack foreign_model cache_ttl is used."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Acme"})
        cache = _make_cache_mock()

        mapping = _make_mapping(cache_ttl=None)
        integration = _make_integration(mappings=[mapping])
        # Set up api_refs so the executor can find the pack
        integration = IntegrationSpec(
            name="ch_api",
            base_url="https://api.example.com",
            api_refs=["chapi"],
            mappings=[mapping],
        )

        # Create a mock service with pack reference
        svc = MagicMock()
        svc.name = "chapi"
        svc.spec_inline = "pack:companies_house_lookup"
        appspec = MagicMock(integrations=[integration], services=[svc])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        put_kwargs = cache.put.call_args
        # companies_house_lookup Company model has cache_ttl=86400
        assert put_kwargs[1]["ttl"] == 86400

    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_mapping_ttl_takes_precedence_over_pack(self, mock_client_cls: MagicMock) -> None:
        """mapping.cache_ttl should take precedence over pack cache_ttl."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Acme"})
        cache = _make_cache_mock()

        mapping = _make_mapping(cache_ttl=120)  # Explicit 2 minutes
        integration = IntegrationSpec(
            name="ch_api",
            base_url="https://api.example.com",
            api_refs=["chapi"],
            mappings=[mapping],
        )

        svc = MagicMock()
        svc.name = "chapi"
        svc.spec_inline = "pack:companies_house_lookup"
        appspec = MagicMock(integrations=[integration], services=[svc])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=cache)
        _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        put_kwargs = cache.put.call_args
        assert put_kwargs[1]["ttl"] == 120  # mapping TTL, not pack's 86400


class TestNoCacheProvided:
    @patch("dazzle_back.runtime.mapping_executor.httpx.AsyncClient")
    def test_no_cache_no_caching(self, mock_client_cls: MagicMock) -> None:
        """When cache=None, no caching is attempted."""
        mock_client_cls.return_value = _mock_http_response({"company_name": "Acme"})

        mapping = _make_mapping()
        integration = _make_integration(mappings=[mapping])
        appspec = MagicMock(integrations=[integration])
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus, cache=None)
        result = _run(executor.execute_manual("ch_api", "lookup", {"company_number": "123"}))

        assert result.success is True
        assert result.cache_hit is False
