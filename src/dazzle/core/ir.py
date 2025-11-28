"""
DAZZLE Internal Representation (IR) types.

This module defines the complete type system for the DAZZLE IR using Pydantic.
The IR is the source of truth for all code generation and validation.

All types are immutable by default (frozen=True) to ensure the IR remains
a pure data structure that can be safely shared and analyzed.
"""

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Core Field Types
# =============================================================================


class FieldTypeKind(str, Enum):
    """Enumeration of supported field types in DAZZLE."""

    STR = "str"
    TEXT = "text"
    INT = "int"
    DECIMAL = "decimal"
    BOOL = "bool"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    ENUM = "enum"
    REF = "ref"
    EMAIL = "email"


class FieldType(BaseModel):
    """
    Represents a field type specification.

    Examples:
        - str(200): FieldType(kind=STR, max_length=200)
        - decimal(10,2): FieldType(kind=DECIMAL, precision=10, scale=2)
        - enum[draft,issued]: FieldType(kind=ENUM, enum_values=["draft", "issued"])
        - ref Client: FieldType(kind=REF, ref_entity="Client")
    """

    kind: FieldTypeKind
    max_length: int | None = None  # for str
    precision: int | None = None  # for decimal
    scale: int | None = None  # for decimal
    enum_values: list[str] | None = None  # for enum
    ref_entity: str | None = None  # for ref

    class Config:
        frozen = True

    @field_validator("enum_values")
    @classmethod
    def validate_enum_values(cls, v: list[str] | None) -> list[str] | None:
        """Ensure enum values are valid identifiers."""
        if v:
            for val in v:
                if not val.isidentifier():
                    raise ValueError(f"Enum value '{val}' is not a valid identifier")
        return v


