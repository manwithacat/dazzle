"""Cross-entity search endpoint (#782).

Registers ``GET /api/search?q=<query>`` that fans out across every entity
with declared searchable fields and returns faceted results grouped by
entity. Searchable fields are drawn from:

- Surface ``search_fields:`` declarations (precedence).
- Entity-level ``searchable`` field modifiers as fallback.

Both sources are pre-computed into ``entity_search_fields`` by
``app_factory.build_entity_search_fields`` and passed into the runtime.
"""

import logging
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def create_search_routes(
    repositories: dict[str, Any],
    entity_search_fields: dict[str, list[str]],
    per_entity_limit: int = 10,
) -> APIRouter | None:
    """Build an APIRouter with ``GET /api/search`` if any entity is searchable.

    Returns ``None`` when no entity declares searchable fields — in that
    case no endpoint is registered, keeping the OpenAPI surface clean.
    """
    searchable = {
        name: fields
        for name, fields in entity_search_fields.items()
        if fields and name in repositories
    }
    if not searchable:
        return None

    router = APIRouter(tags=["Search"])

    @router.get("/api/search")
    async def cross_entity_search(
        q: str = Query(..., description="Search query string", min_length=1),
        entity: str | None = Query(None, description="Restrict search to a single entity name"),
        limit: int = Query(
            per_entity_limit,
            ge=1,
            le=100,
            description="Max results returned per entity",
        ),
    ) -> JSONResponse:
        """Fan search across every searchable entity; group results by entity.

        Results preserve entity order as declared in the DSL so the shape is
        stable across requests. Per-entity failures are logged and skipped
        rather than failing the whole request.
        """
        targets = {entity: searchable[entity]} if entity and entity in searchable else searchable

        results: list[dict[str, Any]] = []
        for entity_name, fields in targets.items():
            repo = repositories.get(entity_name)
            if repo is None:
                continue
            try:
                page = await repo.list(
                    page=1,
                    page_size=limit,
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
