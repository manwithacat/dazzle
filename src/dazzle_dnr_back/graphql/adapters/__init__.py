"""
External API adapters for GraphQL BFF layer.

Provides a unified interface for integrating external REST APIs
(HMRC, banks, accounting platforms, etc.) into the GraphQL facade.
"""

from dazzle_dnr_back.graphql.adapters.base import (
    AdapterConfig,
    AdapterError,
    AdapterResponse,
    AdapterResult,
    ApiError,
    AuthenticationError,
    BaseExternalAdapter,
    PaginatedResponse,
    RateLimitConfig,
    RateLimitError,
    RetryConfig,
    TimeoutError,
    ValidationError,
)
from dazzle_dnr_back.graphql.adapters.errors import (
    ErrorCategory,
    ErrorSeverity,
    NormalizedError,
    normalize_error,
)

__all__ = [
    # Base adapter
    "BaseExternalAdapter",
    "AdapterConfig",
    "RetryConfig",
    "RateLimitConfig",
    # Response types
    "AdapterResponse",
    "AdapterResult",
    "PaginatedResponse",
    # Error types
    "AdapterError",
    "ApiError",
    "AuthenticationError",
    "RateLimitError",
    "TimeoutError",
    "ValidationError",
    # Error normalization
    "NormalizedError",
    "ErrorCategory",
    "ErrorSeverity",
    "normalize_error",
]