class FieldModifier(str, Enum):
    """Modifiers that can be applied to fields."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    PK = "pk"
    UNIQUE = "unique"
    UNIQUE_NULLABLE = "unique?"
    AUTO_ADD = "auto_add"
    AUTO_UPDATE = "auto_update"


class FieldSpec(BaseModel):
    """
    Specification for a single field in an entity or foreign model.

    Attributes:
        name: Field identifier
        type: Field type specification
        modifiers: List of modifiers (required, pk, unique, etc.)
        default: Optional default value
    """

    name: str
    type: FieldType
    modifiers: list[FieldModifier] = Field(default_factory=list)
    default: str | int | float | bool | None = None

    class Config:
        frozen = True

    @property
    def is_required(self) -> bool:
        """Check if field is required."""
        return FieldModifier.REQUIRED in self.modifiers

    @property
    def is_primary_key(self) -> bool:
        """Check if field is primary key."""
        return FieldModifier.PK in self.modifiers

    @property
    def is_unique(self) -> bool:
        """Check if field has unique constraint."""
        return (
            FieldModifier.UNIQUE in self.modifiers
            or FieldModifier.UNIQUE_NULLABLE in self.modifiers
        )


# =============================================================================
# Domain - Entities
# =============================================================================


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

    class Config:
        frozen = True


class EntitySpec(BaseModel):
    """
    Specification for a domain entity.

    Entities represent internal data models that map to tables/aggregates/resources.

    Attributes:
        name: Entity name (PascalCase)
        title: Human-readable title
        fields: List of field specifications
        constraints: Entity-level constraints (unique, index)
    """

    name: str
    title: str | None = None
    fields: list[FieldSpec]
    constraints: list[Constraint] = Field(default_factory=list)

    class Config:
        frozen = True

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

    class Config:
        frozen = True

    def get_entity(self, name: str) -> EntitySpec | None:
        """Get entity by name."""
        for entity in self.entities:
            if entity.name == name:
                return entity
        return None


# =============================================================================
# Surfaces - UI Entry Points
# =============================================================================


class SurfaceMode(str, Enum):
    """Modes that define surface behavior."""

    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    LIST = "list"
    CUSTOM = "custom"


class SurfaceTrigger(str, Enum):
    """Triggers for surface actions."""

    SUBMIT = "submit"
    CLICK = "click"
    AUTO = "auto"


class OutcomeKind(str, Enum):
    """Types of outcomes for surface actions."""

    SURFACE = "surface"
    EXPERIENCE = "experience"
    INTEGRATION = "integration"


class Outcome(BaseModel):
    """
    Action outcome specification.

    Defines what happens when a surface action is triggered.
    """

    kind: OutcomeKind
    target: str  # surface name, experience name, or integration name
    step: str | None = None  # for experience outcomes
    action: str | None = None  # for integration outcomes

    class Config:
        frozen = True


class SurfaceElement(BaseModel):
    """
    Element within a surface section (typically a field).

    Attributes:
        field_name: Name of the field from the entity
        label: Human-readable label
        options: Additional options for rendering
    """

    field_name: str
    label: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = True


class SurfaceSection(BaseModel):
    """
    Section within a surface containing related elements.

    Attributes:
        name: Section identifier
        title: Human-readable title
        elements: List of elements in this section
    """

    name: str
    title: str | None = None
    elements: list[SurfaceElement] = Field(default_factory=list)

    class Config:
        frozen = True


class SurfaceAction(BaseModel):
    """
    Action that can be triggered from a surface.

    Attributes:
        name: Action identifier
        label: Human-readable label
        trigger: When the action is triggered
        outcome: What happens when action fires
    """

    name: str
    label: str | None = None
    trigger: SurfaceTrigger
    outcome: Outcome

    class Config:
        frozen = True


# =============================================================================
# UX Semantic Layer - Attention Signals, Personas, and Display Controls
# =============================================================================


class SignalLevel(str, Enum):
    """Levels for attention signals indicating urgency."""

    CRITICAL = "critical"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"


class ComparisonOperator(str, Enum):
    """Operators for condition expressions."""

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


class LogicalOperator(str, Enum):
    """Logical operators for combining conditions."""

    AND = "and"
    OR = "or"


class ConditionValue(BaseModel):
    """
    A value in a condition expression.

    Can be a literal (string, number, boolean, null) or a list of values.
    """

    literal: str | int | float | bool | None = None
    values: list[str | int | float | bool] | None = None  # For 'in' operator

    class Config:
        frozen = True

    @property
    def is_list(self) -> bool:
        """Check if this is a list value."""
        return self.values is not None


class FunctionCall(BaseModel):
    """
    A function call in a condition expression.

    Examples:
        - days_since(last_inspection_date)
        - count(observations)
    """

    name: str
    argument: str  # Field name

    class Config:
        frozen = True


class Comparison(BaseModel):
    """
    A single comparison in a condition expression.

    Examples:
        - condition_status in [SevereStress, Dead]
        - days_since(last_inspection_date) > 30
        - steward is null
    """

    field: str | None = None  # Direct field reference
    function: FunctionCall | None = None  # Function call
    operator: ComparisonOperator
    value: ConditionValue

    class Config:
        frozen = True

    @property
    def left_operand(self) -> str:
        """Get the left side of the comparison as a string."""
        if self.function:
            return f"{self.function.name}({self.function.argument})"
        return self.field or ""


class ConditionExpr(BaseModel):
    """
    A condition expression that can be simple or compound.

    Examples:
        - condition_status in [SevereStress, Dead]
        - days_since(last_inspection_date) > 30 and steward is null
    """

    comparison: Comparison | None = None  # Simple condition
    left: "ConditionExpr | None" = None  # For compound conditions
    operator: LogicalOperator | None = None  # AND/OR
    right: "ConditionExpr | None" = None  # For compound conditions

    class Config:
        frozen = True

    @property
    def is_compound(self) -> bool:
        """Check if this is a compound (AND/OR) condition."""
        return self.operator is not None


class AttentionSignal(BaseModel):
    """
    Data-driven attention signal for prioritization.

    Defines conditions that should draw user attention and optional actions.

    Attributes:
        level: Severity level (critical, warning, notice, info)
        condition: Condition expression that triggers this signal
        message: Human-readable message to display
        action: Optional surface reference for quick action
    """

    level: SignalLevel
    condition: ConditionExpr
    message: str
    action: str | None = None  # Surface reference

    class Config:
        frozen = True

    @property
    def css_class(self) -> str:
        """Map signal level to CSS class name."""
        return {
            SignalLevel.CRITICAL: "danger",
            SignalLevel.WARNING: "warning",
            SignalLevel.NOTICE: "info",
            SignalLevel.INFO: "secondary",
        }[self.level]


class PersonaVariant(BaseModel):
    """
    Role-specific surface adaptation.

    Defines how a surface should be customized for different user personas.

    Attributes:
        persona: Persona identifier (e.g., "volunteer", "coordinator")
        scope: Filter expression limiting data visibility, or "all"
        purpose: Persona-specific purpose description
        show: Fields to explicitly show (overrides base)
        hide: Fields to hide from base
        show_aggregate: Aggregate metrics to display (e.g., critical_count)
        action_primary: Primary action surface for this persona
        read_only: Whether mutations are disabled
        defaults: Default field values for forms (e.g., {"assigned_to": "current_user"})
        focus: Workspace regions to emphasize for this persona
    """

    persona: str
    scope: ConditionExpr | None = None  # None means "all"
    scope_all: bool = False  # True if "scope: all" was specified
    purpose: str | None = None
    show: list[str] = Field(default_factory=list)
    hide: list[str] = Field(default_factory=list)
    show_aggregate: list[str] = Field(default_factory=list)
    action_primary: str | None = None  # Surface reference
    read_only: bool = False
    defaults: dict[str, Any] = Field(default_factory=dict)  # Field default values
    focus: list[str] = Field(default_factory=list)  # Workspace regions to emphasize

    class Config:
        frozen = True

    def applies_to_user(self, user_context: dict[str, Any]) -> bool:
        """Check if persona applies to given user context."""
        return user_context.get("persona") == self.persona


class SortSpec(BaseModel):
    """
    Sort specification for a field.

    Attributes:
        field: Field name to sort by
        direction: Sort direction (asc or desc)
    """

    field: str
    direction: str = "asc"  # "asc" or "desc"

    class Config:
        frozen = True

    def __str__(self) -> str:
        return f"{self.field} {self.direction}"


class UXSpec(BaseModel):
    """
    Complete UX specification for a surface.

    Captures semantic intent about how users interact with data.

    Attributes:
        purpose: Why this surface exists
        show: Fields to display (overrides section fields if present)
        sort: Default sort order
        filter: Fields available for filtering
        search: Fields available for full-text search
        empty_message: Message shown when no data
        attention_signals: Data-driven priority indicators
        persona_variants: Role-specific adaptations
    """

    purpose: str | None = None
    show: list[str] = Field(default_factory=list)
    sort: list[SortSpec] = Field(default_factory=list)
    filter: list[str] = Field(default_factory=list)
    search: list[str] = Field(default_factory=list)
    empty_message: str | None = None
    attention_signals: list[AttentionSignal] = Field(default_factory=list)
    persona_variants: list[PersonaVariant] = Field(default_factory=list)

    class Config:
        frozen = True

    def get_persona_variant(self, user_context: dict[str, Any]) -> PersonaVariant | None:
        """Get applicable persona variant for user context."""
        for variant in self.persona_variants:
            if variant.applies_to_user(user_context):
                return variant
        return None

    @property
    def has_attention_signals(self) -> bool:
        """Check if any attention signals are defined."""
        return len(self.attention_signals) > 0


class SurfaceSpec(BaseModel):
    """
    Specification for a user-facing surface (screen/form/view).

    Surfaces describe UI entry points and interactions.

    Attributes:
        name: Surface identifier
        title: Human-readable title
        entity_ref: Optional reference to an entity
        mode: Surface mode (view, create, edit, list, custom)
        sections: List of sections containing elements
        actions: List of actions available on this surface
        ux: Optional UX semantic layer specification
    """

    name: str
    title: str | None = None
    entity_ref: str | None = None
    mode: SurfaceMode
    sections: list[SurfaceSection] = Field(default_factory=list)
    actions: list[SurfaceAction] = Field(default_factory=list)
    ux: UXSpec | None = None  # UX Semantic Layer extension

    class Config:
        frozen = True


# =============================================================================
# Workspaces - Composition of Related Information Needs
# =============================================================================


class DisplayMode(str, Enum):
    """Display modes for workspace regions."""

    LIST = "list"
    GRID = "grid"
    TIMELINE = "timeline"
    MAP = "map"
    DETAIL = "detail"  # v0.3.1: Single item detail view


class WorkspaceRegion(BaseModel):
    """
    Named region within a workspace.

    A region displays data from a source entity or surface with optional
    filtering, sorting, and display customization.

    Attributes:
        name: Region identifier
        source: Entity or surface name to source data from
        filter: Optional filter expression
        sort: Optional sort specification
        limit: Maximum records to display
        display: Display mode (list, grid, timeline, map)
        action: Surface for quick action on items
        empty_message: Message when no data
        group_by: Field to group data by for aggregation
        aggregates: Named aggregate expressions
    """

    name: str
    source: str  # Entity or surface name
    filter: ConditionExpr | None = None
    sort: list[SortSpec] = Field(default_factory=list)
    limit: int | None = Field(None, ge=1, le=1000)
    display: DisplayMode = DisplayMode.LIST
    action: str | None = None  # Surface reference
    empty_message: str | None = None
    group_by: str | None = None  # Field to group by
    aggregates: dict[str, str] = Field(default_factory=dict)  # metric_name: expr

    class Config:
        frozen = True


class WorkspaceSpec(BaseModel):
    """
    Composition of related information needs.

    A workspace brings together multiple data views into a cohesive
    user experience, typically representing a role-specific dashboard.

    Attributes:
        name: Workspace identifier
        title: Human-readable title
        purpose: Why this workspace exists
        engine_hint: Optional layout archetype hint (e.g., "focus_metric", "scanner_table")
        regions: List of data regions in the workspace
        ux: Optional workspace-level UX customization
    """

    name: str
    title: str | None = None
    purpose: str | None = None
    engine_hint: str | None = None  # v0.3.1: Force specific archetype
    regions: list[WorkspaceRegion] = Field(default_factory=list)
    ux: UXSpec | None = None  # Workspace-level UX (e.g., persona variants)

    class Config:
        frozen = True

    def get_region(self, name: str) -> WorkspaceRegion | None:
        """Get region by name."""
        for region in self.regions:
            if region.name == name:
                return region
        return None


# =============================================================================
# Experiences - Orchestrated Flows
# =============================================================================


class StepKind(str, Enum):
    """Types of steps in an experience."""

    SURFACE = "surface"
    PROCESS = "process"
    INTEGRATION = "integration"


class TransitionEvent(str, Enum):
    """Events that trigger step transitions."""

    SUCCESS = "success"
    FAILURE = "failure"


class StepTransition(BaseModel):
    """
    Transition from one step to another.

    Attributes:
        event: Event that triggers transition
        next_step: Name of the next step
    """

    event: TransitionEvent
    next_step: str

    class Config:
        frozen = True


class ExperienceStep(BaseModel):
    """
    Single step in an experience flow.

    Attributes:
        name: Step identifier
        kind: Type of step
        surface: Surface name (if kind=surface)
        integration: Integration name (if kind=integration)
        action: Action name (if kind=integration)
        transitions: List of transitions to other steps
    """

    name: str
    kind: StepKind
    surface: str | None = None
    integration: str | None = None
    action: str | None = None
    transitions: list[StepTransition] = Field(default_factory=list)

    class Config:
        frozen = True


class ExperienceSpec(BaseModel):
    """
    Specification for an orchestrated experience (flow).

    Experiences define multi-step user journeys.

    Attributes:
        name: Experience identifier
        title: Human-readable title
        start_step: Name of the starting step
        steps: List of steps in this experience
    """

    name: str
    title: str | None = None
    start_step: str
    steps: list[ExperienceStep] = Field(default_factory=list)

    class Config:
        frozen = True

    def get_step(self, name: str) -> ExperienceStep | None:
        """Get step by name."""
        for step in self.steps:
            if step.name == name:
                return step
        return None


# =============================================================================
# Services - External Systems
# =============================================================================


class AuthKind(str, Enum):
    """Authentication profile types."""

    OAUTH2_LEGACY = "oauth2_legacy"
    OAUTH2_PKCE = "oauth2_pkce"
    JWT_STATIC = "jwt_static"
    API_KEY_HEADER = "api_key_header"
    API_KEY_QUERY = "api_key_query"
    NONE = "none"


class AuthProfile(BaseModel):
    """
    Authentication profile for a service.

    Attributes:
        kind: Type of authentication
        options: Additional auth options (scopes, etc.)
    """

    kind: AuthKind
    options: dict[str, str] = Field(default_factory=dict)

    class Config:
        frozen = True


class ServiceSpec(BaseModel):
    """
    Specification for an external service (API).

    Services represent third-party systems that the app integrates with.

    Attributes:
        name: Service identifier
        title: Human-readable title
        spec_url: URL to service spec (often OpenAPI)
        spec_inline: Inline spec identifier
        auth_profile: Authentication configuration
        owner: Service owner/provider
    """

    name: str
    title: str | None = None
    spec_url: str | None = None
    spec_inline: str | None = None
    auth_profile: AuthProfile
    owner: str | None = None

    class Config:
        frozen = True


# =============================================================================
# Foreign Models - External Data
# =============================================================================


class ForeignConstraintKind(str, Enum):
    """Constraint types for foreign models."""

    READ_ONLY = "read_only"
    EVENT_DRIVEN = "event_driven"
    BATCH_IMPORT = "batch_import"


class ForeignConstraint(BaseModel):
    """
    Constraint on a foreign model.

    Attributes:
        kind: Type of constraint
        options: Additional constraint options
    """

    kind: ForeignConstraintKind
    options: dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = True


class ForeignModelSpec(BaseModel):
    """
    Specification for a foreign (external) data model.

    Foreign models represent data owned by external services.

    Attributes:
        name: Foreign model name
        title: Human-readable title
        service_ref: Reference to service this model comes from
        key_fields: Fields that form the key
        constraints: List of constraints
        fields: List of field specifications
    """

    name: str
    title: str | None = None
    service_ref: str
    key_fields: list[str]
    constraints: list[ForeignConstraint] = Field(default_factory=list)
    fields: list[FieldSpec] = Field(default_factory=list)

    class Config:
        frozen = True

    def get_field(self, name: str) -> FieldSpec | None:
        """Get field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None


