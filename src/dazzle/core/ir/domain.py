"""
Domain model types for DAZZLE IR.

This module contains entity definitions, constraints, access control,
and the domain specification.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .archetype import ArchetypeKind
from .computed import ComputedFieldSpec
from .conditions import ConditionExpr
from .eventing import PublishSpec
from .fields import FieldModifier, FieldSpec
from .invariant import InvariantSpec
from .location import SourceLocation
from .state_machine import StateMachineSpec


class ConstraintKind(StrEnum):
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


class AuthContext(StrEnum):
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


class PolicyEffect(StrEnum):
    """Effect of a policy rule (Cedar-inspired)."""

    PERMIT = "permit"
    FORBID = "forbid"


class PermissionKind(StrEnum):
    """Types of operations that can have permission rules."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"


class PermissionRule(BaseModel):
    """
    Permission rule for a specific operation.

    Defines who can perform CRUD operations with Cedar-style permit/forbid semantics.

    Examples:
        - create: authenticated
        - update: created_by = current_user or assigned_to = current_user
        - delete: created_by = current_user

    Cedar semantics:
        - effect=PERMIT: Grants access if condition matches
        - effect=FORBID: Denies access if condition matches (overrides permits)
        - Default (no matching rule): Deny
    """

    operation: PermissionKind
    require_auth: bool = True  # If True, must be authenticated
    condition: ConditionExpr | None = None  # Additional row-level check
    effect: PolicyEffect = PolicyEffect.PERMIT  # Cedar-style effect
    personas: list[str] = Field(default_factory=list)  # Persona scope (empty = any)

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


class AuditConfig(BaseModel):
    """
    Audit logging configuration for an entity.

    Controls which operations are logged to the audit trail.

    Attributes:
        enabled: Whether audit logging is enabled
        operations: Operations to audit (empty = all operations)
        include_field_changes: Whether to capture old/new field values (v0.34.0)
    """

    enabled: bool = False
    operations: list[PermissionKind] = Field(default_factory=list)
    include_field_changes: bool = True  # v0.34.0: field-level diffs by default

    model_config = ConfigDict(frozen=True)


class BulkFormat(StrEnum):
    """Supported formats for bulk import/export (v0.34.0)."""

    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"


class BulkConfig(BaseModel):
    """
    Bulk import/export configuration for an entity (v0.34.0).

    Attributes:
        import_enabled: Whether bulk import is enabled
        export_enabled: Whether bulk export is enabled
        formats: Supported file formats
        import_fields: Fields to include in import (empty = all writable fields)
        export_fields: Fields to include in export (empty = all non-sensitive fields)
    """

    import_enabled: bool = True
    export_enabled: bool = True
    formats: list[BulkFormat] = Field(default_factory=lambda: [BulkFormat.CSV])
    import_fields: list[str] = Field(default_factory=list)
    export_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


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
        publishes: Event publishing declarations (v0.18.0)
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
    audit: AuditConfig | None = None
    # v0.34.0: Soft delete — archive instead of hard delete
    soft_delete: bool = False
    # v0.34.0: Bulk import/export
    bulk: BulkConfig | None = None
    state_machine: StateMachineSpec | None = None
    examples: list[ExampleRecord] = Field(default_factory=list)
    # v0.18.0: Event publishing
    publishes: list[PublishSpec] = Field(default_factory=list)
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None

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

    @property
    def searchable_fields(self) -> list[FieldSpec]:
        """Get fields marked as searchable (v0.34.0)."""
        return [f for f in self.fields if FieldModifier.SEARCHABLE in f.modifiers]


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
