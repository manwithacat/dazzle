"""Apex tenant-discovery middleware — Phase B of multi-tenant login (#1404).

Fires only for an **authenticated** GET to an **apex (canonical) host** app-root
path. It resolves the identity's memberships and 302s to the org host / picker /
no-orgs per ``resolve_apex_redirect`` (the pure mapper). Every other request —
unauthenticated, non-apex host, non-root path, non-GET — passes straight through,
so it can neither loop (the single-org redirect is cross-host) nor intercept the
public apex landing for logged-out visitors.

The async DB work (membership fetch + ``tenant_id → slug``) lives here; the
decision itself is the pure mapper, keeping the routing logic exhaustively
unit-tested.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp

from dazzle.back.runtime.auth.apex_discovery import resolve_apex_redirect
from dazzle.back.runtime.tenant.resolver import _row_get

# Apex app-root entry points that trigger discovery. Deliberately tiny: never the
# /auth/* picker/no-orgs/login pages (would loop), assets, or API routes.
_APP_ROOT_PATHS = frozenset({"/", "/app", "/app/"})


class ApexDiscoveryMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        canonical_hosts: tuple[str, ...],
        domain: str,
        root_entity: str,
        root_slug_field: str,
        repositories: dict[str, Any],
    ) -> None:
        super().__init__(app)
        self._canonical_hosts = canonical_hosts
        self._domain = domain
        self._root_entity = root_entity
        self._root_slug_field = root_slug_field
        self._repositories = repositories

    async def _slug_for_tenant(self, tenant_id: str) -> str | None:
        repo = self._repositories.get(self._root_entity)
        if repo is None:
            return None
        result = await repo.list(filters={"id": tenant_id}, page_size=1)
        items = result.get("items") or []
        if not items:
            return None
        slug = _row_get(items[0], self._root_slug_field)
        return str(slug) if slug else None

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method != "GET":
            return await call_next(request)
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in self._canonical_hosts:
            return await call_next(request)
        if request.url.path not in _APP_ROOT_PATHS:
            return await call_next(request)

        from dazzle.back.runtime.auth.current import current_user_id

        uid = current_user_id(request)
        if uid is None:
            return await call_next(request)  # logged-out visitor → public apex landing

        store = getattr(getattr(request, "app", None), "state", None)
        auth_store = getattr(store, "auth_store", None)
        if auth_store is None:
            return await call_next(request)

        memberships = auth_store.get_memberships_for_identity(uid)
        # Only the single-active-membership case needs a slug (→ org-host redirect); the
        # picker (≥2) and no-orgs (0) outcomes resolve to fixed apex paths. So resolve at
        # most ONE slug here (never wasted DB work on the picker/no-orgs paths), and keep
        # the decision in the pure/sync mapper.
        active = [m for m in memberships if getattr(m, "status", None) == "active"]
        slug_map: dict[str, str] = {}
        if len(active) == 1:
            slug = await self._slug_for_tenant(active[0].tenant_id)
            if slug:
                slug_map[active[0].tenant_id] = slug

        memberships_required = bool(getattr(store, "memberships_required", False))
        target = resolve_apex_redirect(
            memberships,
            domain=self._domain,
            slug_for_tenant=lambda tid: slug_map.get(tid),
            memberships_required=memberships_required,
        )
        if target:
            return RedirectResponse(target, status_code=302)
        return await call_next(request)
