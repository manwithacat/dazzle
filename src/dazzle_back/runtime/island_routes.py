"""
Island API routes — auto-generated CRUD endpoints for UI islands.

When an island declares ``entity: SomeEntity``, the framework generates
a lightweight data endpoint at ``/api/islands/{island_name}/data``
that proxies to the entity's CRUD service.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter, Depends, HTTPException, Query

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if TYPE_CHECKING:
    from dazzle.core.ir.islands import IslandSpec

logger = logging.getLogger("dazzle.islands")


def create_island_routes(
    islands: list[IslandSpec],
    services: dict[str, Any],
    auth_dep: Any | None = None,
    optional_auth_dep: Any | None = None,
) -> APIRouter:
    """Create API routes for islands that declare an entity binding.

    Args:
        islands: Island specs from the AppSpec.
        services: Service registry keyed by entity name.
        auth_dep: Required auth dependency (if auth is enabled).
        optional_auth_dep: Optional auth dependency.

    Returns:
        FastAPI APIRouter mounted at ``/api/islands``.
    """
    router = APIRouter(prefix="/api/islands", tags=["Islands"])

    for island in islands:
        if not island.entity:
            continue

        entity_name = island.entity
        island_name = island.name

        sub = APIRouter(prefix=f"/{island_name}")

        # Build dependency list
        deps: list[Any] = []
        if auth_dep:
            deps.append(Depends(auth_dep))

        @sub.get("/data", dependencies=deps)
        async def get_island_data(
            limit: int = Query(default=100, ge=1, le=1000),
            offset: int = Query(default=0, ge=0),
            _entity: str = entity_name,
            _island: str = island_name,
        ) -> dict[str, Any]:
            """Fetch data for island from its bound entity."""
            svc = services.get(_entity)
            if not svc:
                raise HTTPException(
                    status_code=404,
                    detail=f"No service found for entity '{_entity}'",
                )
            try:
                items = await svc.list(limit=limit, offset=offset)
                return {"items": items, "island": _island}
            except Exception as exc:
                logger.exception("Island data fetch failed for %s", _entity)
                raise HTTPException(status_code=500, detail=str(exc)) from exc

        router.include_router(sub)

    return router
