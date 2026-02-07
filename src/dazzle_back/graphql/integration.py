"""
FastAPI/Strawberry integration for GraphQL BFF layer.

Provides utilities for mounting GraphQL on an existing FastAPI app
or creating a standalone GraphQL application.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from dazzle_back.graphql.context import GraphQLContext
from dazzle_back.graphql.resolver_generator import ResolverGenerator
from dazzle_back.graphql.schema_generator import SchemaGenerator

# Check for dependencies
try:
    import strawberry
    from strawberry.fastapi import GraphQLRouter

    STRAWBERRY_AVAILABLE = True
except ImportError:
    STRAWBERRY_AVAILABLE = False
    strawberry = None  # type: ignore
    GraphQLRouter = None  # type: ignore

try:
    from fastapi import FastAPI

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore

if TYPE_CHECKING:
    from dazzle_back.specs import BackendSpec


def create_graphql_app(
    spec: BackendSpec,
    services: dict[str, Any] | None = None,
    repositories: dict[str, Any] | None = None,
    path: str = "/graphql",
    enable_graphiql: bool = True,
) -> FastAPI:
    """
    Create a standalone FastAPI application with GraphQL endpoint.

    This creates a new FastAPI app with just the GraphQL endpoint.
    Use mount_graphql() to add GraphQL to an existing app.

    Args:
        spec: BackendSpec defining the schema
        services: Service instances for resolvers (optional)
        repositories: Repository instances for resolvers (optional)
        path: URL path for GraphQL endpoint (default: /graphql)
        enable_graphiql: Enable GraphiQL IDE (default: True)

    Returns:
        FastAPI application with GraphQL endpoint

    Example:
        from dazzle_back.specs import BackendSpec
        from dazzle_back.graphql import create_graphql_app

        spec = BackendSpec(name="myapp", ...)
        app = create_graphql_app(spec)
        # Run with: uvicorn mymodule:app
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed. Install with: pip install fastapi")

    if not STRAWBERRY_AVAILABLE:
        raise RuntimeError(
            "Strawberry is not installed. Install with: pip install strawberry-graphql"
        )

    app = FastAPI(
        title=f"{spec.name} GraphQL API",
        description=f"GraphQL BFF for {spec.name}",
    )

    mount_graphql(
        app,
        spec,
        services=services,
        repositories=repositories,
        path=path,
        enable_graphiql=enable_graphiql,
    )

    return app


def mount_graphql(
    app: FastAPI,
    spec: BackendSpec,
    services: dict[str, Any] | None = None,
    repositories: dict[str, Any] | None = None,
    path: str = "/graphql",
    enable_graphiql: bool = True,
) -> None:
    """
    Mount GraphQL endpoint on an existing FastAPI application.

    This adds a GraphQL endpoint to your existing REST API.

    Args:
        app: Existing FastAPI application
        spec: BackendSpec defining the schema
        services: Service instances for resolvers (optional)
        repositories: Repository instances for resolvers (optional)
        path: URL path for GraphQL endpoint (default: /graphql)
        enable_graphiql: Enable GraphiQL IDE (default: True)

    Example:
        from fastapi import FastAPI
        from dazzle_back.graphql import mount_graphql

        app = FastAPI()
        # ... your existing routes ...

        mount_graphql(app, spec)
        # GraphQL available at /graphql
    """
    if not STRAWBERRY_AVAILABLE:
        raise RuntimeError(
            "Strawberry is not installed. Install with: pip install strawberry-graphql"
        )

    # Generate schema
    schema = create_schema(
        spec,
        services=services or {},
        repositories=repositories or {},
    )

    # Create context getter - Strawberry expects a custom_context dict
    async def get_context() -> dict[str, Any]:
        # Return an empty context that will be populated by request
        return {}

    # Create router without context_getter - use default behavior
    graphql_router = GraphQLRouter(
        schema,
        graphiql=enable_graphiql,
    )

    # Mount on app
    app.include_router(graphql_router, prefix=path)


