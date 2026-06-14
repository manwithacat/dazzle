"""TenantResolutionMiddleware (#1289 slice 3).

Resolves the Host header to a tenant before any downstream route or
auth dependency runs. See the design spec for the full lifecycle.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.types import ASGIApp

from dazzle.back.runtime.slug_validator import validate_slug
from dazzle.back.runtime.tenant.cache import NEGATIVE, TenantCache
from dazzle.back.runtime.tenant.resolver import (
    ExpiredHistoryHit,
    HistoryHit,
    ResolvedTenant,
    Resolver,
)

logger = logging.getLogger("dazzle.tenant")


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


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, binding: TenantHostBinding) -> None:
        super().__init__(app)
        self._b = binding

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = (request.headers.get("host") or "").split(":")[0].lower()

        if host in self._b.canonical_hosts:
            request.state.tenant = None
            return await call_next(request)

        suffix = "." + self._b.domain
        if not host.endswith(suffix):
            return Response("Bad Host", status_code=400)

        slug = host[: -len(suffix)]
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
        request.state.tenant = result
        # #1394: bind the host tenant id for `current_tenant` scope predicates +
        # the dazzle.host_tenant_id GUC. Reset on exit so it never leaks across
        # requests sharing this context (mirrors the schema-token pattern).
        from dazzle.back.runtime.tenant_isolation import (
            _current_host_tenant_id,
            set_current_host_tenant_id,
        )

        token = set_current_host_tenant_id(str(result.id))
        try:
            return await call_next(request)
        finally:
            _current_host_tenant_id.reset(token)
