"""Bulk-action endpoints derived from surface ``ux: bulk_actions:`` (#785).

When a list-mode surface declares bulk actions in its ``ux:`` block, the
runtime mounts a single ``POST /api/{entity_plural}/bulk`` endpoint that
applies a named field transition to every supplied id.

Design: we bypass the service layer's strongly-typed update path and call
``repo.update(id, {field: target_value})`` directly because the bulk
action is a constrained, per-item patch — there's no user-supplied
update payload to validate. Scope/permission enforcement still happens
inside the repo's ``update`` method.
"""

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from dazzle.core.ir import BulkActionSpec
from dazzle.core.strings import to_api_plural

logger = logging.getLogger(__name__)


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
    repositories: dict[str, Any],
) -> APIRouter | None:
    """Register ``POST /api/{plural}/bulk`` for every bulk-action-bearing entity.

    Returns ``None`` when no surface declares bulk actions so apps that
    don't need the feature get a clean OpenAPI surface.
    """
    entity_actions = _build_entity_bulk_actions(surfaces)
    entity_actions = {
        name: actions for name, actions in entity_actions.items() if name in repositories
    }
    if not entity_actions:
        return None

    router = APIRouter(tags=["Bulk Actions"])

    for entity_name, actions in entity_actions.items():
        _register_bulk_route(router, entity_name, actions, repositories[entity_name])

    return router


def _register_bulk_route(
    router: APIRouter,
    entity_name: str,
    actions: list[BulkActionSpec],
    repo: Any,
) -> None:
    """Wire one entity's bulk endpoint with its declared action map."""
    action_map = {a.name: a for a in actions}
    path = f"/api/{to_api_plural(entity_name)}/bulk"

    async def bulk_action_handler(request: Request) -> JSONResponse:
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
        results: list[dict[str, Any]] = []
        ok_count = 0

        for raw_id in ids:
            item_id = str(raw_id)
            try:
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
