"""
Entity specification types for BackendSpec.

Defines entities, fields, relationships, validators, and access rules.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import EntityAccessSpec

# =============================================================================
# Field Type System
# =============================================================================


class ScalarType(StrEnum):
    """Scalar field types."""

    STR = "str"
    TEXT = "text"
    INT = "int"
    DECIMAL = "decimal"
    BOOL = "bool"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    EMAIL = "email"
    URL = "url"
    JSON = "json"
    # File types (Week 9-10)
    FILE = "file"
    IMAGE = "image"
    RICHTEXT = "richtext"
    # Timezone (v0.10.3)
    TIMEZONE = "timezone"  # IANA timezone identifier


class FileFieldConfig(BaseModel):
    """Configuration for file/image fields."""

    max_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum file size in bytes",
    )
    allowed_types: list[str] | None = Field(
        default=None,
        description="Allowed MIME types (e.g., ['image/png', 'image/jpeg'])",
    )
    multiple: bool = Field(
        default=False,
        description="Allow multiple files",
    )
    # Image-specific options
    generate_thumbnail: bool = Field(
        default=True,
        description="Generate thumbnail for images",
    )
    thumbnail_width: int = Field(
        default=200,
        description="Thumbnail width in pixels",
    )
    thumbnail_height: int = Field(
        default=200,
        description="Thumbnail height in pixels",
    )

    model_config = ConfigDict(frozen=True)


class RichTextConfig(BaseModel):
    """Configuration for rich text fields."""

    format: Literal["markdown", "html"] = Field(
        default="markdown",
        description="Rich text format",
    )
    max_length: int | None = Field(
        default=None,
        description="Maximum content length",
    )
    allow_images: bool = Field(
        default=True,
        description="Allow inline images",
    )
    sanitize: bool = Field(
        default=True,
        description="Sanitize HTML output",
    )

    model_config = ConfigDict(frozen=True)


class FieldType(BaseModel):
    """
    Field type specification.

    Examples:
        - str: FieldType(kind="scalar", scalar_type=ScalarType.STR)
        - str(200): FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200)
        - decimal(10,2): FieldType(kind="scalar", scalar_type=ScalarType.DECIMAL, precision=10, scale=2)
        - enum: FieldType(kind="enum", enum_values=["draft", "issued"])
        - ref: FieldType(kind="ref", ref_entity="Client")
        - file: FieldType(kind="scalar", scalar_type=ScalarType.FILE, file_config=FileFieldConfig())
        - richtext: FieldType(kind="scalar", scalar_type=ScalarType.RICHTEXT, richtext_config=RichTextConfig())
    """

    kind: Literal["scalar", "enum", "ref"] = Field(
        description="Type category: scalar, enum, or ref"
    )
    scalar_type: ScalarType | None = Field(
        default=None, description="Scalar type (for kind=scalar)"
    )
    max_length: int | None = Field(default=None, description="Max length for str types")
    precision: int | None = Field(default=None, description="Precision for decimal types")
    scale: int | None = Field(default=None, description="Scale for decimal types")
    enum_values: list[str] | None = Field(default=None, description="Allowed values for enum types")
    ref_entity: str | None = Field(default=None, description="Referenced entity name for ref types")
    # File field configuration (for FILE/IMAGE types)
    file_config: FileFieldConfig | None = Field(
        default=None, description="File upload configuration"
    )
    # Rich text configuration (for RICHTEXT type)
    richtext_config: RichTextConfig | None = Field(
        default=None, description="Rich text configuration"
    )

    model_config = ConfigDict(frozen=True)

    @field_validator("enum_values")
    @classmethod
    def validate_enum_values(cls, v: list[str] | None) -> list[str] | None:
        """Ensure enum values are valid identifiers."""
        if v:
            for val in v:
                if not val.replace("_", "").replace("-", "").isalnum():
                    raise ValueError(f"Enum value '{val}' must be alphanumeric (with _ or -)")
        return v


# Convenience constructors
EnumType = FieldType  # FieldType(kind="enum", enum_values=[...])
RefType = FieldType  # FieldType(kind="ref", ref_entity="...")


# =============================================================================
# Validators
# =============================================================================


class ValidatorKind(StrEnum):
    """Types of validators."""

    MIN = "min"
    MAX = "max"
    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    PATTERN = "pattern"
    EMAIL = "email"
    URL = "url"
    CUSTOM = "custom"


class ValidatorSpec(BaseModel):
    """
    Validation rule for a field.

    Examples:
        - ValidatorSpec(kind="min", value=0)
        - ValidatorSpec(kind="pattern", value="^[A-Z]{3}$")
        - ValidatorSpec(kind="custom", expr="value > start_date")
    """

    kind: ValidatorKind = Field(description="Validator type")
    value: Any | None = Field(default=None, description="Validator value (e.g., min=0)")
    expr: str | None = Field(default=None, description="Custom expression (for kind=custom)")
    message: str | None = Field(default=None, description="Custom error message")

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Fields
# =============================================================================


class FieldSpec(BaseModel):
    """
    Field specification for an entity.

    Attributes:
        name: Field identifier
        type: Field type specification
        required: Whether the field is required
        default: Default value
        validators: List of validation rules
        indexed: Whether to create a database index
        unique: Whether values must be unique
    """

    name: str = Field(description="Field name")
    label: str | None = Field(default=None, description="Human-readable label")
    type: FieldType = Field(description="Field type specification")
    required: bool = Field(default=False, description="Is this field required?")
    default: Any | None = Field(default=None, description="Default value")
    validators: list[ValidatorSpec] = Field(default_factory=list, description="Validation rules")
    indexed: bool = Field(default=False, description="Create database index?")
    unique: bool = Field(default=False, description="Values must be unique?")
    auto_add: bool = Field(default=False, description="Auto-set on create (e.g. created_at)")
    auto_update: bool = Field(default=False, description="Auto-set on update (e.g. updated_at)")

    model_config = ConfigDict(frozen=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure field name is a valid identifier."""
        if not v.isidentifier():
            raise ValueError(f"Field name '{v}' must be a valid identifier")
        return v


