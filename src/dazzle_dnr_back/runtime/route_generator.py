"""
Route generator - generates FastAPI routes from EndpointSpec.

This module creates FastAPI routers and routes from backend specifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional
from uuid import UUID

from pydantic import BaseModel

from dazzle_dnr_back.specs.endpoint import EndpointSpec, HttpMethod
from dazzle_dnr_back.specs.service import OperationKind, ServiceSpec

# Type checking imports
if TYPE_CHECKING:
    from fastapi import APIRouter

# FastAPI is optional - only import if available
try:
    from fastapi import APIRouter as _APIRouter, Depends, HTTPException, Query
    from fastapi.responses import JSONResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    _APIRouter = None  # type: ignore
    HTTPException = None  # type: ignore
    Query = None  # type: ignore


# =============================================================================
# Route Handler Factory
# =============================================================================


def create_list_handler(
    service: Any,
    response_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for list operations."""

    async def handler(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    ) -> Any:
        result = await service.execute(
            operation="list",
            page=page,
            page_size=page_size,
        )
        return result

    return handler


def create_read_handler(
    service: Any,
    response_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for read operations."""

    async def handler(id: UUID) -> Any:
        result = await service.execute(operation="read", id=id)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    return handler


def create_create_handler(
    service: Any,
    input_schema: type[BaseModel],
    response_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for create operations."""

    async def handler(data: input_schema) -> Any:  # type: ignore
        result = await service.execute(operation="create", data=data)
        return result

    return handler


def create_update_handler(
    service: Any,
    input_schema: type[BaseModel],
    response_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for update operations."""

    async def handler(id: UUID, data: input_schema) -> Any:  # type: ignore
        result = await service.execute(operation="update", id=id, data=data)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    return handler


def create_delete_handler(
    service: Any,
) -> Callable[..., Any]:
    """Create a handler for delete operations."""

    async def handler(id: UUID) -> dict[str, bool]:
        result = await service.execute(operation="delete", id=id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return {"deleted": True}

    return handler


def create_custom_handler(
    service: Any,
    input_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for custom operations."""

    if input_schema:

        async def handler_with_input(data: input_schema) -> Any:  # type: ignore
            result = await service.execute(**data.model_dump())
            return result

        return handler_with_input
    else:

        async def handler_no_input() -> Any:
            result = await service.execute()
            return result

        return handler_no_input


# =============================================================================
# Route Generator
# =============================================================================


class RouteGenerator:
    """
    Generates FastAPI routes from endpoint specifications.

    Creates routes with appropriate HTTP methods, paths, and handlers.
    """

    def __init__(
        self,
        services: dict[str, Any],
        models: dict[str, type[BaseModel]],
        schemas: dict[str, dict[str, type[BaseModel]]] | None = None,
    ):
        """
        Initialize the route generator.

        Args:
            services: Dictionary mapping service names to service instances
            models: Dictionary mapping entity names to Pydantic models
            schemas: Optional dictionary with create/update schemas per entity
        """
        if not FASTAPI_AVAILABLE:
            raise RuntimeError(
                "FastAPI is not installed. Install with: pip install fastapi"
            )

        self.services = services
        self.models = models
        self.schemas = schemas or {}
        self._router = _APIRouter()

    def generate_route(
        self,
        endpoint: EndpointSpec,
        service_spec: ServiceSpec | None = None,
    ) -> None:
        """
        Generate a single route from an endpoint specification.

        Args:
            endpoint: Endpoint specification
            service_spec: Optional service specification for type hints
        """
        service = self.services.get(endpoint.service)
        if not service:
            raise ValueError(f"Service not found: {endpoint.service}")

        # Determine operation kind from service spec or infer from method
        operation_kind = None
        entity_name = None

        if service_spec:
            operation_kind = service_spec.domain_operation.kind
            entity_name = service_spec.domain_operation.entity

        # Get schemas for the entity
        entity_schemas = self.schemas.get(entity_name or "", {})
        model = self.models.get(entity_name or "")

        # Create appropriate handler based on operation kind or HTTP method
        handler: Callable[..., Any]

        if operation_kind == OperationKind.LIST or (
            endpoint.method == HttpMethod.GET and "{id}" not in endpoint.path
        ):
            handler = create_list_handler(service, model)
            self._add_route(endpoint, handler, response_model=None)

        elif operation_kind == OperationKind.READ or (
            endpoint.method == HttpMethod.GET and "{id}" in endpoint.path
        ):
            handler = create_read_handler(service, model)
            self._add_route(endpoint, handler, response_model=model)

        elif operation_kind == OperationKind.CREATE or endpoint.method == HttpMethod.POST:
            create_schema = entity_schemas.get("create", model)
            if create_schema:
                handler = create_create_handler(service, create_schema, model)
                self._add_route(endpoint, handler, response_model=model)
            else:
                raise ValueError(f"No create schema for endpoint: {endpoint.name}")

        elif operation_kind == OperationKind.UPDATE or endpoint.method in (
            HttpMethod.PUT,
            HttpMethod.PATCH,
        ):
            update_schema = entity_schemas.get("update", model)
            if update_schema:
                handler = create_update_handler(service, update_schema, model)
                self._add_route(endpoint, handler, response_model=model)
            else:
                raise ValueError(f"No update schema for endpoint: {endpoint.name}")

        elif operation_kind == OperationKind.DELETE or endpoint.method == HttpMethod.DELETE:
            handler = create_delete_handler(service)
            self._add_route(endpoint, handler, response_model=None)

        else:
            # Custom operation
            handler = create_custom_handler(service)
            self._add_route(endpoint, handler, response_model=None)

    def _add_route(
        self,
        endpoint: EndpointSpec,
        handler: Callable[..., Any],
        response_model: type[BaseModel] | None = None,
    ) -> None:
        """Add a route to the router."""
        # Map HTTP methods to router methods
        method_map = {
            HttpMethod.GET: self._router.get,
            HttpMethod.POST: self._router.post,
            HttpMethod.PUT: self._router.put,
            HttpMethod.PATCH: self._router.patch,
            HttpMethod.DELETE: self._router.delete,
        }

        router_method = method_map.get(endpoint.method)
        if not router_method:
            raise ValueError(f"Unsupported HTTP method: {endpoint.method}")

        # Convert path parameters from {id} to FastAPI format
        path = endpoint.path

        # Build route decorator kwargs
        route_kwargs: dict[str, Any] = {
            "summary": endpoint.description or endpoint.name,
            "tags": endpoint.tags or [],
        }

        if response_model:
            route_kwargs["response_model"] = response_model

        # Add the route
        router_method(path, **route_kwargs)(handler)

    def generate_all_routes(
        self,
        endpoints: list[EndpointSpec],
        service_specs: dict[str, ServiceSpec] | None = None,
    ) -> APIRouter:
        """
        Generate routes for all endpoints.

        Args:
            endpoints: List of endpoint specifications
            service_specs: Optional dictionary mapping service names to specs

        Returns:
            FastAPI router with all routes
        """
        service_specs = service_specs or {}

        for endpoint in endpoints:
            service_spec = service_specs.get(endpoint.service)
            self.generate_route(endpoint, service_spec)

        return self._router

    @property
    def router(self) -> APIRouter:
        """Get the generated router."""
        return self._router


# =============================================================================
# Convenience Functions
# =============================================================================


def generate_crud_routes(
    entity_name: str,
    service: Any,
    model: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    prefix: str | None = None,
    tags: list[str] | None = None,
) -> APIRouter:
    """
    Generate standard CRUD routes for an entity.

    This is a convenience function for quickly creating RESTful routes.

    Args:
        entity_name: Name of the entity
        service: CRUD service instance
        model: Pydantic model for the entity
        create_schema: Schema for create operations
        update_schema: Schema for update operations
        prefix: Optional URL prefix (defaults to /entity_name)
        tags: Optional tags for grouping in OpenAPI docs

    Returns:
        FastAPI router with CRUD routes
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is not installed. Install with: pip install fastapi"
        )

    router = _APIRouter()
    prefix = prefix or f"/{entity_name.lower()}s"
    tags = tags or [entity_name]

    # List
    @router.get(prefix, tags=tags, summary=f"List {entity_name}s")
    async def list_items(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> Any:
        return await service.execute(operation="list", page=page, page_size=page_size)

    # Read
    @router.get(f"{prefix}/{{id}}", tags=tags, summary=f"Get {entity_name}", response_model=model)
    async def get_item(id: UUID) -> Any:
        result = await service.execute(operation="read", id=id)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    # Create
    @router.post(prefix, tags=tags, summary=f"Create {entity_name}", response_model=model)
    async def create_item(data: create_schema) -> Any:  # type: ignore
        return await service.execute(operation="create", data=data)

    # Update
    @router.put(f"{prefix}/{{id}}", tags=tags, summary=f"Update {entity_name}", response_model=model)
    async def update_item(id: UUID, data: update_schema) -> Any:  # type: ignore
        result = await service.execute(operation="update", id=id, data=data)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    # Delete
    @router.delete(f"{prefix}/{{id}}", tags=tags, summary=f"Delete {entity_name}")
    async def delete_item(id: UUID) -> dict[str, bool]:
        result = await service.execute(operation="delete", id=id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return {"deleted": True}

    return router
