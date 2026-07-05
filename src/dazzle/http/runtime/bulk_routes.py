"""Bulk-action endpoints derived from surface ``ux: bulk_actions:`` (#785).

When a list-mode surface declares bulk actions in its ``ux:`` block, the
runtime mounts a single ``POST /api/{entity_plural}/bulk`` endpoint that
applies a named field transition to every supplied id. ``delete`` is a
BUILT-IN action (grid convergence C0b — the HM grid's flagship bulk flow)
unless the surface declares its own action of that name, which always wins.

Two body shapes (C0b): the legacy dzTable JSON ``{action, ids}`` and the HM
grid primitive's form payload — ``action`` + repeated ``selected_ids`` /
``excluded_ids`` + ``all_matching_selected`` + a query echo. All-matching
re-runs the echoed query through the SAME gated list pipeline the view used
(never trusting client ids, §15) via :mod:`dazzle.http.runtime.bulk_payload`,
which fails CLOSED on any echo it can't consume faithfully.

RBAC (#1170): the bulk endpoint enforces the same authorization as the
generated single-record route — an entity-level Cedar permit gate (UPDATE
for transitions, DELETE for the built-in delete) plus a per-id ``scope:``
check via :func:`_scoped_pre_read`. Ids the caller cannot scope to are
reported as ``not_found`` (the same IDOR-safe shape the single-record route
uses), never silently mutated. A field patch goes through ``repo.update``
directly — a constrained, per-item transition with no user-supplied payload
to validate; a delete goes through the service (hooks/cascades apply).

When the app has no auth configured at all (``optional_auth_dep`` is
``None``) the endpoint applies actions unenforced — consistent with the
rest of that app having no RBAC.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from dazzle.core.access import AccessOperationKind
from dazzle.core.ir import BulkActionSpec
from dazzle.core.strings import to_api_plural
from dazzle.http.runtime.access.gated import AccessForbidden, access_context_from
from dazzle.http.runtime.audit_wrap import (
    _build_access_context,
    _record_to_dict,
)
from dazzle.http.runtime.bulk_payload import (
    BulkQueryError,
    parse_bulk_selection,
    resolve_all_matching_ids,
)
from dazzle.http.runtime.scope_filters import _scoped_pre_read
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
    entity_search_fields: dict[str, list[str]] | None = None,
    entity_filter_fields: dict[str, list[str]] | None = None,
    entity_access_specs: dict[str, Any] | None = None,
    entity_ref_targets: dict[str, dict[str, str]] | None = None,
    all_matching_cap: int = 10_000,
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
            search_fields=(entity_search_fields or {}).get(entity_name),
            filter_fields=(entity_filter_fields or {}).get(entity_name),
            access_spec=(entity_access_specs or {}).get(entity_name),
            ref_targets=(entity_ref_targets or {}).get(entity_name),
            all_matching_cap=all_matching_cap,
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
    search_fields: list[str] | None = None,
    filter_fields: list[str] | None = None,
    access_spec: Any = None,
    ref_targets: dict[str, str] | None = None,
    all_matching_cap: int = 10_000,
) -> None:
    """Wire one entity's bulk endpoint with RBAC + scope enforcement."""
    action_map = {a.name: a for a in actions}
    path = f"/api/{to_api_plural(entity_name)}/bulk"
    auth_dep = optional_auth_dep if optional_auth_dep is not None else _no_auth

    async def bulk_action_handler(
        request: Request,
        auth_context: Any = Depends(auth_dep),
    ) -> JSONResponse:
        # Dual body shapes (convergence C0b): the legacy dzTable JSON
        # `{action, ids}` and the HM grid primitive's form payload (action +
        # repeated selected_ids/excluded_ids + all_matching_selected + the
        # query echo the rows came from).
        try:
            sel = await parse_bulk_selection(request)
        except Exception:
            return JSONResponse(content={"error": "Unparseable bulk body"}, status_code=400)

        action_name = sel.action
        # `delete` is a BUILT-IN action (the grid's flagship bulk flow) unless
        # the surface declares its own action of that name — a declared
        # transition always wins (never shadow the app's semantics).
        is_delete = action_name == "delete" and action_name not in action_map
        if not is_delete and action_name not in action_map:
            return JSONResponse(
                content={
                    "error": f"Unknown action {action_name!r} for {entity_name}",
                    "actions": sorted({*action_map.keys(), "delete"}),
                },
                status_code=422,
            )
        if is_delete and service is None:
            return JSONResponse(
                content={"error": "Bulk delete requires a service for this entity"},
                status_code=422,
            )

        # Resolve WHO the action applies to. All-matching (§15): re-run the
        # echoed query through the SAME gated list pipeline the view used —
        # never trusting the client ids — then subtract the exclusions. The
        # resolver fails CLOSED on any echo it can't consume faithfully.
        if sel.all_matching:
            if service is None:
                return JSONResponse(
                    content={"error": "All-matching selection requires a service"},
                    status_code=422,
                )
            access = access_context_from(
                auth_context=auth_context,
                entity_name=entity_name,
                cedar_access_spec=cedar_spec,
                fk_graph=fk_graph,
                admin_personas=admin_personas,
            )
            try:
                matched = await resolve_all_matching_ids(
                    service=service,
                    access=access,
                    echo=sel.echo,
                    search_fields=search_fields,
                    filter_fields=filter_fields,
                    access_spec=access_spec,
                    ref_targets=ref_targets,
                    cap=all_matching_cap,
                )
            except BulkQueryError as e:
                return JSONResponse(content={"error": str(e)}, status_code=422)
            except AccessForbidden as e:
                # gated_list's LIST permit gate — a caller with UPDATE/DELETE
                # permit but no LIST permit can't resolve an all-matching set.
                return JSONResponse(content={"error": str(e)}, status_code=403)
            excluded = set(sel.excluded_ids)
            ids = [i for i in matched if i not in excluded]
        else:
            ids = sel.selected_ids

        if not ids:
            return JSONResponse(
                content={"error": "`ids` must be a non-empty list"},
                status_code=422,
            )

        spec = action_map.get(action_name)
        update_payload = {spec.field: spec.target_value} if spec else {}

        # `auth_context is None` ⟺ the app has no auth configured; the
        # real optional-auth dependency always returns an AuthContext
        # (possibly unauthenticated). Only enforce when auth exists.
        # A delete enforces the DELETE operation; a transition, UPDATE.
        op_kind = AccessOperationKind.DELETE if is_delete else AccessOperationKind.UPDATE
        op_name = "delete" if is_delete else "update"
        enforce = auth_context is not None
        ctx: Any = None
        if enforce:
            _user, ctx = _build_access_context(auth_context, admin_personas)
            # Entity-level permit gate — mirrors the generated single-record
            # route. A categorically-denied role fails the whole request 403.
            if cedar_spec is not None:
                gate = evaluate_permission(cedar_spec, op_kind, None, ctx, entity_name=entity_name)
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
                        operation=op_name,
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
                            op_kind,
                            _record_to_dict(existing),
                            ctx,
                            entity_name=entity_name,
                        )
                        if not rec.allowed:
                            results.append({"id": item_id, "ok": False, "error": "forbidden"})
                            continue

                if is_delete:
                    # Through the service (not the raw repo) so delete hooks /
                    # cascades apply — the same path the single-record DELETE
                    # route takes.
                    await service.execute(operation="delete", id=item_id)
                else:
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
                "field": spec.field if spec else None,
                "target_value": spec.target_value if spec else None,
                "total": len(ids),
                "succeeded": ok_count,
                "results": results,
            }
        )

    router.post(path, summary=f"Bulk {entity_name} action")(bulk_action_handler)
