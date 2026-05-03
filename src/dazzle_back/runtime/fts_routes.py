"""Full-text search endpoint (#954 cycle 3).

Exposes ``GET /api/fts/{entity}?q=...`` backed by the cycle-2
``search_vector`` GENERATED column. Builds the query via
:meth:`Repository.fts_search` so all the indexed-FTS work happens
in one place.

Scope-aware filtering: when the entity carries `scope:` rules with
field conditions, the predicate compiler (used by the regular list
endpoint) produces a ``(sql, params)`` tuple that's ANDed into the
FTS WHERE clause. This keeps RBAC correct on the search endpoint
without re-implementing the scope path.

Cycle 3 scope:
  * Single-entity search via the route param.
  * Authentication required (cookie / bearer / dev-default per the
    project's auth dep).
  * Scope predicates honoured when present.

Out of scope here (cycle 4+):
  * Cross-entity / federated search (the legacy ``/api/search``
    endpoint covers the multi-entity ILIKE fallback).
  * Highlight / snippet rendering (``ts_headline``).
  * ``display: search_box`` workspace region wiring.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

logger = logging.getLogger(__name__)


def create_fts_routes(
    *,
    appspec: Any,
    repositories: dict[str, Any],
    fk_graph: Any,
    auth_dep: Any,
    admin_personas: list[str] | None = None,
) -> APIRouter | None:
    """Build the FTS router. Returns ``None`` when the AppSpec has no
    SearchSpecs (no endpoint is registered, OpenAPI stays clean).

    Args:
        appspec: The runtime AppSpec — read for ``searches`` + per-entity
            scope rules.
        repositories: ``{entity_name: Repository}`` from the runtime.
        fk_graph: For predicate compilation (FK traversal).
        auth_dep: FastAPI dependency that resolves the current user.
        admin_personas: Tenant-admin persona allow-list — bypass scope
            for these (mirrors the list endpoint's behaviour).
    """
    searches = list(getattr(appspec, "searches", []) or [])
    if not searches:
        return None

    # Index searches by entity for O(1) lookup at request time.
    spec_by_entity = {s.entity: s for s in searches}

    router = APIRouter(tags=["Search"])

    @router.get("/api/fts/{entity}")
    async def fts_search(
        entity: str,
        request: Request,
        q: str = Query(..., min_length=1, description="Search query"),
        page: int = Query(1, ge=1, description="1-indexed page number"),
        page_size: int = Query(20, ge=1, le=100, description="Per-page limit"),
        auth_context: Any = Depends(auth_dep),
    ) -> dict[str, Any]:
        spec = spec_by_entity.get(entity)
        if spec is None:
            raise HTTPException(
                status_code=404,
                detail=f"No search spec for entity {entity!r}",
            )
        repo = repositories.get(entity)
        if repo is None:
            raise HTTPException(
                status_code=404,
                detail=f"No repository for entity {entity!r}",
            )

        # Compile scope predicate per request — same path the list
        # endpoint takes. Skipped when the entity has no scope rules
        # or the user is a tenant admin.
        scope_pred: tuple[str, list[Any]] | None = None
        cedar_spec = _find_cedar_spec(appspec, entity)
        user_id = _resolve_user_id(auth_context)
        if cedar_spec is not None and user_id is not None:
            scope_pred = _compile_scope(
                cedar_spec=cedar_spec,
                entity_name=entity,
                fk_graph=fk_graph,
                user_id=user_id,
                auth_context=auth_context,
                admin_personas=admin_personas,
            )

        result = await repo.fts_search(
            spec,
            q,
            page=page,
            page_size=page_size,
            scope_predicate=scope_pred,
        )
        return {
            "entity": entity,
            "query": q,
            **result,
        }

    return router


def _find_cedar_spec(appspec: Any, entity_name: str) -> Any | None:
    """Look up the cedar/access spec for an entity. Returns None when
    no scope rules are declared (open access)."""
    for spec in getattr(appspec, "cedar_access_specs", None) or {}:
        if spec == entity_name:
            return appspec.cedar_access_specs[spec]
    return None


def _resolve_user_id(auth_context: Any) -> str | None:
    """Pull the entity-id of the current user, or None when unauth."""
    if auth_context is None:
        return None
    user = getattr(auth_context, "user", None)
    if user is None:
        return None
    return getattr(user, "id", None) or getattr(user, "entity_id", None)


def _compile_scope(
    *,
    cedar_spec: Any,
    entity_name: str,
    fk_graph: Any,
    user_id: str,
    auth_context: Any,
    admin_personas: list[str] | None,
) -> tuple[str, list[Any]] | None:
    """Wrap the route_generator helper to produce a scope predicate
    suitable for ``Repository.fts_search``.

    Returns ``None`` when no scope filter applies (admin bypass, or
    no field-level scope rules). Returns the ``(sql, params)`` tuple
    otherwise.
    """
    try:
        from dazzle_back.runtime.route_generator import _resolve_predicate_filters
    except ImportError:
        logger.debug("route_generator scope compiler unavailable", exc_info=True)
        return None

    # Find a list-permission scope predicate on the cedar spec.
    # Cedar specs carry per-operation predicates compiled by the
    # linker; LIST is the right one for search (returning matching rows).
    from dazzle.core.access import AccessOperationKind

    list_rules = [
        r
        for r in getattr(cedar_spec, "permissions", []) or []
        if getattr(r, "operation", None) == AccessOperationKind.LIST
    ]
    predicates = [p for p in (getattr(r, "predicate", None) for r in list_rules) if p is not None]
    if not predicates:
        return None

    # Cycle 3 simplification: when multiple LIST rules carry predicates,
    # use the first. Multi-predicate OR composition is what the list
    # endpoint does; the FTS endpoint will follow once the same
    # composition helper lands as a public API.
    filters = _resolve_predicate_filters(
        predicate=predicates[0],
        entity_name=entity_name,
        fk_graph=fk_graph,
        user_id=user_id,
        auth_context=auth_context,
        admin_personas=admin_personas,
    )
    if not filters or "__scope_predicate" not in filters:
        return None
    sql, params = filters["__scope_predicate"]
    return (str(sql), list(params))


__all__ = ["create_fts_routes"]
