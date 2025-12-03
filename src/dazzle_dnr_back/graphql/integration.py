"""
FastAPI/Strawberry integration for GraphQL BFF layer.

Provides utilities for mounting GraphQL on an existing FastAPI app
or creating a standalone GraphQL application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dazzle_dnr_back.graphql.context import GraphQLContext, create_context_from_request
from dazzle_dnr_back.graphql.resolver_generator import ResolverGenerator
from dazzle_dnr_back.graphql.schema_generator import SchemaGenerator

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
    from starlette.requests import Request

    from dazzle_dnr_back.specs import BackendSpec


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
        from dazzle_dnr_back.specs import BackendSpec
        from dazzle_dnr_back.graphql import create_graphql_app

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
        from dazzle_dnr_back.graphql import mount_graphql

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

    # Create context getter
    async def get_context(request: Request) -> GraphQLContext:
        return create_context_from_request(request)

    # Create router
    graphql_router = GraphQLRouter(
        schema,
        context_getter=get_context,
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

    # Build class dynamically
    class_dict: dict[str, Any] = {}

    for entity in spec.entities:
        entity_name = entity.name
        entity_lower = _camel_case(entity_name)

        # Get resolver
        get_resolver = query_resolvers.get(entity_lower)
        list_resolver = query_resolvers.get(f"{entity_lower}s")

        # Get type
        entity_type = schema_gen.get_type(entity_name)

        if get_resolver and entity_type:
            # Single entity resolver
            class_dict[entity_lower] = strawberry.field(
                resolver=get_resolver,
                description=f"Get {entity_name} by ID",
            )

        if list_resolver and entity_type:
            # List resolver
            class_dict[f"{entity_lower}s"] = strawberry.field(
                resolver=list_resolver,
                description=f"List all {entity_name}s",
            )

    # Create Query class
    Query = type("Query", (), class_dict)
    return strawberry.type(Query)


def _create_mutation_type(
    spec: BackendSpec,
    resolver_gen: ResolverGenerator,
    schema_gen: SchemaGenerator,
) -> type:
    """Create the Mutation type with all entity resolvers."""
    _, mutation_resolvers = resolver_gen.generate_resolvers()

    class_dict: dict[str, Any] = {}

    for entity in spec.entities:
        entity_name = entity.name

        # Get resolvers
        create_resolver = mutation_resolvers.get(f"create{entity_name}")
        update_resolver = mutation_resolvers.get(f"update{entity_name}")
        delete_resolver = mutation_resolvers.get(f"delete{entity_name}")

        if create_resolver:
            class_dict[f"create{entity_name}"] = strawberry.mutation(
                resolver=create_resolver,
                description=f"Create a new {entity_name}",
            )

        if update_resolver:
            class_dict[f"update{entity_name}"] = strawberry.mutation(
                resolver=update_resolver,
                description=f"Update an existing {entity_name}",
            )

        if delete_resolver:
            class_dict[f"delete{entity_name}"] = strawberry.mutation(
                resolver=delete_resolver,
                description=f"Delete a {entity_name}",
            )

    # Create Mutation class
    Mutation = type("Mutation", (), class_dict)
    return strawberry.type(Mutation)


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
    from dazzle_dnr_back.graphql.schema_generator import generate_schema_sdl

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
