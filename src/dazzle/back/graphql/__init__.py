"""
GraphQL BFF Layer for Dazzle backend runtime.

This module provides GraphQL schema generation and resolver scaffolding
from BackendSpec, implementing the BFF/Facade pattern.

Key components:
- context: Multi-tenant GraphQL context
- schema_generator: Generate Strawberry types from EntitySpec
- resolver_generator: Generate resolvers for CRUD operations
- integration: FastAPI/Strawberry integration
- adapters: External API adapter interface for BFF facade
"""

from dazzle.back.graphql.adapters import (
    AdapterConfig,
    AdapterError,
    AdapterResponse,
    AdapterResult,
    BaseExternalAdapter,
    ErrorCategory,
    ErrorSeverity,
    NormalizedError,
    normalize_error,
)
from dazzle.back.graphql.context import GraphQLContext
from dazzle.back.graphql.integration import create_graphql_app, mount_graphql
from dazzle.back.graphql.resolver_generator import ResolverGenerator
from dazzle.back.graphql.schema_generator import SchemaGenerator

__all__ = [
    # Core components
    "GraphQLContext",
    "SchemaGenerator",
    "ResolverGenerator",
    "create_graphql_app",
    "mount_graphql",
    # Adapter interface
    "BaseExternalAdapter",
    "AdapterConfig",
    "AdapterResponse",
    "AdapterResult",
    "AdapterError",
    # Error normalization
    "NormalizedError",
    "ErrorCategory",
    "ErrorSeverity",
    "normalize_error",
]