# =============================================================================
# Relations
# =============================================================================


class RelationKind(StrEnum):
    """Types of relationships between entities."""

    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"
    ONE_TO_ONE = "one_to_one"


class OnDeleteAction(StrEnum):
    """Actions to take when referenced entity is deleted."""

    RESTRICT = "restrict"
    CASCADE = "cascade"
    NULLIFY = "nullify"
    SET_DEFAULT = "set_default"


class RelationSpec(BaseModel):
    """
    Relationship between entities.

    Examples:
        - One-to-many: Client has many Invoices
          RelationSpec(name="invoices", from_entity="Client", to_entity="Invoice", kind="one_to_many")

        - Many-to-one: Invoice belongs to Client
          RelationSpec(name="client", from_entity="Invoice", to_entity="Client", kind="many_to_one")
    """

    name: str = Field(description="Relation name")
    from_entity: str = Field(description="Source entity")
    to_entity: str = Field(description="Target entity")
    kind: RelationKind = Field(description="Relationship type")
    backref: str | None = Field(default=None, description="Back-reference name on target entity")
    on_delete: OnDeleteAction = Field(
        default=OnDeleteAction.RESTRICT, description="Action on delete"
    )
    required: bool = Field(default=False, description="Is this relation required?")

    model_config = ConfigDict(frozen=True)


# =============================================================================
# State Machine Types
# =============================================================================


class TimeUnit(StrEnum):
    """Time units for auto-transition delays."""

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"


class TransitionTrigger(StrEnum):
    """How a transition can be triggered."""

    MANUAL = "manual"
    AUTO = "auto"


class TransitionGuardSpec(BaseModel):
    """
    A guard condition that must be satisfied for a transition.

    Guards can be:
    - Field requirements: requires assignee (field must be set)
    - Role requirements: role(admin) (user must have role)
    """

    requires_field: str | None = Field(default=None, description="Field that must be set")
    requires_role: str | None = Field(default=None, description="Role user must have")

    model_config = ConfigDict(frozen=True)


class AutoTransitionSpec(BaseModel):
    """
    Specification for automatic transitions.

    Example: auto after 7 days
    """

    delay_value: int = Field(description="Delay value")
    delay_unit: TimeUnit = Field(description="Delay unit")
    allow_manual: bool = Field(default=False, description="Allow manual trigger too")

    model_config = ConfigDict(frozen=True)

    @property
    def delay_seconds(self) -> int:
        """Get delay in seconds."""
        if self.delay_unit == TimeUnit.MINUTES:
            return self.delay_value * 60
        elif self.delay_unit == TimeUnit.HOURS:
            return self.delay_value * 3600
        else:  # DAYS
            return self.delay_value * 86400


