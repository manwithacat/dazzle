"""Tests for TenantMiddleware dispatch — error cases and happy path."""

from unittest.mock import MagicMock

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dazzle_back.runtime.tenant_middleware import HeaderResolver, TenantMiddleware


def _make_app(registry_records: dict[str, MagicMock] | None = None) -> Starlette:
    """Build a minimal Starlette app with TenantMiddleware."""

    async def homepage(request):  # type: ignore[no-untyped-def]
        tenant = getattr(request.state, "tenant", None)
        slug = tenant.slug if tenant else "none"
        return PlainTextResponse(f"tenant={slug}")

    async def health(request):  # type: ignore[no-untyped-def]
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/", homepage),
            Route("/health", health),
        ]
    )

    registry = MagicMock()

    def mock_get(slug: str) -> MagicMock | None:
        if registry_records:
            return registry_records.get(slug)
        return None

    registry.get = mock_get

    resolver = HeaderResolver(header_name="X-Tenant-ID")
    app.add_middleware(
        TenantMiddleware,
        resolver=resolver,
        registry=registry,
    )
    return app


class TestMiddlewareExcludedPaths:
    def test_health_bypasses_tenant(self) -> None:
        app = _make_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.text == "ok"


class TestMiddlewareErrors:
    def test_missing_tenant_returns_400(self) -> None:
        app = _make_app()
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 400
        assert "Tenant not specified" in response.json()["detail"]

    def test_unknown_tenant_returns_404(self) -> None:
        app = _make_app()
        client = TestClient(app)
        response = client.get("/", headers={"X-Tenant-ID": "nonexistent"})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_suspended_tenant_returns_503(self) -> None:
        record = MagicMock(slug="cyfuture", schema_name="tenant_cyfuture", status="suspended")
        app = _make_app({"cyfuture": record})
        client = TestClient(app)
        response = client.get("/", headers={"X-Tenant-ID": "cyfuture"})
        assert response.status_code == 503
        assert "suspended" in response.json()["detail"]


class TestRegistryCache:
    def test_cache_hit_avoids_second_lookup(self) -> None:
        from dazzle_back.runtime.tenant_middleware import _RegistryCache

        registry = MagicMock()
        record = MagicMock(slug="cyfuture", status="active")
        registry.get.return_value = record

        cache = _RegistryCache(registry, ttl=60)
        result1 = cache.get("cyfuture")
        result2 = cache.get("cyfuture")

        assert result1 is record
        assert result2 is record
        assert registry.get.call_count == 1  # only one DB call

    def test_cache_miss_returns_none(self) -> None:
        from dazzle_back.runtime.tenant_middleware import _RegistryCache

        registry = MagicMock()
        registry.get.return_value = None

        cache = _RegistryCache(registry, ttl=60)
        assert cache.get("nonexistent") is None

    def test_expired_entry_triggers_fresh_lookup(self) -> None:
        import time

        from dazzle_back.runtime.tenant_middleware import _RegistryCache

        registry = MagicMock()
        record = MagicMock(slug="cyfuture", status="active")
        registry.get.return_value = record

        cache = _RegistryCache(registry, ttl=0)  # TTL of 0 = always expired
        cache.get("cyfuture")
        time.sleep(0.01)
        cache.get("cyfuture")

        assert registry.get.call_count == 2  # two DB calls


class TestMiddlewareHappyPath:
    def test_active_tenant_sets_context(self) -> None:
        record = MagicMock(slug="cyfuture", schema_name="tenant_cyfuture", status="active")
        app = _make_app({"cyfuture": record})
        client = TestClient(app)
        response = client.get("/", headers={"X-Tenant-ID": "cyfuture"})
        assert response.status_code == 200
        assert "tenant=cyfuture" in response.text
