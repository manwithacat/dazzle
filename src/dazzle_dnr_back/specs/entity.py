"""
Entity specification types for BackendSpec.

Defines entities, fields, relationships, and validators.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Field Type System
# =============================================================================


class ScalarType(str, Enum):
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
    max_length: int | None = Field(
        default=None, description="Max length for str types"
    )
    precision: int | None = Field(
        default=None, description="Precision for decimal types"
    )
    scale: int | None = Field(default=None, description="Scale for decimal types")
    enum_values: list[str] | None = Field(
        default=None, description="Allowed values for enum types"
    )
    ref_entity: str | None = Field(
        default=None, description="Referenced entity name for ref types"
    )
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
                    raise ValueError(
                        f"Enum value '{val}' must be alphanumeric (with _ or -)"
                    )
        return v


# Convenience constructors
EnumType = FieldType  # FieldType(kind="enum", enum_values=[...])
RefType = FieldType  # FieldType(kind="ref", ref_entity="...")


# =============================================================================
# Validators
# =============================================================================


class ValidatorKind(str, Enum):
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
    expr: str | None = Field(
        default=None, description="Custom expression (for kind=custom)"
    )
    message: str | None = Field(
        default=None, description="Custom error message"
    )

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
    validators: list[ValidatorSpec] = Field(
        default_factory=list, description="Validation rules"
    )
    indexed: bool = Field(default=False, description="Create database index?")
    unique: bool = Field(default=False, description="Values must be unique?")

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


class RelationKind(str, Enum):
    """Types of relationships between entities."""

    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"
    ONE_TO_ONE = "one_to_one"


class OnDeleteAction(str, Enum):
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
    backref: str | None = Field(
        default=None, description="Back-reference name on target entity"
    )
    on_delete: OnDeleteAction = Field(
        default=OnDeleteAction.RESTRICT, description="Action on delete"
    )
    required: bool = Field(
        default=False, description="Is this relation required?"
    )

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Entities
# =============================================================================


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
    fields: list[FieldSpec] = Field(
        default_factory=list, description="Entity fields"
    )
    relations: list[RelationSpec] = Field(
        default_factory=list, description="Entity relationships"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

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
