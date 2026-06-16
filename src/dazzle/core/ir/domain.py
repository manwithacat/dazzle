"""
Domain model types for DAZZLE IR.

This module contains entity definitions, constraints, access control,
and the domain specification.
"""

from __future__ import annotations  # required: forward reference

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .archetype import ArchetypeKind
from .computed import ComputedFieldSpec
from .conditions import ConditionExpr
from .eventing import PublishSpec
from .fields import FieldModifier, FieldSpec
from .fitness_repr import FitnessSpec
from .invariant import InvariantSpec
from .lifecycle import LifecycleSpec
from .location import SourceLocation
from .seed import SeedTemplateSpec
from .state_machine import StateMachineSpec


class ConstraintKind(StrEnum):
    """Types of constraints that can be applied to entities."""

    UNIQUE = "unique"
    INDEX = "index"


class ManagedBy(StrEnum):
    """How an entity's lifecycle is driven (#1333).

    Marks an entity as intentionally reachable only through a mechanism
    outside the workspace/surface navigation graph — a custom route, a
    pipeline/job, a multi-step wizard, or an external system. The marker's
    sole effect is to exempt the entity (and its CRUD surfaces) from the
    dead-construct lint. It is deliberately orthogonal to ``domain``: unlike
    ``domain: platform`` it does NOT reclassify the entity's business domain,
    mark it framework-injected, or skip modeling/fitness rules.
    """

    ROUTE = "route"
    PIPELINE = "pipeline"
    WIZARD = "wizard"
    EXTERNAL = "external"


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
    # #1281: when set, this rule explicitly denies the operation for all
    # callers. Lets append-only entities express `permit: update: false`
    # / `permit: delete: false` as a first-class declaration rather than
    # relying on the soft-deny `role(nobody)` workaround. The runtime
    # already default-denies any operation with no PERMIT rule, but the
    # explicit flag distinguishes "intentionally forbidden" from
    # "accidentally omitted" for the validator + audit matrix.
    deny_all: bool = False

    model_config = ConfigDict(frozen=True)


class ScopeRule(BaseModel):
    """Row-filtering scope rule with persona binding.

    Defines which records a role can see after passing the permit gate.
    condition=None means 'all' (no filter). personas=["*"] means all
    authorized roles.

    The ``predicate`` field is populated by the linker at link time.
    It is typed as ``Any`` to avoid circular imports between domain.py and
    predicates.py (ScopePredicate is a Pydantic discriminated union that
    causes Pydantic rebuild issues when imported into domain.py at module load).
    """

    operation: PermissionKind
    condition: ConditionExpr | None = None
    personas: list[str] = Field(default_factory=list)
    predicate: Any = None  # ScopePredicate, compiled at link time


class AccessSpec(BaseModel):
    """
    Access control specification for an entity.

    Defines row-level visibility and operation permissions.

    Attributes:
        visibility: List of visibility rules by auth context
        permissions: List of permission rules by operation
        scopes: List of row-filtering scope rules by operation and persona
    """

    visibility: list[VisibilityRule] = Field(default_factory=list)
    permissions: list[PermissionRule] = Field(default_factory=list)
    scopes: list[ScopeRule] = Field(default_factory=list)

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


class GraphEdgeSpec(BaseModel):
    """Formal graph edge declaration on an entity.

    Declares that this entity represents edges in a property graph.
    source and target must name ref fields on the same entity.
    """

    source: str
    target: str
    type_field: str | None = None
    weight_field: str | None = None
    directed: bool = True
    acyclic: bool = False

    model_config = ConfigDict(frozen=True)


class GraphNodeSpec(BaseModel):
    """Optional graph node annotation on an entity.

    Declares that this entity represents nodes connected by a specific
    edge entity.

    ``parent_field`` (optional) names a ref field on the node entity that
    points to an owning parent entity (e.g. a ``work_id`` FK on ``Node``
    linking to ``Work``). When set, the runtime generates a
    ``GET /api/{parent_plural}/{id}/graph`` endpoint that returns every
    node sharing that parent plus the edges connecting them (#781).
    """

    edge_entity: str
    display: str | None = None
    parent_field: str | None = None

    model_config = ConfigDict(frozen=True)


