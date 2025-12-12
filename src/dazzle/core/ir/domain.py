"""
Domain model types for DAZZLE IR.

This module contains entity definitions, constraints, access control,
and the domain specification.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .archetype import ArchetypeKind
from .computed import ComputedFieldSpec
from .conditions import ConditionExpr
from .fields import FieldSpec
from .invariant import InvariantSpec
from .state_machine import StateMachineSpec


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


class ExampleRecord(BaseModel):
    """
    Example data record for an entity.

    Used for LLM cognition - concrete examples help LLMs understand
    the intended data format and valid values.

    v0.7.1: Added for LLM cognition
    """

    values: dict[str, str | int | float | bool | None] = Field(
        description="Field name to value mapping"
    )

    model_config = ConfigDict(frozen=True)


class EntitySpec(BaseModel):
    """
    Specification for a domain entity.

    Entities represent internal data models that map to tables/aggregates/resources.

    Attributes:
        name: Entity name (PascalCase)
        title: Human-readable title
        intent: Purpose statement for LLM cognition (v0.7.1)
        domain: Domain classification tag (v0.7.1)
        patterns: Pattern tags for auto-generation hints (v0.7.1)
        extends: Archetype names this entity inherits from (v0.7.1)
        archetype_kind: Semantic archetype (settings, tenant, etc.) (v0.10.3)
        is_singleton: Whether entity has exactly one record (v0.10.3)
        is_tenant_root: Whether entity is the tenant root for multi-tenancy (v0.10.3)
        fields: List of field specifications
        computed_fields: List of computed (derived) field specifications
        invariants: List of entity invariants (cross-field constraints)
        constraints: Entity-level constraints (unique, index)
        access: Access control specification (visibility + permissions)
        state_machine: State machine specification for status transitions (v0.7.0)
        examples: Example data records for LLM cognition (v0.7.1)
    """

    name: str
    title: str | None = None
    intent: str | None = None
    domain: str | None = None
    patterns: list[str] = Field(default_factory=list)
    extends: list[str] = Field(default_factory=list)
    # v0.10.3: Semantic archetype support
    archetype_kind: ArchetypeKind | None = None
    is_singleton: bool = False
    is_tenant_root: bool = False
    fields: list[FieldSpec]
    computed_fields: list[ComputedFieldSpec] = Field(default_factory=list)
    invariants: list[InvariantSpec] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    access: AccessSpec | None = None
    state_machine: StateMachineSpec | None = None
    examples: list[ExampleRecord] = Field(default_factory=list)

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

    def get_computed_field(self, name: str) -> ComputedFieldSpec | None:
        """Get computed field by name."""
        for field in self.computed_fields:
            if field.name == name:
                return field
        return None

    @property
    def has_state_machine(self) -> bool:
        """Check if this entity has a state machine."""
        return self.state_machine is not None

    @property
    def has_computed_fields(self) -> bool:
        """Check if this entity has computed fields."""
        return len(self.computed_fields) > 0


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
