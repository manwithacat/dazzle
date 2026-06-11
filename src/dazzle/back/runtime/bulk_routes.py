"""Bulk-action endpoints derived from surface ``ux: bulk_actions:`` (#785).

When a list-mode surface declares bulk actions in its ``ux:`` block, the
runtime mounts a single ``POST /api/{entity_plural}/bulk`` endpoint that
applies a named field transition to every supplied id.

RBAC (#1170): the bulk endpoint enforces the same authorization as the
generated single-record UPDATE route — an entity-level Cedar permit gate
plus a per-id ``scope:`` check via :func:`_scoped_pre_read`. Ids the
caller cannot scope to are reported as ``not_found`` (the same IDOR-safe
shape the single-record route uses), never silently mutated. The actual
field patch still goes through ``repo.update`` directly — it is a
constrained, per-item transition with no user-supplied payload to
validate.

When the app has no auth configured at all (``optional_auth_dep`` is
``None``) the endpoint applies actions unenforced — consistent with the
rest of that app having no RBAC.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from dazzle.back.runtime.audit_wrap import (
    _build_access_context,
    _record_to_dict,
)
from dazzle.back.runtime.scope_filters import _scoped_pre_read
from dazzle.core.access import AccessOperationKind
from dazzle.core.ir import BulkActionSpec
from dazzle.core.strings import to_api_plural
from dazzle.render.access_evaluator import evaluate_permission

logger = logging.getLogger(__name__)


async def _no_auth() -> None:
    """Auth dependency stand-in for apps with no auth configured."""
    return None


def _build_entity_bulk_actions(surfaces: list[Any]) -> dict[str, list[BulkActionSpec]]:
    """Collect bulk action specs per entity from list-mode surfaces."""
    result: dict[str, list[BulkActionSpec]] = {}
    for surface in surfaces:
        entity_ref = getattr(surface, "entity_ref", None)
        if not entity_ref:
            continue
        mode = str(getattr(surface, "mode", "") or "").lower()
        if mode != "list":
            continue
        ux = getattr(surface, "ux", None)
        if ux is None:
            continue
        actions = getattr(ux, "bulk_actions", None) or []
        if not actions:
            continue
        # First surface per entity wins; duplicate surfaces are ignored.
        result.setdefault(entity_ref, list(actions))
    return result


def create_bulk_routes(
    surfaces: list[Any],
    *,
    repositories: dict[str, Any],
    services: dict[str, Any],
    cedar_access_specs: dict[str, Any],
    fk_graph: Any,
    optional_auth_dep: Any,
    admin_personas: list[str] | None = None,
) -> APIRouter | None:
    """Register ``POST /api/{plural}/bulk`` for every bulk-action-bearing entity.

    Returns ``None`` when no surface declares bulk actions so apps that
    don't need the feature get a clean OpenAPI surface.

    Args:
        surfaces: AppSpec surfaces — scanned for ``ux: bulk_actions:`` blocks.
        repositories: ``{entity_name: Repository}`` — used for the field patch.
        services: ``{entity_name: BaseService}`` — used for the scope-aware
            pre-read that enforces ``scope:`` rules per id.
        cedar_access_specs: ``{entity_name: EntityAccessSpec}`` — the Cedar
            permit/scope model. An entity absent here has no access rules.
        fk_graph: FK graph for scope-predicate compilation.
        optional_auth_dep: FastAPI dependency resolving the current user.
            ``None`` when the app has no auth — the endpoint then runs
            unenforced, consistent with the app's other routes.
        admin_personas: Tenant-admin persona allow-list (scope bypass).
    """
    entity_actions = _build_entity_bulk_actions(surfaces)

    # An entity needs a repo to mutate; when auth is enforced it also
    # needs a service for the scope-aware pre-read. Skip any that lacks
    # what it needs so we never expose an unenforceable bulk route.
    registerable: dict[str, list[BulkActionSpec]] = {}
    for name, actions in entity_actions.items():
        if name not in repositories:
            continue
        if optional_auth_dep is not None and name not in services:
            logger.warning("Bulk actions on %s skipped — no service for scope enforcement", name)
            continue
        registerable[name] = actions

    if not registerable:
        return None

    router = APIRouter(tags=["Bulk Actions"])

    for entity_name, actions in registerable.items():
        _register_bulk_route(
            router,
            entity_name,
            actions,
            repo=repositories[entity_name],
            service=services.get(entity_name),
            cedar_spec=cedar_access_specs.get(entity_name),
            fk_graph=fk_graph,
            optional_auth_dep=optional_auth_dep,
            admin_personas=admin_personas,
        )

    return router


def _register_bulk_route(
    router: APIRouter,
    entity_name: str,
    actions: list[BulkActionSpec],
    *,
    repo: Any,
    service: Any,
    cedar_spec: Any,
    fk_graph: Any,
    optional_auth_dep: Any,
    admin_personas: list[str] | None,
) -> None:
    """Wire one entity's bulk endpoint with RBAC + scope enforcement."""
    action_map = {a.name: a for a in actions}
    path = f"/api/{to_api_plural(entity_name)}/bulk"
    auth_dep = optional_auth_dep if optional_auth_dep is not None else _no_auth

    async def bulk_action_handler(
        request: Request,
        auth_context: Any = Depends(auth_dep),
    ) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(content={"error": "Body must be valid JSON"}, status_code=400)

        action_name = str(body.get("action", ""))
        ids = body.get("ids")

        if action_name not in action_map:
            return JSONResponse(
                content={
                    "error": f"Unknown action {action_name!r} for {entity_name}",
                    "actions": sorted(action_map.keys()),
                },
                status_code=422,
            )
        if not isinstance(ids, list) or not ids:
            return JSONResponse(
                content={"error": "`ids` must be a non-empty list"},
                status_code=422,
            )

        spec = action_map[action_name]
        update_payload = {spec.field: spec.target_value}

        # `auth_context is None` ⟺ the app has no auth configured; the
        # real optional-auth dependency always returns an AuthContext
        # (possibly unauthenticated). Only enforce when auth exists.
        enforce = auth_context is not None
        ctx: Any = None
        if enforce:
            _user, ctx = _build_access_context(auth_context, admin_personas)
            # Entity-level permit gate — mirrors the generated UPDATE route.
            # A categorically-denied role fails the whole request with 403.
            if cedar_spec is not None:
                gate = evaluate_permission(
                    cedar_spec, AccessOperationKind.UPDATE, None, ctx, entity_name=entity_name
                )
                if not gate.allowed:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Not permitted to perform bulk actions on {entity_name}",
                    )

        results: list[dict[str, Any]] = []
        ok_count = 0

        for raw_id in ids:
            item_id = str(raw_id)
            try:
                if enforce:
                    # Row-level scope check. Ids outside the caller's
                    # scope come back as None → reported as not_found,
                    # the same IDOR-safe shape the single-record route
                    # uses (scope-denied is indistinguishable from absent).
                    existing = await _scoped_pre_read(
                        service=service,
                        operation="update",
                        id=item_id,
                        cedar_access_spec=cedar_spec,
                        auth_context=auth_context,
                        entity_name=entity_name,
                        fk_graph=fk_graph,
                        admin_personas=admin_personas,
                    )
                    if existing is None:
                        results.append({"id": item_id, "ok": False, "error": "not_found"})
                        continue
                    # Per-record forbid check — catches forbid rules that
                    # reference record fields (e.g. forbid on locked rows).
                    if cedar_spec is not None:
                        rec = evaluate_permission(
                            cedar_spec,
                            AccessOperationKind.UPDATE,
                            _record_to_dict(existing),
                            ctx,
                            entity_name=entity_name,
                        )
                        if not rec.allowed:
                            results.append({"id": item_id, "ok": False, "error": "forbidden"})
                            continue

                updated = await repo.update(item_id, update_payload)
                if updated is None:
                    results.append({"id": item_id, "ok": False, "error": "not_found"})
                    continue
                results.append({"id": item_id, "ok": True})
                ok_count += 1
            except Exception as e:
                # Log the full exception server-side, but expose only a
                # generic error code to the caller so stack-trace details
                # don't leak (CodeQL py/stack-trace-exposure, alert #61).
                logger.warning(
                    "Bulk %s.%s failed for %s: %s",
                    entity_name,
                    action_name,
                    item_id,
                    e,
                )
                results.append({"id": item_id, "ok": False, "error": "internal_error"})

        return JSONResponse(
            content={
                "action": action_name,
                "field": spec.field,
                "target_value": spec.target_value,
                "total": len(ids),
                "succeeded": ok_count,
                "results": results,
            }
        )

    router.post(path, summary=f"Bulk {entity_name} action")(bulk_action_handler)
