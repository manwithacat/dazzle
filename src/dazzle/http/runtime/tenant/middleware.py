"""TenantResolutionMiddleware (#1289 slice 3).

Resolves the Host header to a tenant before any downstream route or
auth dependency runs. See the design spec for the full lifecycle.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.types import ASGIApp

from dazzle.http.runtime.slug_validator import validate_slug
from dazzle.http.runtime.tenant.cache import NEGATIVE, TenantCache
from dazzle.http.runtime.tenant.resolver import (
    ExpiredHistoryHit,
    HistoryHit,
    ResolvedTenant,
    Resolver,
    _maybe_await,
)

AliasLookup = Callable[[str], ResolvedTenant | None | Awaitable[ResolvedTenant | None]]

logger = logging.getLogger(__name__)

# Demo / QA capture on apex (localhost): force host-tenant bind so
# `current_tenant` scopes populate job desks without real DNS subdomains.
# Set by recapture_demo_fleet for tenant_host examples (e.g. domain_join_co).
_HOST_TENANT_SLUG_ENV = "DAZZLE_HOST_TENANT_SLUG"


NotFoundRenderer = Callable[[str], str]
ExpiredRenderer = Callable[[str, str, str], str]


@dataclass(frozen=True)
class TenantHostBinding:
    """Per-domain configuration for the resolution middleware."""

    app_name: str
    domain: str
    canonical_hosts: tuple[str, ...]
    cache: TenantCache
    resolver: Resolver
    not_found_renderer: NotFoundRenderer
    expired_renderer: ExpiredRenderer
    # ADR-0055: leftover tokens never invent B. Empty / unknown ≠ slug extract.
    topology: str = ""
    # Composing alias probe (PR4). None = no table wired; Host falls through to A/B.
    alias_lookup: AliasLookup | None = None
    alias_cache: TenantCache | None = None


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, binding: TenantHostBinding) -> None:
        super().__init__(app)
        self._b = binding

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = (request.headers.get("host") or "").split(":")[0].lower()
        path = request.url.path or ""

        # Demo override — bind a known slug even on canonical hosts (localhost).
        # Skip /__test__ so reset-and-load can seed before the slug exists.
        demo_slug = (os.environ.get(_HOST_TENANT_SLUG_ENV) or "").strip().lower()
        if demo_slug and not path.startswith("/__test__"):
            return await self._dispatch_slug(request, call_next, demo_slug, host=host)

        if host in self._b.canonical_hosts:
            request.state.tenant = None
            return await call_next(request)

        # ADR-0055 PR4: alias table before B slug parse / A unknown-Host 400.
        try:
            aliased = await self._probe_alias(host)
        except Exception:
            logger.exception("alias lookup failed for %s", host)
            return Response("Tenant lookup failed", status_code=502)
        if aliased is not None:
            return await self._bind_and_call(request, call_next, aliased)

        # ADR-0055 topology A: Host does not name a tenant. Leftover labels
        # are not slugs — 400 rather than inventing B.
        if self._b.topology != "provider_subdomain":
            return Response("Bad Host", status_code=400)

        suffix = "." + self._b.domain
        if not host.endswith(suffix):
            return Response("Bad Host", status_code=400)

        slug = host[: -len(suffix)]
        return await self._dispatch_slug(request, call_next, slug, host=host)

    async def _dispatch_slug(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        slug: str,
        *,
        host: str,
    ) -> Response:
        try:
            validate_slug(slug)
        except ValueError:
            return HTMLResponse(self._b.not_found_renderer(host), status_code=404)  # nosemgrep

        cached = self._b.cache.get(slug)
        if cached is NEGATIVE:
            return HTMLResponse(self._b.not_found_renderer(host), status_code=404)  # nosemgrep

        result = cached
        if result is None:
            try:
                result = await self._b.resolver.lookup(slug)
            except Exception:
                logger.exception("tenant resolver lookup failed for %s", slug)
                return Response("Tenant lookup failed", status_code=502)
            self._b.cache.set(slug, result if result is not None else NEGATIVE)

        if result is None:
            return HTMLResponse(self._b.not_found_renderer(host), status_code=404)  # nosemgrep

        if isinstance(result, HistoryHit):
            target = f"https://{result.new_slug}.{self._b.domain}/"
            return RedirectResponse(target, status_code=301)

        if isinstance(result, ExpiredHistoryHit):
            body = self._b.expired_renderer(result.old_slug, result.new_slug, self._b.domain)
            return HTMLResponse(body, status_code=410)  # nosemgrep

        assert isinstance(result, ResolvedTenant)
        return await self._bind_and_call(request, call_next, result)

    async def _probe_alias(self, host: str) -> ResolvedTenant | None:
        lookup = self._b.alias_lookup
        if lookup is None:
            return None
        cache = self._b.alias_cache
        if cache is not None:
            cached = cache.get(host)
            if cached is NEGATIVE:
                return None
            if isinstance(cached, ResolvedTenant):
                return cached
        raw = await _maybe_await(lookup(host))
        result = raw if isinstance(raw, ResolvedTenant) else None
        if cache is None:
            return result
        if result is not None:
            cache.set(host, result)
            return result
        # Negative-cache leftover hosts on A only. On B the miss may still be a slug.
        if self._b.topology != "provider_subdomain":
            cache.set(host, NEGATIVE)
        return None

    async def _bind_and_call(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        result: ResolvedTenant,
    ) -> Response:
        request.state.tenant = result
        # #1394: bind the host tenant id for `current_tenant` scope predicates +
        # the dazzle.host_tenant_id GUC. Reset on exit so it never leaks across
        # requests sharing this context (mirrors the schema-token pattern).
        from dazzle.http.runtime.tenant_isolation import (
            _current_host_tenant_id,
            set_current_host_tenant_id,
        )

        token = set_current_host_tenant_id(str(result.id))
        try:
            return await call_next(request)
        finally:
            _current_host_tenant_id.reset(token)
