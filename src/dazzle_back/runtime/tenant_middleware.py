"""Tenant middleware — resolves tenant from request, routes to schema.

Resolver protocol + implementations (subdomain, header, session).
TenantMiddleware class with registry cache.
"""

import logging
import os
import time
from typing import Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60


class TenantResolver(Protocol):
    """Extracts tenant slug from a request."""

    def resolve(self, request: Request) -> str | None: ...


class SubdomainResolver:
    """Extracts tenant slug from subdomain: {slug}.{base_domain}."""

    def __init__(self, base_domain: str) -> None:
        self._base_domain = base_domain.lower()

    def resolve(self, request: Request) -> str | None:
        host = (request.url.hostname or "").lower()
        if not host or not self._base_domain:
            return None
        if not host.endswith(f".{self._base_domain}"):
            return None
        prefix = host[: -(len(self._base_domain) + 1)]
        # Take only the immediate subdomain (first segment)
        slug = prefix.split(".")[-1] if "." in prefix else prefix
        return slug if slug else None


class HeaderResolver:
    """Extracts tenant slug from an HTTP header."""

    def __init__(self, header_name: str = "X-Tenant-ID") -> None:
        self._header_name = header_name.lower()

    def resolve(self, request: Request) -> str | None:
        return request.headers.get(self._header_name) or None


class SessionResolver:
    """Extracts tenant slug from a session cookie."""

    def __init__(self, cookie_name: str = "dazzle_tenant") -> None:
        self._cookie_name = cookie_name

    def resolve(self, request: Request) -> str | None:
        return request.cookies.get(self._cookie_name) or None


def build_resolver(tenant_config: Any) -> TenantResolver:
    """Build the appropriate resolver from TenantConfig."""
    resolver_type = tenant_config.resolver
    if resolver_type == "subdomain":
        return SubdomainResolver(base_domain=tenant_config.base_domain)
    elif resolver_type == "header":
        return HeaderResolver(header_name=tenant_config.header_name)
    elif resolver_type == "session":
        return SessionResolver()
    else:
        raise ValueError(f"Unknown tenant resolver: {resolver_type}")


class _RegistryCache:
    """In-memory cache for tenant registry lookups with TTL."""

    def __init__(self, registry: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
        self._registry = registry
        self._ttl = ttl
        self._cache: dict[str, tuple[Any, float]] = {}

    def get(self, slug: str) -> Any | None:
        """Look up tenant record, using cache with TTL."""
        now = time.monotonic()
        cached = self._cache.get(slug)
        if cached and (now - cached[1]) < self._ttl:
            return cached[0]
        record = self._registry.get(slug)
        if record:
            self._cache[slug] = (record, now)
        else:
            self._cache.pop(slug, None)
        return record


_EXCLUDED_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static/",
    "/auth/",
    "/_dazzle/",
)


class TenantMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that resolves tenant and sets schema context."""

    def __init__(
        self,
        app: Any,
        resolver: TenantResolver,
        registry: Any,
        excluded_prefixes: tuple[str, ...] = _EXCLUDED_PREFIXES,
    ) -> None:
        super().__init__(app)
        self._resolver = resolver
        self._cache = _RegistryCache(registry)
        self._excluded_prefixes = excluded_prefixes

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        from .tenant_isolation import _current_tenant_schema, set_current_tenant_schema

        path = request.url.path

        # Skip excluded paths
        if any(path.startswith(p) for p in self._excluded_prefixes):
            return await call_next(request)

        # Dev override: DAZZLE_TENANT_SLUG env var
        slug = os.environ.get("DAZZLE_TENANT_SLUG") or self._resolver.resolve(request)

        if not slug:
            return JSONResponse(
                {"detail": "Tenant not specified"},
                status_code=400,
            )

        record = self._cache.get(slug)
        if not record:
            return JSONResponse(
                {"detail": f"Tenant '{slug}' not found"},
                status_code=404,
            )

        if record.status == "suspended":
            return JSONResponse(
                {"detail": f"Tenant '{slug}' is suspended"},
                status_code=503,
            )

        # Set schema context for pg_backend
        token = set_current_tenant_schema(record.schema_name)
        request.state.tenant = record

        try:
            response = await call_next(request)
        finally:
            _current_tenant_schema.reset(token)

        return response
