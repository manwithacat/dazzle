"""Tenant middleware — resolves tenant from Host, routes to schema.

Schema isolation uses the same Host story as ``tenant_host:`` (ADR-0055 PR3).
Client-named tenant (``X-Tenant-ID``, session cookie) is not a resolver.
``DAZZLE_TENANT_SLUG`` remains a server override.
"""

from __future__ import annotations  # required: forward reference

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


def build_resolver(tenant_config: Any) -> TenantResolver:
    """Host parser only. Leftover ``header`` / ``session`` tokens stay put."""
    resolver_type = getattr(tenant_config, "resolver", "") or "subdomain"
    if resolver_type == "subdomain":
        return SubdomainResolver(base_domain=tenant_config.base_domain)
    raise ValueError(
        f"Unknown tenant resolver: {resolver_type!r}. "
        "Host is the tenant parser (tenant_host:); header/session were removed (ADR-0055)."
    )


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
        per_tenant_config_schema: dict[str, str] | None = None,
    ) -> None:
        super().__init__(app)
        self._resolver = resolver
        self._cache = _RegistryCache(registry)
        self._excluded_prefixes = excluded_prefixes
        # #957 cycle 8 — DSL-declared `tenancy: per_tenant_config:`
        # schema, used to coerce the JSONB config into typed values
        # exposed via `request.state.tenant_config`. None / empty
        # means apps without a per_tenant_config block — the request
        # state attribute is set to {} so callers can index without
        # guarding for absence.
        self._per_tenant_config_schema = per_tenant_config_schema or {}

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        from .tenant_isolation import _current_tenant_schema, set_current_tenant_schema

        path = request.url.path

        # Skip excluded paths
        if any(path.startswith(p) for p in self._excluded_prefixes):
            return await call_next(request)

        # Server override, then tenant_host ResolvedTenant, then Host slug.
        # Leftover X-Tenant-ID / dazzle_tenant cookie are not resolvers.
        slug = (os.environ.get("DAZZLE_TENANT_SLUG") or "").strip() or None
        if not slug:
            resolved = getattr(request.state, "tenant", None)
            host_slug = getattr(resolved, "slug", None) if resolved is not None else None
            slug = str(host_slug) if host_slug else self._resolver.resolve(request)

        if not slug:
            marker = getattr(getattr(request, "app", None), "state", None)
            topology = (
                getattr(getattr(marker, "tenant_host", None), "topology", "")
                if marker is not None
                else ""
            )
            if topology == "apex":
                return await call_next(request)
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

        # #957 cycle 8 — coerce per-tenant config against the
        # DSL-declared schema and expose on request.state. Empty
        # schema produces an empty dict (no risk of KeyError on the
        # callers' side since they iterate the schema's known keys).
        from dazzle.tenant.config_coercion import coerce_config

        request.state.tenant_config = coerce_config(
            getattr(record, "config", None),
            self._per_tenant_config_schema,
        )

        try:
            response = await call_next(request)
        finally:
            _current_tenant_schema.reset(token)

        return response