class StateTransitionSpec(BaseModel):
    """
    A single state transition definition.

    Attributes:
        from_state: State to transition from ("*" means any state)
        to_state: State to transition to
        trigger: How the transition is triggered (manual or auto)
        guards: Conditions that must be met
        auto_spec: Specification for automatic transitions
    """

    from_state: str = Field(description="Source state ('*' for wildcard)")
    to_state: str = Field(description="Target state")
    trigger: TransitionTrigger = Field(default=TransitionTrigger.MANUAL, description="Trigger type")
    guards: list[TransitionGuardSpec] = Field(default_factory=list, description="Guard conditions")
    auto_spec: AutoTransitionSpec | None = Field(default=None, description="Auto transition config")

    model_config = ConfigDict(frozen=True)

    @property
    def is_wildcard(self) -> bool:
        """Check if this is a wildcard transition."""
        return self.from_state == "*"


class StateMachineSpec(BaseModel):
    """
    Complete state machine specification for an entity.

    Attributes:
        status_field: Name of the field that holds the state
        states: List of valid states
        transitions: List of allowed state transitions
    """

    status_field: str = Field(description="Field holding the state")
    states: list[str] = Field(default_factory=list, description="Valid states")
    transitions: list[StateTransitionSpec] = Field(
        default_factory=list, description="Allowed transitions"
    )

    model_config = ConfigDict(frozen=True)

    def get_transitions_from(self, state: str) -> list[StateTransitionSpec]:
        """Get all transitions from a given state."""
        result = []
        for t in self.transitions:
            if t.from_state == state or t.from_state == "*":
                result.append(t)
        return result

    def get_allowed_targets(self, from_state: str) -> set[str]:
        """Get all states reachable from a given state."""
        targets = set()
        for t in self.get_transitions_from(from_state):
            targets.add(t.to_state)
        return targets

    def is_transition_allowed(self, from_state: str, to_state: str) -> bool:
        """Check if a transition is allowed (ignoring guards)."""
        return to_state in self.get_allowed_targets(from_state)

    def get_transition(self, from_state: str, to_state: str) -> StateTransitionSpec | None:
        """Get the transition definition between two states."""
        for t in self.transitions:
            if (t.from_state == from_state or t.from_state == "*") and t.to_state == to_state:
                return t
        return None


# =============================================================================
# Entities
# =============================================================================


class AggregateFunctionKind(StrEnum):
    """Supported aggregate functions for computed fields."""

    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    DAYS_UNTIL = "days_until"
    DAYS_SINCE = "days_since"


class ArithmeticOperatorKind(StrEnum):
    """Arithmetic operators for computed expressions."""

    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"


class ComputedExprSpec(BaseModel):
    """
    Computed expression specification.

    Represents a node in the expression tree for computed fields.
    """

    kind: Literal["field_ref", "aggregate", "arithmetic", "literal"] = Field(
        description="Expression type"
    )
    # For field_ref: path to the field
    path: list[str] | None = Field(default=None, description="Field path for field_ref")
    # For aggregate: function and field
    function: AggregateFunctionKind | None = Field(default=None, description="Aggregate function")
    field: "ComputedExprSpec | None" = Field(default=None, description="Field for aggregate")
    # For arithmetic: left, operator, right
    left: "ComputedExprSpec | None" = Field(default=None, description="Left operand")
    operator: ArithmeticOperatorKind | None = Field(default=None, description="Arithmetic operator")
    right: "ComputedExprSpec | None" = Field(default=None, description="Right operand")
    # For literal: value
    value: int | float | None = Field(default=None, description="Literal value")

    model_config = ConfigDict(frozen=True)


class ComputedFieldSpec(BaseModel):
    """
    Computed (derived) field specification.

    Computed fields are calculated from other fields at runtime.

    Examples:
        - total: computed sum(line_items.amount)
        - days_left: computed days_until(due_date)
        - tax: computed subtotal * 0.1
    """

    name: str = Field(description="Field name")
    expression: ComputedExprSpec = Field(description="Expression to compute")

    model_config = ConfigDict(frozen=True)


# Rebuild model for recursive types
ComputedExprSpec.model_rebuild()


# =============================================================================
# Invariants
# =============================================================================


class InvariantComparisonKind(StrEnum):
    """Comparison operators for invariant expressions."""

    EQ = "=="
    NE = "!="
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="


