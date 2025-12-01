"""
CRUD route handlers for DNR container runtime.

Provides dynamic entity CRUD endpoints based on the backend spec.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from .data_store import data_store


def register_crud_routes(
    app: FastAPI,
    entities: list[dict[str, Any]],
) -> None:
    """
    Register CRUD routes for all entities in the backend spec.

    Args:
        app: FastAPI application instance
        entities: List of entity configurations from backend spec
    """
    for entity in entities:
        entity_name = entity["name"]
        route_prefix = f"/api/{entity_name.lower()}s"

        # Create handlers with closure to capture entity_name
        list_h, create_h, get_h, update_h, delete_h = _make_crud_handlers(entity_name)

        # Register routes
        app.get(route_prefix)(list_h)
        app.post(route_prefix)(create_h)
        app.get(f"{route_prefix}/{{item_id}}")(get_h)
        app.put(f"{route_prefix}/{{item_id}}")(update_h)
        app.delete(f"{route_prefix}/{{item_id}}")(delete_h)


def _make_crud_handlers(
    entity_name: str,
) -> tuple[Callable[..., Any], ...]:
    """Create CRUD handler functions for an entity."""

    async def list_items() -> dict[str, Any]:
        collection = data_store.get_collection(entity_name)
        items = list(collection.values())
        return {"items": items, "total": len(items)}

    async def create_item(request: Request) -> dict[str, Any]:
        data: dict[str, Any] = await request.json()
        item_id = str(uuid.uuid4())
        data["id"] = item_id
        collection = data_store.get_collection(entity_name)
        collection[item_id] = data
        return data

    async def get_item(item_id: str) -> dict[str, Any]:
        collection = data_store.get_collection(entity_name)
        if item_id not in collection:
            raise HTTPException(status_code=404, detail=f"{entity_name} not found")
        item: dict[str, Any] = collection[item_id]
        return item

    async def update_item(item_id: str, request: Request) -> dict[str, Any]:
        collection = data_store.get_collection(entity_name)
        if item_id not in collection:
            raise HTTPException(status_code=404, detail=f"{entity_name} not found")
        data: dict[str, Any] = await request.json()
        data["id"] = item_id
        collection[item_id].update(data)
        updated: dict[str, Any] = collection[item_id]
        return updated

    async def delete_item(item_id: str) -> dict[str, Any]:
        collection = data_store.get_collection(entity_name)
        if item_id not in collection:
            raise HTTPException(status_code=404, detail=f"{entity_name} not found")
        del collection[item_id]
        return {"deleted": True}

    return list_items, create_item, get_item, update_item, delete_item