# =============================================================================
# Integrations - Connections Between Internal and External
# =============================================================================


class Expression(BaseModel):
    """
    Simple expression for mappings.

    Supports paths (form.vrn, entity.id) and literals.

    Attributes:
        path: Dotted path (e.g., "form.vrn", "entity.client_id")
        literal: Literal value (string, number, boolean)
    """

    path: str | None = None
    literal: str | int | float | bool | None = None

    class Config:
        frozen = True

    @field_validator("path", "literal")
    @classmethod
    def validate_one_set(
        cls, v: str | int | float | bool | None, info: Any
    ) -> str | int | float | bool | None:
        """Ensure exactly one of path or literal is set."""
        # This is simplified; full validation would check both fields
        return v


class MappingRule(BaseModel):
    """
    Mapping rule for integrations.

    Maps a target field to a source expression.

    Attributes:
        target_field: Field to map to
        source: Expression providing the value
    """

    target_field: str
    source: Expression

    class Config:
        frozen = True


class IntegrationAction(BaseModel):
    """
    Action within an integration (on-demand operation).

    Attributes:
        name: Action identifier
        when_surface: Surface that triggers this action
        call_service: Service to call
        call_operation: Operation name on service
        call_mapping: Mapping for call parameters
        response_foreign_model: Foreign model for response
        response_entity: Entity to map response to
        response_mapping: Mapping for response fields
    """

    name: str
    when_surface: str
    call_service: str
    call_operation: str
    call_mapping: list[MappingRule] = Field(default_factory=list)
    response_foreign_model: str | None = None
    response_entity: str | None = None
    response_mapping: list[MappingRule] = Field(default_factory=list)

    class Config:
        frozen = True


