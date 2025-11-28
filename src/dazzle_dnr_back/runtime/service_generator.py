"""
Service generator - generates domain service stubs from ServiceSpec.

This module creates service classes that implement domain operations.
Services handle business logic and can be customized by users.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Generic, List, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel

from dazzle_dnr_back.specs.service import (
    OperationKind,
    ServiceSpec,
)

if TYPE_CHECKING:
    from dazzle_dnr_back.runtime.repository import SQLiteRepository


# =============================================================================
# Type Variables
# =============================================================================

T = TypeVar("T", bound=BaseModel)
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)


# =============================================================================
# Base Service Classes
# =============================================================================


class BaseService(ABC, Generic[T]):
    """
    Abstract base service class.

    Provides the interface for all services. Subclasses implement
    specific domain operations.
    """

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the service operation."""
        ...


class CRUDService(BaseService[T], Generic[T, CreateT, UpdateT]):
    """
    Generic CRUD service implementation.

    Provides standard create, read, update, delete, and list operations.
    Supports both in-memory storage (for testing) and SQLite persistence
    via the repository pattern.
    """

    def __init__(
        self,
        entity_name: str,
        model_class: type[T],
        create_schema: type[CreateT],
        update_schema: type[UpdateT],
        repository: "SQLiteRepository[T] | None" = None,
    ):
        self.entity_name = entity_name
        self.model_class = model_class
        self.create_schema = create_schema
        self.update_schema = update_schema

        # Repository for SQLite persistence
        self._repository = repository

        # In-memory store as fallback (for testing without database)
        self._store: dict[UUID, T] = {}

    def set_repository(self, repository: "SQLiteRepository[T]") -> None:
        """
        Set the repository for persistent storage.

        Args:
            repository: SQLite repository instance
        """
        self._repository = repository

    async def execute(self, operation: str, **kwargs: Any) -> Any:
        """Route to the appropriate operation."""
        operations = {
            "create": self.create,
            "read": self.read,
            "update": self.update,
            "delete": self.delete,
            "list": self.list,
        }
        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")
        return await operations[operation](**kwargs)

    async def create(self, data: CreateT) -> T:
        """Create a new entity."""
        # Generate ID
        entity_id = uuid4()

        # Build entity data
        entity_data = {"id": entity_id, **data.model_dump()}

        # Use repository if available
        if self._repository:
            return await self._repository.create(entity_data)

        # Fallback to in-memory
        entity = self.model_class(**entity_data)
        self._store[entity_id] = entity
        return entity

    async def read(self, id: UUID) -> T | None:
        """Read an entity by ID."""
        if self._repository:
            return await self._repository.read(id)
        return self._store.get(id)

    async def update(self, id: UUID, data: UpdateT) -> T | None:
        """Update an existing entity."""
        # Get update data, excluding None values
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}

        if self._repository:
            return await self._repository.update(id, update_data)

        # Fallback to in-memory
        existing = self._store.get(id)
        if not existing:
            return None

        # Merge with existing
        merged_data = {**existing.model_dump(), **update_data}

        # Create updated instance
        updated = self.model_class(**merged_data)
        self._store[id] = updated

        return updated

    async def delete(self, id: UUID) -> bool:
        """Delete an entity by ID."""
        if self._repository:
            return await self._repository.delete(id)

        if id in self._store:
            del self._store[id]
            return True
        return False

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        List entities with pagination and filtering.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            filters: Optional filter criteria

        Returns:
            Dictionary with items, total, page, and page_size
        """
        if self._repository:
            return await self._repository.list(page, page_size, filters)

        # Fallback to in-memory
        items = list(self._store.values())

        # Apply filters if provided
        if filters:
            items = self._apply_filters(items, filters)

        # Calculate pagination
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_items = items[start:end]

        return {
            "items": paginated_items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _apply_filters(
        self, items: List[T], filters: dict[str, Any]
    ) -> List[T]:
        """Apply filters to a list of items."""
        filtered = []
        for item in items:
            item_dict = item.model_dump()
            match = True
            for key, value in filters.items():
                if key in item_dict and item_dict[key] != value:
                    match = False
                    break
            if match:
                filtered.append(item)
        return filtered


class CustomService(BaseService[T]):
    """
    Custom service for non-CRUD operations.

    Provides a flexible base for implementing custom domain logic.
    """

    def __init__(
        self,
        service_name: str,
        handler: Callable[..., Any] | None = None,
    ):
        self.service_name = service_name
        self._handler = handler

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the custom service operation."""
        if self._handler:
            return await self._handler(**kwargs)
        else:
            # Default stub implementation
            return {"status": "ok", "service": self.service_name, "message": "Not implemented"}

    def set_handler(self, handler: Callable[..., Any]) -> None:
        """Set the handler function for this service."""
        self._handler = handler


# =============================================================================
# Service Factory
# =============================================================================


class ServiceFactory:
    """
    Factory for creating services from ServiceSpec.

    Creates appropriate service implementations based on the service specification.
    """

    def __init__(self, models: dict[str, type[BaseModel]]):
        """
        Initialize the service factory.

        Args:
            models: Dictionary mapping entity names to Pydantic models
        """
        self.models = models
        self._services: dict[str, BaseService[Any]] = {}

    def create_service(
        self,
        spec: ServiceSpec,
        create_schema: type[BaseModel] | None = None,
        update_schema: type[BaseModel] | None = None,
    ) -> BaseService[Any]:
        """
        Create a service from a ServiceSpec.

        Args:
            spec: Service specification
            create_schema: Optional create schema (for CRUD services)
            update_schema: Optional update schema (for CRUD services)

        Returns:
            Service instance
        """
        if spec.is_crud and spec.target_entity:
            entity_name = spec.target_entity
            model = self.models.get(entity_name)

            if not model:
                raise ValueError(f"No model found for entity: {entity_name}")

            # Use provided schemas or create defaults
            if not create_schema:
                create_schema = model
            if not update_schema:
                update_schema = model

            service: BaseService[Any] = CRUDService(
                entity_name=entity_name,
                model_class=model,
                create_schema=create_schema,
                update_schema=update_schema,
            )
        else:
            service = CustomService(service_name=spec.name)

        self._services[spec.name] = service
        return service

    def get_service(self, name: str) -> BaseService[Any] | None:
        """Get a service by name."""
        return self._services.get(name)

    def create_all_services(
        self,
        specs: list[ServiceSpec],
        schemas: dict[str, dict[str, type[BaseModel]]] | None = None,
    ) -> dict[str, BaseService[Any]]:
        """
        Create services for all specifications.

        Args:
            specs: List of service specifications
            schemas: Optional dictionary mapping entity names to
                     {"create": schema, "update": schema}

        Returns:
            Dictionary mapping service names to service instances
        """
        schemas = schemas or {}

        for spec in specs:
            entity_name = spec.target_entity
            entity_schemas = schemas.get(entity_name or "", {})

            self.create_service(
                spec,
                create_schema=entity_schemas.get("create"),
                update_schema=entity_schemas.get("update"),
            )

        return self._services


# =============================================================================
# Service Execution Context
# =============================================================================


class ServiceContext:
    """
    Execution context for services.

    Holds request-scoped data like current user, tenant, and trace ID.
    """

    def __init__(
        self,
        user_id: UUID | None = None,
        tenant_id: UUID | None = None,
        trace_id: str | None = None,
        permissions: list[str] | None = None,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.trace_id = trace_id or str(uuid4())
        self.permissions = permissions or []

    def has_permission(self, permission: str) -> bool:
        """Check if context has a specific permission."""
        return "*" in self.permissions or permission in self.permissions
