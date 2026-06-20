"""
Authentication and authorization specification types for BackendSpec.

Defines auth rules, tenancy, permissions, roles, and entity access rules.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dazzle.core.access import (
    AccessAuthContext,
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    AccessPolicyEffect,
    EntityAccessSpec,
    PermissionRuleSpec,
    ScopeRuleSpec,
    VisibilityRuleSpec,
)

# Re-exports for back-side callers — the access-rule spec types moved to
# dazzle.core.access in #1096 to break the back↔ui cycle (#1086). Imports
# of these names from `dazzle.http.specs.auth` or `dazzle.http.specs`
# continue to work; new code should import directly from `dazzle.core.access`.
__all__ = [
    "AccessAuthContext",
    "AccessComparisonKind",
    "AccessConditionSpec",
    "AccessLogicalKind",
    "AccessOperationKind",
    "AccessPolicyEffect",
    "AuthRuleSpec",
    "AuthScheme",
    "EntityAccessSpec",
    "PermissionRuleSpec",
    "PermissionSpec",
    "RoleSpec",
    "ScopeRuleSpec",
    "TenancyRuleSpec",
    "TenancyStrategy",
    "VisibilityRuleSpec",
]

# =============================================================================
# Roles and Permissions
# =============================================================================


class PermissionSpec(BaseModel):
    """
    Permission specification.

    Example:
        PermissionSpec(name="invoice:create", description="Create invoices")
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Permission name (e.g., 'invoice:create')")
    description: str | None = Field(default=None, description="Permission description")
    resource: str | None = Field(default=None, description="Resource this permission applies to")
    actions: list[str] = Field(
        default_factory=list, description="Actions allowed (create, read, update, delete)"
    )


class RoleSpec(BaseModel):
    """
    Role specification.

    Example:
        RoleSpec(name="admin", permissions=["*"], description="Administrator role")
        RoleSpec(name="user", permissions=["invoice:read", "invoice:create"])
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Role name")
    description: str | None = Field(default=None, description="Role description")
    permissions: list[str] = Field(default_factory=list, description="Permission names")
    inherits: list[str] = Field(default_factory=list, description="Inherited roles")


# =============================================================================
# Authentication
# =============================================================================


class AuthScheme(StrEnum):
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

    model_config = ConfigDict(frozen=True)

    required: bool = Field(default=True, description="Is authentication required?")
    scheme: AuthScheme = Field(default=AuthScheme.BEARER, description="Authentication scheme")
    roles: list[str] = Field(default_factory=list, description="Required roles (any of)")
    permissions: list[str] = Field(
        default_factory=list, description="Required permissions (all of)"
    )
    custom_checks: list[str] = Field(
        default_factory=list, description="Custom auth check expressions"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @property
    def is_public(self) -> bool:
        """Check if this endpoint is public (no auth required)."""
        return not self.required


# =============================================================================
# Tenancy
# =============================================================================


class TenancyStrategy(StrEnum):
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

    model_config = ConfigDict(frozen=True)

    strategy: TenancyStrategy = Field(default=TenancyStrategy.NONE, description="Tenancy strategy")
    tenant_field: str | None = Field(
        default=None, description="Field name for tenant discriminator"
    )
    enforce: bool = Field(default=True, description="Enforce tenant isolation?")
    allow_cross_tenant: bool = Field(
        default=False, description="Allow cross-tenant access for superusers?"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @property
    def is_multi_tenant(self) -> bool:
        """Check if multi-tenancy is enabled."""
        return self.strategy != TenancyStrategy.NONE