class SyncMode(str, Enum):
    """Sync modes for integration syncs."""

    SCHEDULED = "scheduled"
    EVENT_DRIVEN = "event_driven"


class MatchRule(BaseModel):
    """
    Match rule for syncs (bidirectional field mapping).

    Attributes:
        foreign_field: Field in foreign model
        entity_field: Field in entity
    """

    foreign_field: str
    entity_field: str

    class Config:
        frozen = True


class IntegrationSync(BaseModel):
    """
    Sync operation within an integration (scheduled or event-driven).

    Attributes:
        name: Sync identifier
        mode: Sync mode (scheduled or event_driven)
        schedule: Cron expression (if scheduled)
        from_service: Service to sync from
        from_operation: Operation to call
        from_foreign_model: Foreign model to use
        into_entity: Entity to sync into
        match_rules: Rules for matching foreign records to entities
    """

    name: str
    mode: SyncMode
    schedule: str | None = None  # cron expression
    from_service: str
    from_operation: str
    from_foreign_model: str
    into_entity: str
    match_rules: list[MatchRule] = Field(default_factory=list)

    class Config:
        frozen = True


class IntegrationSpec(BaseModel):
    """
    Specification for an integration between internal and external systems.

    Integrations connect entities, surfaces, and experiences with services
    and foreign models.

    Attributes:
        name: Integration identifier
        title: Human-readable title
        service_refs: List of services used
        foreign_model_refs: List of foreign models used
        actions: List of on-demand actions
        syncs: List of sync operations
    """

    name: str
    title: str | None = None
    service_refs: list[str] = Field(default_factory=list)
    foreign_model_refs: list[str] = Field(default_factory=list)
    actions: list[IntegrationAction] = Field(default_factory=list)
    syncs: list[IntegrationSync] = Field(default_factory=list)

    class Config:
        frozen = True


