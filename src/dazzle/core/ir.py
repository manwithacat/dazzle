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
    """

    name: str
    title: str | None = None
    entity_ref: str | None = None
    mode: SurfaceMode
    sections: list[SurfaceSection] = Field(default_factory=list)
    actions: list[SurfaceAction] = Field(default_factory=list)

    class Config:
        frozen = True


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
    experiences: list[ExperienceSpec] = Field(default_factory=list)
    services: list[ServiceSpec] = Field(default_factory=list)
    foreign_models: list[ForeignModelSpec] = Field(default_factory=list)
    integrations: list[IntegrationSpec] = Field(default_factory=list)
    tests: list[TestSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

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
        experiences: Experiences defined in this module
        services: Services defined in this module
        foreign_models: Foreign models defined in this module
        integrations: Integrations defined in this module
        tests: Tests defined in this module
    """

    entities: list[EntitySpec] = Field(default_factory=list)
    surfaces: list[SurfaceSpec] = Field(default_factory=list)
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
