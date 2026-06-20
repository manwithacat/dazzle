"""
Endpoint specification types for BackendSpec.

Defines HTTP/RPC endpoint mappings for services.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# HTTP Method
# =============================================================================


class HttpMethod(StrEnum):
    """HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


# =============================================================================
# Rate Limiting
# =============================================================================


class RateLimitSpec(BaseModel):
    """
    Rate limiting configuration for an endpoint.

    Example:
        RateLimitSpec(requests=100, window_seconds=60)  # 100 requests per minute
    """

    model_config = ConfigDict(frozen=True)

    requests: int = Field(description="Number of allowed requests")
    window_seconds: int = Field(description="Time window in seconds")
    strategy: str = Field(default="sliding_window", description="Rate limiting strategy")


# =============================================================================
# Endpoints
# =============================================================================


class EndpointSpec(BaseModel):
    """
    HTTP endpoint specification.

    Maps a service to an HTTP endpoint with method, path, auth, and rate limiting.

    Example:
        EndpointSpec(
            name="create_invoice",
            service="create_invoice",
            method=HttpMethod.POST,
            path="/invoices",
            auth=AuthRuleSpec(required=True, roles=["admin", "user"]),
            rate_limit=RateLimitSpec(requests=100, window_seconds=60)
        )
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Endpoint name")
    service: str = Field(description="Service name to invoke")
    method: HttpMethod = Field(description="HTTP method")
    path: str = Field(description="URL path (e.g., /invoices)")
    description: str | None = Field(default=None, description="Endpoint description")
    tags: list[str] = Field(default_factory=list, description="OpenAPI tags for grouping")
    rate_limit: RateLimitSpec | None = Field(
        default=None, description="Rate limiting configuration"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    require_roles: list[str] = Field(
        default_factory=list,
        description="Roles (persona IDs) required to access this endpoint",
    )
    deny_roles: list[str] = Field(
        default_factory=list,
        description="Roles (persona IDs) denied from accessing this endpoint",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Ensure path starts with /."""
        if not v.startswith("/"):
            raise ValueError(f"Path '{v}' must start with /")
        return v

    @property
    def full_path(self) -> str:
        """Get full path with method."""
        return f"{self.method.value} {self.path}"