# =============================================================================
# Tests - Test Specifications
# =============================================================================


class TestActionKind(str, Enum):
    """Types of test actions."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    CALL = "call"
    GET = "get"


class TestAssertionKind(str, Enum):
    """Types of test assertions."""

    STATUS = "status"
    CREATED = "created"
    FIELD = "field"
    ERROR = "error"
    COUNT = "count"


class TestComparisonOperator(str, Enum):
    """Comparison operators for test assertions."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"


class TestSetupStep(BaseModel):
    """
    Setup step in a test.

    Creates objects or sets up state before test action.
    """

    variable_name: str
    action: TestActionKind
    entity_name: str
    data: dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = True


class TestAction(BaseModel):
    """
    Main action to test.

    Attributes:
        kind: Type of action (create, update, delete, etc.)
        target: Entity or object being acted upon
        data: Data for the action
    """

    kind: TestActionKind
    target: str  # Entity name or variable reference
    data: dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = True


class TestAssertion(BaseModel):
    """
    Test assertion/expectation.

    Attributes:
        kind: Type of assertion
        field_name: Field being asserted (for FIELD assertions)
        operator: Comparison operator
        expected_value: Expected value
    """

    kind: TestAssertionKind
    field_name: str | None = None
    operator: TestComparisonOperator | None = None
    expected_value: Any | None = None
    error_message: str | None = None

    class Config:
        frozen = True


class TestSpec(BaseModel):
    """
    Test specification from DSL.

    Defines a test case with setup, action, and expectations.

    Attributes:
        name: Test identifier
        description: Human-readable description
        setup_steps: Objects to create before test
        action: Main action to test
        assertions: List of expected outcomes
    """

    name: str
    description: str | None = None
    setup_steps: list[TestSetupStep] = Field(default_factory=list)
    action: TestAction
    assertions: list[TestAssertion] = Field(default_factory=list)

    class Config:
        frozen = True


