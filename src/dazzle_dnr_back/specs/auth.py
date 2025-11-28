"""
Authentication and authorization specification types for BackendSpec.

Defines auth rules, tenancy, permissions, and roles.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Roles and Permissions
# =============================================================================


class PermissionSpec(BaseModel):
    """
    Permission specification.

    Example:
        PermissionSpec(name="invoice:create", description="Create invoices")
    """

    name: str = Field(description="Permission name (e.g., 'invoice:create')")
    description: str | None = Field(default=None, description="Permission description")
    resource: str | None = Field(
        default=None, description="Resource this permission applies to"
    )
    actions: list[str] = Field(
        default_factory=list, description="Actions allowed (create, read, update, delete)"
    )

    class Config:
        frozen = True


class RoleSpec(BaseModel):
    """
    Role specification.

    Example:
        RoleSpec(name="admin", permissions=["*"], description="Administrator role")
        RoleSpec(name="user", permissions=["invoice:read", "invoice:create"])
    """

    name: str = Field(description="Role name")
    description: str | None = Field(default=None, description="Role description")
    permissions: list[str] = Field(
        default_factory=list, description="Permission names"
    )
    inherits: list[str] = Field(
        default_factory=list, description="Inherited roles"
    )

    class Config:
        frozen = True


# =============================================================================
# Authentication
# =============================================================================


class AuthScheme(str, Enum):
    """Authentication schemes."""

    BEARER = "bearer"
    API_KEY = "api_key"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    CUSTOM = "custom"


class AuthRuleSpec(BaseModel):
    """
    Authentication rule for an endpoint.

    Example:
        AuthRuleSpec(required=True, scheme=AuthScheme.BEARER, roles=["admin", "user"])
        AuthRuleSpec(required=False)  # Public endpoint
    """

    required: bool = Field(
        default=True, description="Is authentication required?"
    )
    scheme: AuthScheme = Field(
        default=AuthScheme.BEARER, description="Authentication scheme"
    )
    roles: list[str] = Field(
        default_factory=list, description="Required roles (any of)"
    )
    permissions: list[str] = Field(
        default_factory=list, description="Required permissions (all of)"
    )
    custom_checks: list[str] = Field(
        default_factory=list, description="Custom auth check expressions"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    class Config:
        frozen = True

    @property
    def is_public(self) -> bool:
        """Check if this endpoint is public (no auth required)."""
        return not self.required


# =============================================================================
# Tenancy
# =============================================================================


class TenancyStrategy(str, Enum):
    """Multi-tenancy strategies."""

    NONE = "none"
    SINGLE = "single"
    DISCRIMINATOR = "discriminator"  # tenant_id column
    SCHEMA = "schema"  # separate DB schema per tenant
    DATABASE = "database"  # separate database per tenant


class TenancyRuleSpec(BaseModel):
    """
    Tenancy rule for an endpoint or entity.

    Example:
        TenancyRuleSpec(
            strategy=TenancyStrategy.DISCRIMINATOR,
            tenant_field="tenant_id",
            enforce=True
        )
    """

    strategy: TenancyStrategy = Field(
        default=TenancyStrategy.NONE, description="Tenancy strategy"
    )
    tenant_field: str | None = Field(
        default=None, description="Field name for tenant discriminator"
    )
    enforce: bool = Field(
        default=True, description="Enforce tenant isolation?"
    )
    allow_cross_tenant: bool = Field(
        default=False, description="Allow cross-tenant access for superusers?"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    class Config:
        frozen = True

    @property
    def is_multi_tenant(self) -> bool:
        """Check if multi-tenancy is enabled."""
        return self.strategy != TenancyStrategy.NONE