def create_schema(
    spec: BackendSpec,
    services: dict[str, Any] | None = None,
    repositories: dict[str, Any] | None = None,
) -> Any:
    """
    Create a Strawberry GraphQL schema from BackendSpec.

    Args:
        spec: BackendSpec defining entities
        services: Service instances for resolvers
        repositories: Repository instances for resolvers

    Returns:
        Strawberry Schema object
    """
    if not STRAWBERRY_AVAILABLE:
        raise RuntimeError(
            "Strawberry is not installed. Install with: pip install strawberry-graphql"
        )

    services = services or {}
    repositories = repositories or {}

    # Generate types
    schema_gen = SchemaGenerator(spec)
    schema_gen.generate_types()

    # Generate resolvers
    resolver_gen = ResolverGenerator(spec, services, repositories)

    # Create Query type
    Query = _create_query_type(spec, resolver_gen, schema_gen)

    # Create Mutation type
    Mutation = _create_mutation_type(spec, resolver_gen, schema_gen)

    # Create schema
    return strawberry.Schema(query=Query, mutation=Mutation)


def _create_query_type(
    spec: BackendSpec,
    resolver_gen: ResolverGenerator,
    schema_gen: SchemaGenerator,
) -> type:
    """Create the Query type with all entity resolvers."""
    query_resolvers, _ = resolver_gen.generate_resolvers()

    # Build class dynamically with proper type annotations
    class_dict: dict[str, Any] = {}
    annotations: dict[str, Any] = {}

    for entity in spec.entities:
        entity_name = entity.name
        entity_lower = _camel_case(entity_name)

        # Get resolver
        get_resolver = query_resolvers.get(entity_lower)
        list_resolver = query_resolvers.get(f"{entity_lower}s")

        # Get type
        entity_type = schema_gen.get_type(entity_name)

        if get_resolver and entity_type:
            # Single entity resolver - returns Optional[EntityType]
            optional_type = entity_type | None
            class_dict[entity_lower] = strawberry.field(
                resolver=get_resolver,
                description=f"Get {entity_name} by ID",
                graphql_type=optional_type,
            )
            annotations[entity_lower] = optional_type

        if list_resolver and entity_type:
            # List resolver - returns List[EntityType]
            list_type = list[entity_type]  # type: ignore[valid-type]
            class_dict[f"{entity_lower}s"] = strawberry.field(
                resolver=list_resolver,
                description=f"List all {entity_name}s",
                graphql_type=list_type,
            )
            annotations[f"{entity_lower}s"] = list_type

    # Add annotations to class dict
    class_dict["__annotations__"] = annotations

    # Create Query class
    Query = type("Query", (), class_dict)
    return strawberry.type(Query)


def _create_mutation_type(
    spec: BackendSpec,
    resolver_gen: ResolverGenerator,
    schema_gen: SchemaGenerator,
) -> type:
    """Create the Mutation type with all entity resolvers."""
    class_dict: dict[str, Any] = {}
    annotations: dict[str, Any] = {}

    for entity in spec.entities:
        entity_name = entity.name

        # Get types
        entity_type = schema_gen.get_type(entity_name)
        input_create_type = schema_gen.get_input_type(f"{entity_name}CreateInput")
        input_update_type = schema_gen.get_input_type(f"{entity_name}UpdateInput")

        if not entity_type:
            continue

        # Create resolver - use typed wrapper functions
        repo = resolver_gen.repositories.get(entity_name)

        if input_create_type:
            create_resolver = _make_create_resolver(entity_name, repo, input_create_type)
            class_dict[f"create{entity_name}"] = strawberry.mutation(
                resolver=create_resolver,
                description=f"Create a new {entity_name}",
                graphql_type=entity_type,
            )
            annotations[f"create{entity_name}"] = entity_type

        if input_update_type:
            update_resolver = _make_update_resolver(entity_name, repo, input_update_type)
            class_dict[f"update{entity_name}"] = strawberry.mutation(
                resolver=update_resolver,
                description=f"Update an existing {entity_name}",
                graphql_type=entity_type,
            )
            annotations[f"update{entity_name}"] = entity_type

        delete_resolver = _make_delete_resolver(entity_name, repo)
        class_dict[f"delete{entity_name}"] = strawberry.mutation(
            resolver=delete_resolver,
            description=f"Delete a {entity_name}",
            graphql_type=bool,
        )
        annotations[f"delete{entity_name}"] = bool

    # Add annotations to class dict
    class_dict["__annotations__"] = annotations

    # Create Mutation class
    Mutation = type("Mutation", (), class_dict)
    return strawberry.type(Mutation)