class TemporalSpec(BaseModel):
    """Effective-dated entity declaration (#1223 / #1217 Pattern 7).

    Marks an entity as carrying open / closed temporal intervals — each
    row spans ``start_field`` to ``end_field``. NULL ``end_field`` is
    the convention for "currently active." The framework uses this spec
    to compose tombstone filters on read paths, enforce "at most one
    active row per ``key_field``" at the DB layer, and re-project
    queries via ``?as_of=YYYY-MM-DD`` URL params.

    **Status at v0.71.161 (Phase 3a.i):** parsed into IR; runtime
    consumers land in subsequent slices (3a.ii through 3a.v). DSL
    authoring works today — declaring ``temporal:`` on an entity has
    no runtime effect until the next ship cycles wire the consumers.

    Attributes:
        start_field: Name of the field carrying the interval start. Must
            be a ``date`` or ``datetime`` field declared on the entity.
        end_field: Name of the field carrying the interval end. Must be
            an *optional* ``date`` or ``datetime`` field declared on the
            entity (NULL = currently active).
        key_field: Name of the field that identifies the *thing* being
            tracked over time (e.g. ``person`` on an Employment entity).
            The "at most one active row per key" constraint groups by
            this field.
        default_filter: Either ``active`` (auto-filter list/read paths
            to rows where end_field IS NULL) or ``none`` (no
            auto-filter). Default ``active``.
        as_of_param: URL query-string parameter name that re-projects
            the temporal filter to an arbitrary date. Default ``as_of``.
    """

    start_field: str
    end_field: str
    key_field: str
    default_filter: str = "active"
    as_of_param: str = "as_of"

    model_config = ConfigDict(frozen=True)


class TenantHostSpec(BaseModel):
    """Host-header tenant routing configuration for an entity (#1289).

    Auto-mounts the framework's TenantResolutionMiddleware when any entity
    declares this block. See docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md
    """

    model_config = ConfigDict(frozen=True)

    domain: str
    slug_field: str
    canonical_hosts: list[str] = Field(default_factory=list)
    cookie_scope: Literal["host", "apex"] = "host"
    super_admin_role: str = "super_admin"
    history_entity: str | None = None
    not_found_template: str | None = None
    expired_template: str | None = None
    order: int | None = None
    # ADR-0036 (#1394 Layer 2): tenant-hierarchy parent edge. Names a `ref` field
    # on THIS entity whose target is another `tenant_host` entity (the parent
    # kind). The linker derives the kind partial-order from these edges; the
    # `current_tenant` compiler uses it to select aggregate-vs-single (a parent
    # host aggregates over descendants via the FK path; a leaf host is single).
    # `None` = a root / flat tenant kind. Validated against the FK graph + the
    # RLS partition root at link time (ADR-0036 D2/D4).
    parent: str | None = None


