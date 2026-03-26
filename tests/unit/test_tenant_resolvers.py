"""Tests for tenant resolver implementations."""

from unittest.mock import MagicMock

import pytest


def _make_request(
    *, host: str = "localhost", headers: dict | None = None, cookies: dict | None = None
) -> MagicMock:
    """Create a mock Starlette Request."""
    request = MagicMock()
    request.headers = headers or {}
    request.cookies = cookies or {}
    url = MagicMock()
    url.hostname = host
    request.url = url
    return request


class TestSubdomainResolver:
    def test_extracts_slug_from_subdomain(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SubdomainResolver

        resolver = SubdomainResolver(base_domain="app.example.com")
        request = _make_request(host="cyfuture.app.example.com")
        assert resolver.resolve(request) == "cyfuture"

    def test_returns_none_for_bare_domain(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SubdomainResolver

        resolver = SubdomainResolver(base_domain="app.example.com")
        request = _make_request(host="app.example.com")
        assert resolver.resolve(request) is None

    def test_returns_none_for_localhost(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SubdomainResolver

        resolver = SubdomainResolver(base_domain="app.example.com")
        request = _make_request(host="localhost")
        assert resolver.resolve(request) is None

    def test_multi_level_subdomain(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SubdomainResolver

        resolver = SubdomainResolver(base_domain="app.example.com")
        request = _make_request(host="deep.cyfuture.app.example.com")
        slug = resolver.resolve(request)
        assert slug is not None


class TestHeaderResolver:
    def test_extracts_from_header(self) -> None:
        from dazzle_back.runtime.tenant_middleware import HeaderResolver

        resolver = HeaderResolver(header_name="X-Tenant-ID")
        request = _make_request(headers={"x-tenant-id": "cyfuture"})
        assert resolver.resolve(request) == "cyfuture"

    def test_returns_none_when_missing(self) -> None:
        from dazzle_back.runtime.tenant_middleware import HeaderResolver

        resolver = HeaderResolver(header_name="X-Tenant-ID")
        request = _make_request()
        assert resolver.resolve(request) is None

    def test_custom_header_name(self) -> None:
        from dazzle_back.runtime.tenant_middleware import HeaderResolver

        resolver = HeaderResolver(header_name="X-Custom")
        request = _make_request(headers={"x-custom": "myco"})
        assert resolver.resolve(request) == "myco"


class TestSessionResolver:
    def test_extracts_from_cookie(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SessionResolver

        resolver = SessionResolver()
        request = _make_request(cookies={"dazzle_tenant": "cyfuture"})
        assert resolver.resolve(request) == "cyfuture"

    def test_returns_none_when_no_cookie(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SessionResolver

        resolver = SessionResolver()
        request = _make_request()
        assert resolver.resolve(request) is None


class TestBuildResolver:
    def test_builds_subdomain_resolver(self) -> None:
        from dazzle.core.manifest import TenantConfig
        from dazzle_back.runtime.tenant_middleware import build_resolver

        config = TenantConfig(resolver="subdomain", base_domain="app.example.com")
        resolver = build_resolver(config)
        assert resolver is not None

    def test_builds_header_resolver(self) -> None:
        from dazzle.core.manifest import TenantConfig
        from dazzle_back.runtime.tenant_middleware import build_resolver

        config = TenantConfig(resolver="header", header_name="X-My-Tenant")
        resolver = build_resolver(config)
        assert resolver is not None

    def test_builds_session_resolver(self) -> None:
        from dazzle.core.manifest import TenantConfig
        from dazzle_back.runtime.tenant_middleware import build_resolver

        config = TenantConfig(resolver="session")
        resolver = build_resolver(config)
        assert resolver is not None

    def test_unknown_resolver_raises(self) -> None:
        from dazzle.core.manifest import TenantConfig
        from dazzle_back.runtime.tenant_middleware import build_resolver

        config = TenantConfig(resolver="magic")
        with pytest.raises(ValueError, match="Unknown tenant resolver"):
            build_resolver(config)
