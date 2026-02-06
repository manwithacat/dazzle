"""
Service generator - generates domain service stubs from ServiceSpec.

This module creates service classes that implement domain operations.
Services handle business logic and can be customized by users.
"""

import builtins
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel

from dazzle_back.specs.entity import EntitySpec, StateMachineSpec
from dazzle_back.specs.service import (
    ServiceSpec,
)

if TYPE_CHECKING:
    from dazzle_back.runtime.repository import SQLiteRepository


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


# Callback type for entity lifecycle events
EntityEventCallback = Callable[
    [str, str, dict[str, Any], dict[str, Any] | None],  # entity_name, entity_id, data, old_data
    Any,  # Return type (usually Awaitable[list[str]] for process IDs)
]


class CRUDService(BaseService[T], Generic[T, CreateT, UpdateT]):
    """
    Generic CRUD service implementation.

    Provides standard create, read, update, delete, and list operations.
    Supports both in-memory storage (for testing) and SQLite persistence
    via the repository pattern.

    Entity lifecycle events (v0.24.0):
    Services can register callbacks to be notified when entities are
    created, updated, or deleted. This enables process triggering.
    """

    def __init__(
        self,
        entity_name: str,
        model_class: type[T],
        create_schema: type[CreateT],
        update_schema: type[UpdateT],
        repository: "SQLiteRepository[T] | None" = None,
        state_machine: StateMachineSpec | None = None,
        entity_spec: EntitySpec | None = None,
    ):
        self.entity_name = entity_name
        self.model_class = model_class
        self.create_schema = create_schema
        self.update_schema = update_schema
        self.state_machine = state_machine
        self.entity_spec = entity_spec

        # Repository for SQLite persistence
        self._repository = repository

        # In-memory store as fallback (for testing without database)
        self._store: dict[UUID, T] = {}

        # Lifecycle event callbacks (v0.24.0)
        self._on_created_callbacks: list[EntityEventCallback] = []
        self._on_updated_callbacks: list[EntityEventCallback] = []
        self._on_deleted_callbacks: list[EntityEventCallback] = []

    def on_created(self, callback: EntityEventCallback) -> None:
        """Register a callback to be called after entity creation."""
        self._on_created_callbacks.append(callback)

    def on_updated(self, callback: EntityEventCallback) -> None:
        """Register a callback to be called after entity update."""
        self._on_updated_callbacks.append(callback)

    def on_deleted(self, callback: EntityEventCallback) -> None:
        """Register a callback to be called after entity deletion."""
        self._on_deleted_callbacks.append(callback)

    async def _notify_created(self, entity_id: str, entity_data: dict[str, Any]) -> None:
        """Notify all on_created callbacks."""
        import asyncio

        for callback in self._on_created_callbacks:
            try:
                result = callback(self.entity_name, entity_id, entity_data, None)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                # Log but don't fail the operation
                import logging

                logging.getLogger("dazzle.service").warning(
                    f"Entity created callback failed for {self.entity_name}: {e}"
                )

    async def _notify_updated(
        self, entity_id: str, entity_data: dict[str, Any], old_data: dict[str, Any]
    ) -> None:
        """Notify all on_updated callbacks."""
        import asyncio

        for callback in self._on_updated_callbacks:
            try:
                result = callback(self.entity_name, entity_id, entity_data, old_data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                # Log but don't fail the operation
                import logging

                logging.getLogger("dazzle.service").warning(
                    f"Entity updated callback failed for {self.entity_name}: {e}"
                )

    async def _notify_deleted(self, entity_id: str, entity_data: dict[str, Any]) -> None:
        """Notify all on_deleted callbacks."""
        import asyncio

        for callback in self._on_deleted_callbacks:
            try:
                result = callback(self.entity_name, entity_id, entity_data, None)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                # Log but don't fail the operation
                import logging

                logging.getLogger("dazzle.service").warning(
                    f"Entity deleted callback failed for {self.entity_name}: {e}"
                )

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
        """
        Create a new entity.

        Validates:
        - Invariants are satisfied
        - Foreign key references exist

        Applies:
        - Default values for missing fields
        """
        from dazzle_back.runtime.invariant_evaluator import (
            InvariantViolationError,
            check_invariants_for_create,
        )

        # Generate ID
        entity_id = uuid4()

        # Build entity data
        entity_data = {"id": entity_id, **data.model_dump()}

        # Apply default values for fields not provided (v0.14.2)
        if self.entity_spec:
            for field in self.entity_spec.fields:
                if field.name not in entity_data or entity_data[field.name] is None:
                    if field.default is not None:
                        entity_data[field.name] = field.default

        # Validate invariants (v0.14.2)
        if self.entity_spec and self.entity_spec.invariants:
            try:
                check_invariants_for_create(self.entity_spec.invariants, entity_data)
            except InvariantViolationError:
                raise  # Re-raise as-is

        # Validate foreign key references (v0.14.2)
        if self.entity_spec and self._repository:
            await self._validate_references(entity_data)

        # Use repository if available
        if self._repository:
            entity = await self._repository.create(entity_data)
        else:
            # Fallback to in-memory
            entity = self.model_class(**entity_data)
            self._store[entity_id] = entity

        # Notify callbacks (v0.24.0 - process triggering)
        await self._notify_created(str(entity_id), entity_data)

        return entity

    async def read(self, id: UUID) -> T | None:
        """Read an entity by ID."""
        if self._repository:
            return await self._repository.read(id)
        return self._store.get(id)

    async def update(
        self,
        id: UUID,
        data: UpdateT,
        user_roles: list[str] | None = None,
    ) -> T | None:
        """
        Update an existing entity.

        Validates:
        - State machine transitions are valid
        - Invariants are satisfied after update
        - Foreign key references exist

        Args:
            id: Entity ID to update
            data: Update data
            user_roles: User's roles for state machine role guard checks

        Returns:
            Updated entity or None if not found

        Raises:
            TransitionError: If state machine transition is invalid
            InvariantViolationError: If invariant constraint is violated
            ReferenceNotFoundError: If referenced entity doesn't exist
        """
        from dazzle_back.runtime.invariant_evaluator import (
            InvariantViolationError,
            check_invariants_for_update,
        )
        from dazzle_back.runtime.state_machine import (
            validate_status_update,
        )

        # Get update data, excluding None values
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}

        # Read current entity for state machine validation
        current = await self.read(id)
        if current is None:
            return None

        current_data = current.model_dump() if hasattr(current, "model_dump") else dict(current)

        # Validate state machine transition if entity has a state machine
        if self.state_machine:
            result = validate_status_update(
                self.state_machine,
                current_data,
                update_data,
                user_roles,
            )
            if result is not None and not result.is_valid:
                raise result.error  # type: ignore

        # Validate invariants after update (v0.14.2)
        if self.entity_spec and self.entity_spec.invariants:
            try:
                check_invariants_for_update(
                    self.entity_spec.invariants,
                    current_data,
                    update_data,
                )
            except InvariantViolationError:
                raise  # Re-raise as-is

        # Validate foreign key references (v0.14.2)
        if self.entity_spec and self._repository:
            await self._validate_references(update_data)

        if self._repository:
            updated = await self._repository.update(id, update_data)
        else:
            # Fallback to in-memory
            existing = self._store.get(id)
            if not existing:
                return None

            # Merge with existing
            merged_data = {**existing.model_dump(), **update_data}

            # Create updated instance
            updated = self.model_class(**merged_data)
            self._store[id] = updated

        if updated is not None:
            # Get updated entity data for notification
            updated_data = updated.model_dump() if hasattr(updated, "model_dump") else dict(updated)
            # Notify callbacks (v0.24.0 - process triggering)
            await self._notify_updated(str(id), updated_data, current_data)

        return updated

    async def delete(self, id: UUID) -> bool:
        """Delete an entity by ID."""
        # Read entity data before deletion for notification
        entity = await self.read(id)
        if entity is None:
            return False

        entity_data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)

        if self._repository:
            deleted = await self._repository.delete(id)
        else:
            if id in self._store:
                del self._store[id]
                deleted = True
            else:
                deleted = False

        if deleted:
            # Notify callbacks (v0.24.0 - process triggering)
            await self._notify_deleted(str(id), entity_data)

        return deleted

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
        sort: list[str] | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """
        List entities with pagination and filtering.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            filters: Optional filter criteria
            sort: Optional sort fields (prefix with '-' for descending)
            search: Optional full-text search query

        Returns:
            Dictionary with items, total, page, and page_size
        """
        if self._repository:
            return await self._repository.list(page, page_size, filters, sort=sort, search=search)

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

    def _apply_filters(self, items: builtins.list[T], filters: dict[str, Any]) -> builtins.list[T]:
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

    async def _validate_references(self, data: dict[str, Any]) -> None:
        """
        Validate that all foreign key references point to existing entities.

        v0.14.2: Added to ensure referential integrity.

        Args:
            data: Entity data to validate

        Raises:
            ReferenceNotFoundError: If a referenced entity doesn't exist
        """
        if not self.entity_spec or not self._repository:
            return

        # Get ref fields from entity spec
        for field in self.entity_spec.fields:
            if field.type.kind == "ref" and field.type.ref_entity:
                ref_value = data.get(field.name)
                if ref_value is not None:
                    # Need to check if the referenced entity exists
                    # Import repository factory to get the right repo

                    # Get the database manager from our repository
                    db = self._repository.db

                    # Check if referenced entity exists
                    ref_entity = field.type.ref_entity
                    ref_id = str(ref_value) if not isinstance(ref_value, str) else ref_value

                    with db.connection() as conn:
                        from dazzle_back.runtime.query_builder import quote_identifier

                        table = quote_identifier(ref_entity)
                        sql = f'SELECT 1 FROM {table} WHERE "id" = ? LIMIT 1'
                        cursor = conn.execute(sql, (ref_id,))
                        exists = cursor.fetchone() is not None

                    if not exists:
                        from dazzle_back.runtime.invariant_evaluator import (
                            InvariantViolationError,
                        )

                        raise InvariantViolationError(
                            f"Referenced {ref_entity} with ID '{ref_id}' not found "
                            f"(field: {field.name})"
                        )


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

    def __init__(
        self,
        models: dict[str, type[BaseModel]],
        state_machines: dict[str, StateMachineSpec] | None = None,
        entity_specs: dict[str, EntitySpec] | None = None,
    ):
        """
        Initialize the service factory.

        Args:
            models: Dictionary mapping entity names to Pydantic models
            state_machines: Dictionary mapping entity names to state machine specs
            entity_specs: Dictionary mapping entity names to full entity specs (v0.14.2)
        """
        self.models = models
        self.state_machines = state_machines or {}
        self.entity_specs = entity_specs or {}
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

            # Get state machine for this entity
            state_machine = self.state_machines.get(entity_name)

            # Get full entity spec for validation (v0.14.2)
            entity_spec = self.entity_specs.get(entity_name)

            service: BaseService[Any] = CRUDService(
                entity_name=entity_name,
                model_class=model,
                create_schema=create_schema,
                update_schema=update_schema,
                state_machine=state_machine,
                entity_spec=entity_spec,
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
