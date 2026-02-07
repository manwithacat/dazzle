"""
Resolver Generator - Generate GraphQL resolvers from BackendSpec.

Creates resolvers that delegate to the DNR service layer while
enforcing multi-tenant isolation through context.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from dazzle_back.graphql.context import GraphQLContext
from dazzle_back.specs.entity import EntitySpec

# Strawberry is optional
try:
    import strawberry

    STRAWBERRY_AVAILABLE = True
except ImportError:
    STRAWBERRY_AVAILABLE = False
    strawberry = None  # type: ignore

if TYPE_CHECKING:
    from dazzle_back.specs import BackendSpec


class ResolverGenerator:
    """
    Generate GraphQL resolvers from BackendSpec.

    Resolvers are generated for:
    - Query: get by ID, list with pagination
    - Mutation: create, update, delete

    All resolvers:
    - Extract tenant_id from context (never from args)
    - Delegate to service layer
    - Handle errors uniformly
    """

    def __init__(
        self,
        spec: BackendSpec,
        services: dict[str, Any],
        repositories: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the resolver generator.

        Args:
            spec: BackendSpec defining entities and services
            services: Dictionary of service instances by name
            repositories: Optional dictionary of repository instances
        """
        if not STRAWBERRY_AVAILABLE:
            raise RuntimeError(
                "Strawberry is not installed. Install with: pip install strawberry-graphql"
            )
        self.spec = spec
        self.services = services
        self.repositories = repositories or {}
        self._query_resolvers: dict[str, Callable[..., Any]] = {}
        self._mutation_resolvers: dict[str, Callable[..., Any]] = {}

    def generate_resolvers(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Generate all resolvers.

        Returns:
            Tuple of (query_resolvers, mutation_resolvers)
        """
        for entity in self.spec.entities:
            self._generate_entity_resolvers(entity)

        return self._query_resolvers, self._mutation_resolvers

    def _generate_entity_resolvers(self, entity: EntitySpec) -> None:
        """Generate CRUD resolvers for an entity."""
        entity_name = entity.name
        entity_lower = _camel_case(entity_name)

        # Find the service for this entity
        service = self._find_service_for_entity(entity_name)

        # Generate query resolvers
        self._query_resolvers[entity_lower] = self._create_get_resolver(entity_name, service)
        self._query_resolvers[f"{entity_lower}s"] = self._create_list_resolver(entity_name, service)

        # Generate mutation resolvers
        self._mutation_resolvers[f"create{entity_name}"] = self._create_create_resolver(
            entity_name, service
        )
        self._mutation_resolvers[f"update{entity_name}"] = self._create_update_resolver(
            entity_name, service
        )
        self._mutation_resolvers[f"delete{entity_name}"] = self._create_delete_resolver(
            entity_name, service
        )

    def _find_service_for_entity(self, entity_name: str) -> Any | None:
        """Find the service that handles operations for an entity."""
        # Look for entity-specific services
        for svc in self.services.values():
            if hasattr(svc, "entity_name") and svc.entity_name == entity_name:
                return svc
        return None

    def _create_get_resolver(self, entity_name: str, service: Any | None) -> Callable[..., Any]:
        """Create a resolver for getting a single entity by ID."""
        repo = self.repositories.get(entity_name)

        async def resolve_get(
            info: strawberry.Info,
            id: str,
        ) -> Any | None:
            ctx: GraphQLContext = info.context

            # Use repository if available
            if repo:
                # Apply tenant filter if tenant context exists
                filters = {}
                if ctx.tenant_id:
                    filters["tenant_id"] = ctx.tenant_id

                try:
                    result = repo.get_by_id(id)
                    # Verify tenant ownership
                    if result and ctx.tenant_id:
                        if hasattr(result, "tenant_id") and result.tenant_id != ctx.tenant_id:
                            return None
                    return result
                except Exception:
                    return None

            # Fall back to service
            if service and hasattr(service, "get"):
                try:
                    return await _maybe_await(service.get(id, tenant_id=ctx.tenant_id))
                except Exception:
                    return None

            return None

        return resolve_get

    def _create_list_resolver(self, entity_name: str, service: Any | None) -> Callable[..., Any]:
        """Create a resolver for listing entities with pagination."""
        repo = self.repositories.get(entity_name)

        async def resolve_list(
            info: strawberry.Info,
            limit: int | None = 100,
            offset: int | None = 0,
        ) -> list[Any]:
            ctx: GraphQLContext = info.context

            # Use repository if available
            if repo:
                try:
                    filters = {}
                    if ctx.tenant_id:
                        filters["tenant_id"] = ctx.tenant_id

                    results: list[Any] = repo.list(
                        limit=limit or 100,
                        offset=offset or 0,
                        filters=filters if filters else None,
                    )
                    return results
                except Exception:
                    return []

            # Fall back to service
            if service and hasattr(service, "list"):
                try:
                    svc_result: list[Any] = await _maybe_await(
                        service.list(
                            limit=limit,
                            offset=offset,
                            tenant_id=ctx.tenant_id,
                        )
                    )
                    return svc_result
                except Exception:
                    return []

            return []

        return resolve_list

    def _create_create_resolver(self, entity_name: str, service: Any | None) -> Callable[..., Any]:
        """Create a resolver for creating a new entity."""
        repo = self.repositories.get(entity_name)

        async def resolve_create(
            info: strawberry.Info,
            input: Any,
        ) -> Any:
            ctx: GraphQLContext = info.context
            ctx.require_authenticated()

            # Convert input to dict
            data = _input_to_dict(input)

            # Add tenant context
            if ctx.tenant_id:
                data["tenant_id"] = ctx.tenant_id

            # Add user context
            if ctx.user_id:
                data["created_by"] = ctx.user_id

            # Use repository if available
            if repo:
                try:
                    return repo.create(data)
                except Exception as e:
                    raise ValueError(f"Failed to create {entity_name}: {e}")

            # Fall back to service
            if service and hasattr(service, "create"):
                try:
                    return await _maybe_await(service.create(data))
                except Exception as e:
                    raise ValueError(f"Failed to create {entity_name}: {e}")

            raise ValueError(f"No service or repository for {entity_name}")

        return resolve_create

    def _create_update_resolver(self, entity_name: str, service: Any | None) -> Callable[..., Any]:
        """Create a resolver for updating an entity."""
        repo = self.repositories.get(entity_name)

        async def resolve_update(
            info: strawberry.Info,
            id: str,
            input: Any,
        ) -> Any:
            ctx: GraphQLContext = info.context
            ctx.require_authenticated()

            # Convert input to dict, excluding None values
            data = _input_to_dict(input, exclude_none=True)

            # Add user context
            if ctx.user_id:
                data["updated_by"] = ctx.user_id

            # Use repository if available
            if repo:
                try:
                    # Verify tenant ownership
                    existing = repo.get_by_id(id)
                    if not existing:
                        raise ValueError(f"{entity_name} not found")
                    if ctx.tenant_id and hasattr(existing, "tenant_id"):
                        if existing.tenant_id != ctx.tenant_id:
                            raise PermissionError("Access denied")

                    return repo.update(id, data)
                except (ValueError, PermissionError):
                    raise
                except Exception as e:
                    raise ValueError(f"Failed to update {entity_name}: {e}")

            # Fall back to service
            if service and hasattr(service, "update"):
                try:
                    return await _maybe_await(service.update(id, data, tenant_id=ctx.tenant_id))
                except Exception as e:
                    raise ValueError(f"Failed to update {entity_name}: {e}")

            raise ValueError(f"No service or repository for {entity_name}")

        return resolve_update

    def _create_delete_resolver(self, entity_name: str, service: Any | None) -> Callable[..., Any]:
        """Create a resolver for deleting an entity."""
        repo = self.repositories.get(entity_name)

        async def resolve_delete(
            info: strawberry.Info,
            id: str,
        ) -> bool:
            ctx: GraphQLContext = info.context
            ctx.require_authenticated()

            # Use repository if available
            if repo:
                try:
                    # Verify tenant ownership
                    existing = repo.get_by_id(id)
                    if not existing:
                        return False
                    if ctx.tenant_id and hasattr(existing, "tenant_id"):
                        if existing.tenant_id != ctx.tenant_id:
                            raise PermissionError("Access denied")

                    repo.delete(id)
                    return True
                except PermissionError:
                    raise
                except Exception:
                    return False

            # Fall back to service
            if service and hasattr(service, "delete"):
                try:
                    await _maybe_await(service.delete(id, tenant_id=ctx.tenant_id))
                    return True
                except Exception:
                    return False

            return False

        return resolve_delete

    def create_query_type(self) -> type:
        """Create a Strawberry Query type with all resolvers."""
        query_resolvers, _ = self.generate_resolvers()

        # Build methods
        methods: dict[str, Any] = {}

        for name, resolver in query_resolvers.items():
            methods[name] = strawberry.field(resolver=resolver)

        # Create Query class
        query_class = type("Query", (), methods)
        return strawberry.type(query_class)

    def create_mutation_type(self) -> type:
        """Create a Strawberry Mutation type with all resolvers."""
        _, mutation_resolvers = self.generate_resolvers()

        methods: dict[str, Any] = {}

        for name, resolver in mutation_resolvers.items():
            methods[name] = strawberry.mutation(resolver=resolver)

        mutation_class = type("Mutation", (), methods)
        return strawberry.type(mutation_class)


def _camel_case(name: str) -> str:
    """Convert PascalCase to camelCase."""
    if not name:
        return name
    return name[0].lower() + name[1:]


def _pascal_case(name: str) -> str:
    """Convert camelCase to PascalCase."""
    if not name:
        return name
    return name[0].upper() + name[1:]


def _input_to_dict(input_obj: Any, exclude_none: bool = False) -> dict[str, Any]:
    """Convert a Strawberry input object to a dictionary."""
    if hasattr(input_obj, "__dict__"):
        data = {k: v for k, v in input_obj.__dict__.items() if not k.startswith("_")}
    elif hasattr(input_obj, "model_dump"):
        data = input_obj.model_dump()
    elif isinstance(input_obj, dict):
        data = input_obj
    else:
        data = dict(input_obj)

    if exclude_none:
        data = {k: v for k, v in data.items() if v is not None}

    return data


async def _maybe_await(value: Any) -> Any:
    """Await a value if it's a coroutine, otherwise return it."""
    import asyncio

    if asyncio.iscoroutine(value):
        return await value
    return value