class MembershipSpec(BaseModel):
    """Declarative user→tenant membership relation (ADR-0037, #1393 Phase C).

    Declared with a `membership:` block on the **tenant-root kind** (the entity
    that is simultaneously the RLS partition root and the ADR-0036 hierarchy
    root). It makes the previously-inferred tenant-root match explicit and
    link-validated: "this kind is the membership/RLS/hierarchy root, and its
    members are framework `User` identities with these roles."

    The principal is always the framework `User` in v1 (ADR-0037 acceptance
    decision — `identity:` deliberately omitted). Descendant-host reachability is
    DERIVED from one root membership via the `parent:` edges (no per-leaf rows).
    The framework `memberships` store remains the runtime model; this block is a
    validated binding, not a new table.
    """

    model_config = ConfigDict(frozen=True)

    # The per-tenant role/persona source field on the membership (the personas an
    # identity holds *in this tenant*). `None` = the framework membership `roles`.
    roles: str | None = None


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
        temporal: Effective-dated / temporal entity specification (v0.71.161, #1223 Phase 3a.i)
        subtype_of: Name of base entity this is a subtype of (v0.71.180, #1217 Phase 3e.i)
        subtype_children: Back-pointer to subtypes (linker-populated; empty in raw parser output)
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
    is_profile: bool = False  # auth Plan 3c — archetype: profile (per-member data)
    fields: list[FieldSpec]
    computed_fields: list[ComputedFieldSpec] = Field(default_factory=list)
    invariants: list[InvariantSpec] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    access: AccessSpec | None = None
    audit: AuditConfig | None = None
    # v0.34.0: Soft delete — archive instead of hard delete
    soft_delete: bool = False
    # v0.71.161 (#1223 Phase 3a.i): effective-dated / temporal entity
    # declaration. When set, the framework will (in subsequent slices)
    # auto-filter read paths to currently-active rows and thread
    # `?as_of=` URL params through workspace renders.
    temporal: TemporalSpec | None = None
    # v0.71.180 (#1217 Phase 3e.i): subtype polymorphism (table-per-type).
    # When set on a child entity, declares an IS-A relationship to the named
    # base. Linker populates `subtype_children` on the base (back-pointer)
    # and synthesises a `kind` enum field. See ADR-0026.
    subtype_of: str | None = None
    subtype_children: tuple[str, ...] = ()
    # v0.79.7 (#1283 phase 3): native document signing primitive. When True,
    # the linker auto-injects 11 fields (status enum, signing_url,
    # signed_document, token_hash, signer_ip/user_agent, 4× timestamps)
    # and defaults `audit` to AuditConfig(enabled=True). The runtime
    # signing routes (phase 3d) and the dazzle.signing backend
    # (shipped v0.79.7 phase 2) read from these fields.
    signable: bool = False
    # Optional dotted-path callable invoked before signing — raises
    # SigningError(...) to block. Used for grant checks ("signatory must
    # hold approve_letter grant") or domain logic that can't be expressed
    # in DSL scope rules.
    signing_validator: str | None = None
    # v0.79.12 (#1283 phase 6a): optional dotted-path callable that
    # produces the document body HTML. Signature: ``(entity, row) ->
    # str``. The framework imports + invokes it before generating the
    # PDF. When unset, a stub "entity name + id" placeholder is used.
    # Resolution is constrained to the same regex as signing_validator
    # so a build-time DSL declaration is the only way in.
    signing_template: str | None = None
    # v0.34.0: Bulk import/export
    bulk: BulkConfig | None = None
    state_machine: StateMachineSpec | None = None
    # ADR-0020: Lifecycle evidence predicates (orthogonal to state_machine)
    lifecycle: LifecycleSpec | None = None
    # Agent-Led Fitness v1: per-entity repr_fields projection for diff tracking
    fitness: FitnessSpec | None = None
    examples: list[ExampleRecord] = Field(default_factory=list)
    # v0.18.0: Event publishing
    publishes: list[PublishSpec] = Field(default_factory=list)
    # v0.38.0: Declarative seed template for reference data
    seed_template: SeedTemplateSpec | None = None
    # v0.44.0: Explicit display field for FK references
    display_field: str | None = None
    # v0.46.0: Graph semantics (#619)
    graph_edge: GraphEdgeSpec | None = None
    graph_node: GraphNodeSpec | None = None
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None
    # v0.80.7 (#1289): host-header tenant routing configuration
    tenant_host: TenantHostSpec | None = None
    # ADR-0037 (#1393 Phase C): declarative membership relation; set only on the
    # tenant-root kind (link-validated). None = no declared membership here.
    membership: MembershipSpec | None = None
    # #1333: lifecycle-ownership marker. When set, the entity is reachable
    # only via a mechanism outside the nav graph (route/pipeline/wizard/
    # external), so the dead-construct lint exempts it and its surfaces.
    # Orthogonal to `domain` — does NOT reclassify the business domain.
    managed_by: ManagedBy | None = None

    model_config = ConfigDict(frozen=True)

    @property
    def primary_key(self) -> FieldSpec | None:
        """Get the primary key field, if any."""
        for field in self.fields:
            if field.is_primary_key:
                return field
        return None

    @property
    def is_polymorphic_base(self) -> bool:
        """True when one or more entities declare `subtype_of: <this>`."""
        return len(self.subtype_children) > 0

    @property
    def is_polymorphic_child(self) -> bool:
        """True when this entity declares `subtype_of: <some base>`."""
        return self.subtype_of is not None

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
