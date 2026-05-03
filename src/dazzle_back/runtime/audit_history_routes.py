"""HTMX-loaded audit-history fragment route (#956 cycle 11).

Detail-view templates with `show_history: true` (cycle 8 / cycle 10)
include an HTMX placeholder that GETs ``/_dazzle/audit-history/{type}/{id}``.
This module provides the route factory that returns the rendered
fragment via cycle-9's ``render_audit_history_region``.

Distinct from `audit_routes.py` — that's the compliance AuditLogger
under `/api/_audit/...`. This is the user-visible change-history
primitive under `/_dazzle/audit-history/...`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from starlette.responses import HTMLResponse

logger = logging.getLogger(__name__)


def create_audit_history_routes(
    *,
    audit_service: Any,
    audits: list[Any],
    auth_dep: Callable[..., Any] | None = None,
) -> APIRouter:
    """Build the ``/_dazzle/audit-history`` router.

    Args:
        audit_service: The framework's ``AuditEntry`` service from
            ``server.services["AuditEntry"]``. None / missing is
            handled by ``render_audit_history_region`` returning the
            empty-state markup; the route still 200s with valid HTML.
        audits: The AppSpec's `audits` list — used to find the
            matching AuditSpec for `entity_type` and check
            `show_to:` RBAC.
        auth_dep: Optional FastAPI dep returning an AuthContext-like
            object with ``user.roles``. When None (no auth gate
            configured) the request runs as the anonymous viewer
            with no personas — RBAC will deny on any restricted
            audit block.

    Returns:
        APIRouter with prefix ``/_dazzle/audit-history`` and a single
        ``GET /{entity_type}/{entity_id}`` route.
    """
    router = APIRouter(prefix="/_dazzle/audit-history", tags=["Audit History"])

    if auth_dep is not None:

        @router.get("/{entity_type}/{entity_id}", response_class=HTMLResponse)
        async def get_audit_history_with_auth(
            entity_type: str,
            entity_id: str,
            auth_context: Any = Depends(auth_dep),
        ) -> HTMLResponse:
            html = await _render(
                audit_service=audit_service,
                audits=audits,
                entity_type=entity_type,
                entity_id=entity_id,
                auth_context=auth_context,
            )
            return HTMLResponse(content=html)

        return router

    @router.get("/{entity_type}/{entity_id}", response_class=HTMLResponse)
    async def get_audit_history(
        entity_type: str,
        entity_id: str,
    ) -> HTMLResponse:
        html = await _render(
            audit_service=audit_service,
            audits=audits,
            entity_type=entity_type,
            entity_id=entity_id,
            auth_context=None,
        )
        return HTMLResponse(content=html)

    return router


async def _render(
    *,
    audit_service: Any,
    audits: list[Any],
    entity_type: str,
    entity_id: str,
    auth_context: Any,
) -> str:
    """Extract personas from the auth context, then delegate to
    ``render_audit_history_region``."""
    from dazzle_back.runtime.audit_region import render_audit_history_region

    return await render_audit_history_region(
        audit_service=audit_service,
        audits=audits,
        entity_type=entity_type,
        entity_id=entity_id,
        viewer_personas=_extract_personas(auth_context),
    )


def _extract_personas(auth_context: Any) -> list[str]:
    """Pull persona / role names off the auth_context, or `[]`.

    Tolerant of any AuthContext shape — the existing app may carry
    `user.roles` as strings or as objects with `.name`. Returns an
    empty list when the user is unauthenticated; the visibility
    gate then denies any restricted audit block (deny-by-default).
    """
    if auth_context is None or not getattr(auth_context, "is_authenticated", False):
        return []
    user = getattr(auth_context, "user", None)
    if user is None:
        return []
    raw_roles = getattr(user, "roles", []) or []
    out: list[str] = []
    for r in raw_roles:
        if isinstance(r, str):
            out.append(r.removeprefix("role_"))
        else:
            name = getattr(r, "name", None)
            if name:
                out.append(str(name).removeprefix("role_"))
    return out
