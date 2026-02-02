"""
Authentication and authorization specification types for BackendSpec.

Defines auth rules, tenancy, permissions, roles, and entity access rules.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


# =============================================================================
# Entity Access Rules (v0.7.0)
# =============================================================================


class AccessComparisonKind(str, Enum):
    """Comparison operators for access rule conditions."""

    EQUALS = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    IN = "in"
    NOT_IN = "not in"
    IS = "is"
    IS_NOT = "is not"


class AccessLogicalKind(str, Enum):
    """Logical operators for combining access conditions."""

    AND = "and"
    OR = "or"


class AccessAuthContext(str, Enum):
    """Authentication context for access rules."""

    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"


class AccessOperationKind(str, Enum):
    """Access operation types."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class AccessConditionSpec(BaseModel):
    """
    Access condition specification.

    Represents a node in the expression tree for access conditions.
    Can be:
    - comparison: field op value (e.g., owner_id = current_user)
    - role_check: role(role_name) (e.g., role(admin))
    - logical: left op right (combining conditions with AND/OR)

    Examples:
        - owner_id = current_user
        - role(admin)
        - owner_id = current_user or role(admin)
        - owner.team_id = current_team and status = active
    """

    kind: Literal["comparison", "role_check", "logical"] = Field(description="Condition type")
    # For comparison: field, operator, value
    field: str | None = Field(
        default=None,
        description="Field path for comparison (supports dotted paths like owner.team_id)",
    )
    comparison_op: AccessComparisonKind | None = Field(
        default=None, description="Comparison operator"
    )
    value: str | int | float | bool | None = Field(
        default=None, description="Comparison value (literal or special like 'current_user')"
    )
    value_list: list[str | int | float | bool] | None = Field(
        default=None, description="List of values for IN/NOT IN operators"
    )
    # For role_check: role name
    role_name: str | None = Field(default=None, description="Role name for role() check")
    # For logical: left, operator, right
    logical_op: AccessLogicalKind | None = Field(
        default=None, description="Logical operator (AND/OR)"
    )
    logical_left: "AccessConditionSpec | None" = Field(
        default=None, description="Left operand for logical"
    )
    logical_right: "AccessConditionSpec | None" = Field(
        default=None, description="Right operand for logical"
    )

    model_config = ConfigDict(frozen=True)


class VisibilityRuleSpec(BaseModel):
    """
    Visibility rule for entity read access.

    Defines when users can see/read entities.

    Examples:
        - Anonymous users can see if is_public = true
        - Authenticated users can see if owner_id = current_user
    """

    context: AccessAuthContext = Field(description="Auth context (anonymous/authenticated)")
    condition: AccessConditionSpec = Field(description="Condition for visibility")

    model_config = ConfigDict(frozen=True)


class PermissionRuleSpec(BaseModel):
    """
    Permission rule for entity write access.

    Defines when users can create/update/delete entities.

    Examples:
        - Only owner can update: owner_id = current_user
        - Only admin can delete: role(admin)
    """

    operation: AccessOperationKind = Field(description="Operation type (create/update/delete)")
    require_auth: bool = Field(default=True, description="Require authentication")
    condition: AccessConditionSpec | None = Field(
        default=None,
        description="Condition for permission (None = always allowed if authenticated)",
    )

    model_config = ConfigDict(frozen=True)


class EntityAccessSpec(BaseModel):
    """
    Entity-level access control specification.

    Combines visibility rules (read access) and permission rules (write access).

    Example:
        EntityAccessSpec(
            visibility=[
                VisibilityRuleSpec(
                    context=AccessAuthContext.AUTHENTICATED,
                    condition=AccessConditionSpec(
                        kind="comparison",
                        field="owner_id",
                        comparison_op=AccessComparisonKind.EQUALS,
                        value="current_user"
                    )
                )
            ],
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    condition=AccessConditionSpec(...)
                )
            ]
        )
    """

    visibility: list[VisibilityRuleSpec] = Field(
        default_factory=list, description="Visibility rules (read access)"
    )
    permissions: list[PermissionRuleSpec] = Field(
        default_factory=list, description="Permission rules (create/update/delete access)"
    )

    model_config = ConfigDict(frozen=True)


# Rebuild model for recursive types
AccessConditionSpec.model_rebuild()
