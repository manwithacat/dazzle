"""Cross-entity search endpoint (#782).

Registers ``GET /_dazzle/search?q=<query>`` that fans out across every entity
with declared searchable fields and returns faceted results grouped by
entity. Searchable fields are drawn from:

- Surface ``search_fields:`` declarations (precedence).
- Entity-level ``searchable`` field modifiers as fallback.

Both sources are pre-computed into ``entity_search_fields`` by
``app_factory.build_entity_search_fields`` and passed into the runtime.

Access (ship P): each entity is searched under the LIST enforcement its list
endpoint applies — the Cedar LIST permit gate and `scope: list:` rules, via
:func:`access.gated.list_scope_filters`. An entity the caller may not list, or
whose scope matches no rule for the caller (including any anonymous caller on an
entity with access rules), is left out of the results rather than read unscoped.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from dazzle.http.runtime.access.gated import (
    AccessForbidden,
    access_context_from,
    list_scope_filters,
)
from dazzle.http.runtime.auth.auth_views import leftover_honest_auth_error

logger = logging.getLogger(__name__)


def leftover_honest_search_entity(raw: Any, declared: Any) -> str | None:
    """Valid declared searchable entity names ride. Leftover stays put (None).

    Leftover ``?entity=zzz`` / ``ghost`` / ``MysteryEntity`` on
    GET ``/_dazzle/search`` used to miss the searchable catalog and
    invent the unfiltered fleet (``test_unknown_entity_param_stays_put``).
    Valid declared entity names ride. Absent / blank is first-visit
    (``""`` — all entities). Rest is stay-put (None → 400). Distinct
    from leftover catalog picker (oral #69) and leftover search-box
    ``q`` (gallery). Live ``hx-get="/_dazzle/search"``
    (``docs/reference/frontend.md``) + contact_manager
    ``patterns: searchable``. Cycle 2247.
    """
    return leftover_honest_auth_error(raw, declared)


def create_search_routes(
    repositories: dict[str, Any],
    entity_search_fields: dict[str, list[str]],
    per_entity_limit: int = 10,
    *,
    cedar_access_specs: dict[str, Any] | None = None,
    fk_graph: Any = None,
    optional_auth_dep: Any = None,
    admin_personas: list[str] | None = None,
) -> APIRouter | None:
    """Build an APIRouter with ``GET /_dazzle/search`` if any entity is searchable.

    Returns ``None`` when no entity declares searchable fields — in that
    case no endpoint is registered, keeping the OpenAPI surface clean.

    ``cedar_access_specs`` / ``fk_graph`` / ``admin_personas`` are the inputs
    the list routes are generated from; ``optional_auth_dep`` resolves the
    caller (``None`` when the app has auth disabled — then, as on the list
    routes, no Cedar enforcement applies).
    """
    access_specs = cedar_access_specs or {}
    searchable = {
        name: fields
        for name, fields in entity_search_fields.items()
        if fields and name in repositories
    }
    if not searchable:
        return None

    router = APIRouter(prefix="/_dazzle/search", tags=["Search"])

    async def _no_auth() -> None:
        return None

    @router.get("")
    async def cross_entity_search(
        q: str = Query(..., description="Search query string", min_length=1),
        entity: str | None = Query(None, description="Restrict search to a single entity name"),
        limit: int = Query(
            per_entity_limit,
            ge=1,
            le=100,
            description="Max results returned per entity",
        ),
        auth_context: Any = Depends(optional_auth_dep or _no_auth),
    ) -> JSONResponse:
        """Fan search across every searchable entity; group results by entity.

        Results preserve entity order as declared in the DSL so the shape is
        stable across requests. Per-entity failures are logged and skipped
        rather than failing the whole request.
        """
        honest_entity = leftover_honest_search_entity(entity, searchable)
        if honest_entity is None:
            # Leftover ``?entity=zzz`` invented the fleet. Stay put.
            return JSONResponse(content={"error": "invalid entity"}, status_code=400)
        targets = {honest_entity: searchable[honest_entity]} if honest_entity else searchable

        results: list[dict[str, Any]] = []
        for entity_name, fields in targets.items():
            repo = repositories.get(entity_name)
            if repo is None:
                continue
            cedar_spec = access_specs.get(entity_name) if optional_auth_dep else None
            scope_filters: dict[str, Any] | None = {}
            if cedar_spec is not None:
                access = access_context_from(
                    auth_context=auth_context,
                    entity_name=entity_name,
                    cedar_access_spec=cedar_spec,
                    fk_graph=fk_graph,
                    admin_personas=admin_personas,
                )
                try:
                    scope_filters = list_scope_filters(access)
                except AccessForbidden:
                    scope_filters = None
            if scope_filters is None:
                # Not listable by this caller — leave the entity out entirely.
                continue
            try:
                page = await repo.list(
                    page=1,
                    page_size=limit,
                    filters=scope_filters or None,
                    search=q,
                    search_fields=fields,
                )
            except Exception:
                logger.warning("Cross-entity search failed for %s", entity_name, exc_info=True)
                continue

            items_raw = page.get("items", []) if isinstance(page, dict) else []
            items: list[dict[str, Any]] = []
            for row in items_raw:
                if isinstance(row, dict):
                    items.append(row)
                else:
                    dump = getattr(row, "model_dump", None)
                    items.append(dump(mode="json") if callable(dump) else dict(row))
            total = int(page.get("total", len(items))) if isinstance(page, dict) else len(items)

            results.append(
                {
                    "entity": entity_name,
                    "total": total,
                    "fields": list(fields),
                    "items": items,
                }
            )

        return JSONResponse(
            content={
                "query": q,
                "results": results,
            }
        )

    return router