# =============================================================================
# Top-Level - App Specification
# =============================================================================


class UXLayouts(BaseModel):
    """
    Container for UX semantic layout specifications.

    Holds workspace layouts and persona definitions for the layout engine.

    Attributes:
        workspaces: List of workspace layout specifications
        personas: List of persona layout specifications
    """

    model_config = {"frozen": True}

    workspaces: list["WorkspaceLayout"] = Field(default_factory=list)
    personas: list["PersonaLayout"] = Field(default_factory=list)


class AppSpec(BaseModel):
    """
    Complete application specification.

    This is the root of the IR tree and represents a fully merged,
    linked application definition.

    Attributes:
        name: Application name
        title: Human-readable title
        version: Version string
        domain: Domain specification (entities)
        surfaces: List of surface specifications
        workspaces: List of workspace specifications
        experiences: List of experience specifications
        services: List of service specifications
        foreign_models: List of foreign model specifications
        integrations: List of integration specifications
        metadata: Additional metadata
    """

    name: str
    title: str | None = None
    version: str = "0.1.0"
    domain: DomainSpec
    surfaces: list[SurfaceSpec] = Field(default_factory=list)
    workspaces: list[WorkspaceSpec] = Field(default_factory=list)  # UX extension (old)
    experiences: list[ExperienceSpec] = Field(default_factory=list)
    services: list[ServiceSpec] = Field(default_factory=list)
    foreign_models: list[ForeignModelSpec] = Field(default_factory=list)
    integrations: list[IntegrationSpec] = Field(default_factory=list)
    tests: list[TestSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ux: UXLayouts | None = None  # Semantic layout engine (v0.3)

    class Config:
        frozen = True

    def get_entity(self, name: str) -> EntitySpec | None:
        """Get entity by name."""
        return self.domain.get_entity(name)

    def get_surface(self, name: str) -> SurfaceSpec | None:
        """Get surface by name."""
        for surface in self.surfaces:
            if surface.name == name:
                return surface
        return None

    def get_workspace(self, name: str) -> WorkspaceSpec | None:
        """Get workspace by name."""
        for workspace in self.workspaces:
            if workspace.name == name:
                return workspace
        return None

    def get_experience(self, name: str) -> ExperienceSpec | None:
        """Get experience by name."""
        for experience in self.experiences:
            if experience.name == name:
                return experience
        return None

    def get_service(self, name: str) -> ServiceSpec | None:
        """Get service by name."""
        for service in self.services:
            if service.name == name:
                return service
        return None

    def get_test(self, name: str) -> TestSpec | None:
        """Get test by name."""
        for test in self.tests:
            if test.name == name:
                return test
        return None

    def get_foreign_model(self, name: str) -> ForeignModelSpec | None:
        """Get foreign model by name."""
        for fm in self.foreign_models:
            if fm.name == name:
                return fm
        return None

    def get_integration(self, name: str) -> IntegrationSpec | None:
        """Get integration by name."""
        for integration in self.integrations:
            if integration.name == name:
                return integration
        return None

    @property
    def type_catalog(self) -> dict[str, list[FieldType]]:
        """
        Extract catalog of all field types used in the application.

        Returns a mapping of field names to the types they use across
        all entities and foreign models. Useful for:
        - Stack generators building type mappings
        - Detecting type inconsistencies (same field name, different types)
        - Schema evolution analysis

        Returns:
            Dict mapping field names to list of FieldType objects
        """
        catalog: dict[str, list[FieldType]] = {}

        # Collect from entities
        for entity in self.domain.entities:
            for field in entity.fields:
                if field.name not in catalog:
                    catalog[field.name] = []
                # Only add if not already present (avoid duplicates)
                if field.type not in catalog[field.name]:
                    catalog[field.name].append(field.type)

        # Collect from foreign models
        for foreign_model in self.foreign_models:
            for field in foreign_model.fields:
                if field.name not in catalog:
                    catalog[field.name] = []
                if field.type not in catalog[field.name]:
                    catalog[field.name].append(field.type)

        return catalog

    def get_field_type_conflicts(self) -> list[str]:
        """
        Detect fields with the same name but different types.

        Returns:
            List of warning messages about type conflicts
        """
        conflicts = []
        for field_name, types in self.type_catalog.items():
            if len(types) > 1:
                type_descriptions = [
                    f"{t.kind.value}"
                    + (
                        f"({t.max_length})"
                        if t.max_length
                        else f"({t.precision},{t.scale})"
                        if t.precision
                        else f"[{','.join(t.enum_values)}]"
                        if t.enum_values
                        else f" {t.ref_entity}"
                        if t.ref_entity
                        else ""
                    )
                    for t in types
                ]
                conflicts.append(
                    f"Field '{field_name}' has inconsistent types: {', '.join(type_descriptions)}"
                )
        return conflicts


# =============================================================================
# Module-Level IR (for parser output)
# =============================================================================


class ModuleFragment(BaseModel):
    """
    Parsed fragments from a single module.

    This is the output of parsing a single DSL file.

    Attributes:
        entities: Entities defined in this module
        surfaces: Surfaces defined in this module
        workspaces: Workspaces defined in this module
        experiences: Experiences defined in this module
        services: Services defined in this module
        foreign_models: Foreign models defined in this module
        integrations: Integrations defined in this module
        tests: Tests defined in this module
    """

    entities: list[EntitySpec] = Field(default_factory=list)
    surfaces: list[SurfaceSpec] = Field(default_factory=list)
    workspaces: list[WorkspaceSpec] = Field(default_factory=list)  # UX extension
    experiences: list[ExperienceSpec] = Field(default_factory=list)
    services: list[ServiceSpec] = Field(default_factory=list)
    foreign_models: list[ForeignModelSpec] = Field(default_factory=list)
    integrations: list[IntegrationSpec] = Field(default_factory=list)
    tests: list[TestSpec] = Field(default_factory=list)

    class Config:
        frozen = True


class ModuleIR(BaseModel):
    """
    Complete IR for a single module (file).

    Attributes:
        name: Module name (e.g., "vat_tools.core")
        file: Source file path
        app_name: App name (if declared in this module)
        app_title: App title (if declared in this module)
        uses: List of module names this module depends on
        fragment: Parsed DSL fragments
    """

    name: str
    file: Path
    app_name: str | None = None
    app_title: str | None = None
    uses: list[str] = Field(default_factory=list)
    fragment: ModuleFragment = Field(default_factory=ModuleFragment)

    class Config:
        frozen = True
        arbitrary_types_allowed = True  # for Path


# =============================================================================
# UI Semantic Layout IR (v0.3.0)
# =============================================================================


class AttentionSignalKind(str, Enum):
    """
    Semantic kinds of UI attention signals.

    Each kind represents a distinct UI interaction pattern that requires
    specific layout treatment.
    """

    KPI = "kpi"  # Key metric/number requiring visual prominence
    ALERT_FEED = "alert_feed"  # Stream of notifications/alerts
    TABLE = "table"  # Tabular data grid
    ITEM_LIST = "item_list"  # Vertical list of items
    DETAIL_VIEW = "detail_view"  # Full details of single item
    TASK_LIST = "task_list"  # Actionable task items
    FORM = "form"  # Input form for data entry
    CHART = "chart"  # Data visualization
    SEARCH = "search"  # Search interface
    FILTER = "filter"  # Filter controls


class LayoutSignal(BaseModel):
    """
    Semantic UI element requiring user attention in the layout engine.

    A layout signal represents a logical UI element that the user needs to
    be aware of and potentially interact with. Signals are allocated to surfaces
    by the layout engine based on their characteristics.

    Note: This is distinct from AttentionSignal (line 429) which is for DSL-based
    data-driven attention signals with conditions and messages.

    Attributes:
        id: Unique signal identifier
        kind: Semantic kind of signal
        label: Human-readable label
        source: Entity/surface reference that provides data
        attention_weight: Relative importance (0.0-1.0, higher = more important)
        urgency: How quickly user needs to respond
        interaction_frequency: How often user interacts with this signal
        density_preference: Preferred information density
        mode: Primary interaction mode
        constraints: Additional constraints (e.g., min_width, max_items)
    """

    model_config = {"frozen": True}

    id: str
    kind: AttentionSignalKind
    label: str
    source: str  # Entity or surface name
    attention_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency: str = "medium"  # low, medium, high
    interaction_frequency: str = "occasional"  # rare, occasional, frequent
    density_preference: str = "comfortable"  # compact, comfortable, spacious
    mode: str = "read"  # read, act, configure
    constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        """Validate urgency is one of allowed values."""
        if v not in ("low", "medium", "high"):
            raise ValueError(f"urgency must be low/medium/high, got: {v}")
        return v

    @field_validator("interaction_frequency")
    @classmethod
    def validate_interaction_frequency(cls, v: str) -> str:
        """Validate interaction frequency is one of allowed values."""
        if v not in ("rare", "occasional", "frequent"):
            raise ValueError(f"interaction_frequency must be rare/occasional/frequent, got: {v}")
        return v

    @field_validator("density_preference")
    @classmethod
    def validate_density_preference(cls, v: str) -> str:
        """Validate density preference is one of allowed values."""
        if v not in ("compact", "comfortable", "spacious"):
            raise ValueError(f"density_preference must be compact/comfortable/spacious, got: {v}")
        return v

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate mode is one of allowed values."""
        if v not in ("read", "act", "configure"):
            raise ValueError(f"mode must be read/act/configure, got: {v}")
        return v


class WorkspaceLayout(BaseModel):
    """
    Layout-enriched workspace definition.

    Extends the basic workspace concept with layout-specific metadata used
    by the layout engine to determine optimal UI structure.

    Attributes:
        id: Workspace identifier
        label: Human-readable label
        persona_targets: List of persona IDs this workspace is optimized for
        attention_budget: Total attention capacity (1.0 = normal, >1.0 = dense)
        time_horizon: Temporal focus of workspace
        engine_hint: Optional archetype hint (e.g., "scanner_table")
        attention_signals: List of signals to display in this workspace
    """

    model_config = {"frozen": True}

    id: str
    label: str
    persona_targets: list[str] = Field(default_factory=list)
    attention_budget: float = Field(default=1.0, ge=0.0, le=1.5)
    time_horizon: str = "daily"  # realtime, daily, archival
    engine_hint: str | None = None
    attention_signals: list["LayoutSignal"] = Field(default_factory=list)

    @field_validator("time_horizon")
    @classmethod
    def validate_time_horizon(cls, v: str) -> str:
        """Validate time horizon is one of allowed values."""
        if v not in ("realtime", "daily", "archival"):
            raise ValueError(f"time_horizon must be realtime/daily/archival, got: {v}")
        return v


class PersonaLayout(BaseModel):
    """
    Layout-enriched persona definition.

    Extends the basic persona concept with UI preference biases used by
    the layout engine to optimize interfaces for specific user roles.

    Attributes:
        id: Persona identifier
        label: Human-readable label
        goals: List of primary user goals
        proficiency_level: User expertise level
        session_style: Typical interaction pattern
        attention_biases: Signal kind → weight multiplier map
    """

    model_config = {"frozen": True}

    id: str
    label: str
    goals: list[str] = Field(default_factory=list)
    proficiency_level: str = "intermediate"  # novice, intermediate, expert
    session_style: str = "deep_work"  # glance, deep_work
    attention_biases: dict[str, float] = Field(default_factory=dict)

    @field_validator("proficiency_level")
    @classmethod
    def validate_proficiency_level(cls, v: str) -> str:
        """Validate proficiency level is one of allowed values."""
        if v not in ("novice", "intermediate", "expert"):
            raise ValueError(f"proficiency_level must be novice/intermediate/expert, got: {v}")
        return v

    @field_validator("session_style")
    @classmethod
    def validate_session_style(cls, v: str) -> str:
        """Validate session style is one of allowed values."""
        if v not in ("glance", "deep_work"):
            raise ValueError(f"session_style must be glance/deep_work, got: {v}")
        return v


class LayoutArchetype(str, Enum):
    """
    Named layout patterns with specific compositional rules.

    Each archetype defines a specific way to organize attention signals
    into a coherent UI structure.
    """

    FOCUS_METRIC = "focus_metric"  # Single dominant KPI/metric
    SCANNER_TABLE = "scanner_table"  # Table-centric with filters
    DUAL_PANE_FLOW = "dual_pane_flow"  # List + detail master-detail
    MONITOR_WALL = "monitor_wall"  # Multiple moderate-importance signals
    COMMAND_CENTER = "command_center"  # Dense, expert-focused dashboard


class LayoutSurface(BaseModel):
    """
    Named region within a layout where signals are rendered.

    Surfaces are the building blocks of layout archetypes. Each surface
    has a specific purpose and capacity constraints.

    Attributes:
        id: Surface identifier (e.g., "primary", "sidebar", "toolbar")
        archetype: Parent archetype
        capacity: Maximum attention weight this surface can hold
        priority: Surface priority for signal allocation
        assigned_signals: List of signal IDs assigned to this surface
        constraints: Surface-specific constraints
    """

    model_config = {"frozen": True}

    id: str
    archetype: LayoutArchetype
    capacity: float = Field(default=1.0, ge=0.0)
    priority: int = Field(default=1, ge=1)
    assigned_signals: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class LayoutPlan(BaseModel):
    """
    Deterministic output of the layout engine.

    The layout plan specifies exactly how a workspace should be rendered,
    including which archetype to use, where each signal appears, and
    any warnings about over-budget situations.

    Attributes:
        workspace_id: Source workspace identifier
        persona_id: Target persona identifier (if persona-specific)
        archetype: Selected layout archetype
        surfaces: List of surfaces with assigned signals
        over_budget_signals: Signal IDs that couldn't fit
        warnings: Layout warnings (e.g., attention budget exceeded)
        metadata: Additional metadata for debugging/logging
    """

    model_config = {"frozen": True}

    workspace_id: str
    persona_id: str | None = None
    archetype: LayoutArchetype
    surfaces: list[LayoutSurface] = Field(default_factory=list)
    over_budget_signals: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
