"""
GraphQL BFF Layer for DNR Backend.

This module provides GraphQL schema generation and resolver scaffolding
from BackendSpec, implementing the BFF/Facade pattern.

Key components:
- context: Multi-tenant GraphQL context
- schema_generator: Generate Strawberry types from EntitySpec
- resolver_generator: Generate resolvers for CRUD operations
- integration: FastAPI/Strawberry integration
- adapters: External API adapter interface for BFF facade
"""

from dazzle_dnr_back.graphql.adapters import (
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
from dazzle_dnr_back.graphql.context import GraphQLContext
from dazzle_dnr_back.graphql.integration import create_graphql_app, mount_graphql
from dazzle_dnr_back.graphql.resolver_generator import ResolverGenerator
from dazzle_dnr_back.graphql.schema_generator import SchemaGenerator

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
