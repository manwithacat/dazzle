"""
Domain model types for DAZZLE IR.

This module contains entity definitions, constraints, access control,
and the domain specification.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionExpr
from .fields import FieldSpec


class ConstraintKind(str, Enum):
    """Types of constraints that can be applied to entities."""

    UNIQUE = "unique"
    INDEX = "index"


class Constraint(BaseModel):
    """
    Entity-level constraint (unique or index).

    Attributes:
        kind: Type of constraint
        fields: List of field names involved in constraint
    """

    kind: ConstraintKind
    fields: list[str]

    model_config = ConfigDict(frozen=True)


class AuthContext(str, Enum):
    """Authentication context for access control rules."""

    ANONYMOUS = "anonymous"  # Not logged in
    AUTHENTICATED = "authenticated"  # Any logged-in user


class VisibilityRule(BaseModel):
    """
    Row-level visibility rule for a specific auth context.

    Defines which records are visible based on authentication state.

    Examples:
        - when anonymous: is_public = true
        - when authenticated: is_public = true or created_by = current_user
    """

    context: AuthContext
    condition: ConditionExpr

    model_config = ConfigDict(frozen=True)


class PermissionKind(str, Enum):
    """Types of operations that can have permission rules."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class PermissionRule(BaseModel):
    """
    Permission rule for a specific operation.

    Defines who can perform create/update/delete operations.

    Examples:
        - create: authenticated
        - update: created_by = current_user or assigned_to = current_user
        - delete: created_by = current_user
    """

    operation: PermissionKind
    require_auth: bool = True  # If True, must be authenticated
    condition: ConditionExpr | None = None  # Additional row-level check

    model_config = ConfigDict(frozen=True)


class AccessSpec(BaseModel):
    """
    Access control specification for an entity.

    Defines row-level visibility and operation permissions.

    Attributes:
        visibility: List of visibility rules by auth context
        permissions: List of permission rules by operation
    """

    visibility: list[VisibilityRule] = Field(default_factory=list)
    permissions: list[PermissionRule] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    def get_visibility_for(self, context: AuthContext) -> ConditionExpr | None:
        """Get visibility condition for a specific auth context."""
        for rule in self.visibility:
            if rule.context == context:
                return rule.condition
        return None

    def get_permission_for(self, operation: PermissionKind) -> PermissionRule | None:
        """Get permission rule for a specific operation."""
        for rule in self.permissions:
            if rule.operation == operation:
                return rule
        return None


class EntitySpec(BaseModel):
    """
    Specification for a domain entity.

    Entities represent internal data models that map to tables/aggregates/resources.

    Attributes:
        name: Entity name (PascalCase)
        title: Human-readable title
        fields: List of field specifications
        constraints: Entity-level constraints (unique, index)
        access: Access control specification (visibility + permissions)
    """

    name: str
    title: str | None = None
    fields: list[FieldSpec]
    constraints: list[Constraint] = Field(default_factory=list)
    access: AccessSpec | None = None

    model_config = ConfigDict(frozen=True)

    @property
    def primary_key(self) -> FieldSpec | None:
        """Get the primary key field, if any."""
        for field in self.fields:
            if field.is_primary_key:
                return field
        return None

    def get_field(self, name: str) -> FieldSpec | None:
        """Get field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None


class DomainSpec(BaseModel):
    """
    The domain model containing all entities.

    Attributes:
        entities: List of entity specifications
    """

    entities: list[EntitySpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    def get_entity(self, name: str) -> EntitySpec | None:
        """Get entity by name."""
        for entity in self.entities:
            if entity.name == name:
                return entity
        return None