def _make_create_resolver(entity_name: str, repo: Any, input_type: type) -> Callable[..., Any]:
    """Create a typed resolver for creating entities."""

    async def resolve_create(info: strawberry.Info, input: Any) -> Any:
        from dazzle_back.graphql.resolver_generator import _input_to_dict

        ctx: GraphQLContext = info.context

        # Convert input to dict
        data = _input_to_dict(input)

        # Add tenant context
        if ctx.tenant_id:
            data["tenant_id"] = ctx.tenant_id

        if ctx.user_id:
            data["created_by"] = ctx.user_id

        if repo:
            try:
                return repo.create(data)
            except Exception as e:
                raise ValueError(f"Failed to create {entity_name}: {e}")

        raise ValueError(f"No repository for {entity_name}")

    # Set __annotations__ to tell Strawberry the types (include info with proper type)
    resolve_create.__annotations__ = {
        "info": strawberry.Info,
        "input": input_type,
        "return": Any,
    }
    return resolve_create


def _make_update_resolver(entity_name: str, repo: Any, input_type: type) -> Callable[..., Any]:
    """Create a typed resolver for updating entities."""

    async def resolve_update(info: strawberry.Info, id: str, input: Any) -> Any:
        from dazzle_back.graphql.resolver_generator import _input_to_dict

        ctx: GraphQLContext = info.context

        # Convert input to dict, excluding None values
        data = _input_to_dict(input, exclude_none=True)

        if ctx.user_id:
            data["updated_by"] = ctx.user_id

        if repo:
            try:
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

        raise ValueError(f"No repository for {entity_name}")

    resolve_update.__annotations__ = {
        "info": strawberry.Info,
        "id": str,
        "input": input_type,
        "return": Any,
    }
    return resolve_update


def _make_delete_resolver(entity_name: str, repo: Any) -> Callable[..., Any]:
    """Create a typed resolver for deleting entities."""

    async def resolve_delete(info: strawberry.Info, id: str) -> bool:
        ctx: GraphQLContext = info.context

        if repo:
            try:
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

        return False

    resolve_delete.__annotations__ = {
        "info": strawberry.Info,
        "id": str,
        "return": bool,
    }
    return resolve_delete


def _camel_case(name: str) -> str:
    """Convert PascalCase to camelCase."""
    if not name:
        return name
    return name[0].lower() + name[1:]


# =============================================================================
# Schema Inspection
# =============================================================================


def print_schema(spec: BackendSpec) -> str:
    """
    Print the GraphQL schema SDL for a BackendSpec.

    Args:
        spec: BackendSpec to generate schema from

    Returns:
        GraphQL SDL string
    """
    from dazzle_back.graphql.schema_generator import generate_schema_sdl

    return generate_schema_sdl(spec)


def inspect_schema(spec: BackendSpec) -> dict[str, Any]:
    """
    Get schema inspection data.

    Returns:
        Dictionary with schema statistics and structure
    """
    return {
        "entities": [e.name for e in spec.entities],
        "queries": [f"{_camel_case(e.name)}(id: ID!): {e.name}" for e in spec.entities]
        + [f"{_camel_case(e.name)}s(limit: Int, offset: Int): [{e.name}!]!" for e in spec.entities],
        "mutations": [
            f"create{e.name}(input: {e.name}CreateInput!): {e.name}!" for e in spec.entities
        ]
        + [
            f"update{e.name}(id: ID!, input: {e.name}UpdateInput!): {e.name}!"
            for e in spec.entities
        ]
        + [f"delete{e.name}(id: ID!): Boolean!" for e in spec.entities],
        "stats": {
            "entity_count": len(spec.entities),
            "query_count": len(spec.entities) * 2,  # get + list per entity
            "mutation_count": len(spec.entities) * 3,  # create + update + delete per entity
        },
    }