class InvariantLogicalKind(StrEnum):
    """Logical operators for combining invariant conditions."""

    AND = "and"
    OR = "or"


class DurationUnitKind(StrEnum):
    """Time units for duration expressions."""

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"  # v0.10.2
    MONTHS = "months"  # v0.10.2
    YEARS = "years"  # v0.10.2


class InvariantExprSpec(BaseModel):
    """
    Invariant expression specification.

    Represents a node in the expression tree for invariant conditions.
    """

    kind: Literal["field_ref", "literal", "duration", "comparison", "logical", "not"] = Field(
        description="Expression type"
    )
    # For field_ref: path to the field
    path: list[str] | None = Field(default=None, description="Field path for field_ref")
    # For literal: value (string, number, or bool)
    value: int | float | str | bool | None = Field(default=None, description="Literal value")
    # For duration: value and unit
    duration_value: int | None = Field(default=None, description="Duration value")
    duration_unit: DurationUnitKind | None = Field(default=None, description="Duration unit")
    # For comparison: left, operator, right
    comparison_left: "InvariantExprSpec | None" = Field(
        default=None, description="Left operand for comparison"
    )
    comparison_op: InvariantComparisonKind | None = Field(
        default=None, description="Comparison operator"
    )
    comparison_right: "InvariantExprSpec | None" = Field(
        default=None, description="Right operand for comparison"
    )
    # For logical: left, operator, right
    logical_left: "InvariantExprSpec | None" = Field(
        default=None, description="Left operand for logical"
    )
    logical_op: InvariantLogicalKind | None = Field(default=None, description="Logical operator")
    logical_right: "InvariantExprSpec | None" = Field(
        default=None, description="Right operand for logical"
    )
    # For not: operand
    not_operand: "InvariantExprSpec | None" = Field(
        default=None, description="Operand for NOT expression"
    )

    model_config = ConfigDict(frozen=True)


class InvariantSpec(BaseModel):
    """
    Entity invariant specification.

    Invariants are cross-field constraints that must always hold.

    Examples:
        - invariant: end_date > start_date
        - invariant: quantity >= 0
        - invariant: status == "active" or status == "pending"
    """

    expression: InvariantExprSpec = Field(description="Invariant condition")
    message: str | None = Field(default=None, description="Custom error message")

    model_config = ConfigDict(frozen=True)


# Rebuild model for recursive types
InvariantExprSpec.model_rebuild()


class EntitySpec(BaseModel):
    """
    Entity specification.

    An entity represents a domain model with fields and relationships.

    Example:
        EntitySpec(
            name="Client",
            label="Client",
            fields=[
                FieldSpec(name="name", type=FieldType(kind="scalar", scalar_type=ScalarType.STR)),
                FieldSpec(name="email", type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL)),
            ],
            relations=[
                RelationSpec(name="invoices", to_entity="Invoice", kind=RelationKind.ONE_TO_MANY)
            ]
        )
    """

    name: str = Field(description="Entity name")
    label: str | None = Field(default=None, description="Human-readable label")
    description: str | None = Field(default=None, description="Entity description")
    fields: list[FieldSpec] = Field(default_factory=list, description="Entity fields")
    computed_fields: list[ComputedFieldSpec] = Field(
        default_factory=list, description="Computed (derived) fields"
    )
    invariants: list[InvariantSpec] = Field(
        default_factory=list, description="Entity invariants (cross-field constraints)"
    )
    relations: list[RelationSpec] = Field(default_factory=list, description="Entity relationships")
    state_machine: StateMachineSpec | None = Field(
        default=None, description="State machine for status field transitions"
    )
    access: EntityAccessSpec | None = Field(
        default=None, description="Entity access rules (visibility and permissions)"
    )
    # v0.10.3: Archetype flags
    is_singleton: bool = Field(
        default=False,
        description="Entity is a singleton (settings entity - only one record exists)",
    )
    is_tenant_root: bool = Field(
        default=False,
        description="Entity is the tenant root (defines multi-tenant boundary)",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(frozen=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure entity name is a valid identifier."""
        if not v.isidentifier():
            raise ValueError(f"Entity name '{v}' must be a valid identifier")
        return v

    def get_field(self, name: str) -> FieldSpec | None:
        """Get field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None

    def get_relation(self, name: str) -> RelationSpec | None:
        """Get relation by name."""
        for relation in self.relations:
            if relation.name == name:
                return relation
        return None
