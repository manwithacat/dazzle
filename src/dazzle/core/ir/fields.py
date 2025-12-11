"""
Field type definitions for DAZZLE IR.

This module contains the core field type system including field types,
modifiers, and field specifications.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    JSON = "json"  # v0.9.4: Flexible JSON data (maps to JSONB/JSON in databases)
    # v0.7.1: Relationship types with ownership semantics
    HAS_MANY = "has_many"
    HAS_ONE = "has_one"
    EMBEDS = "embeds"
    BELONGS_TO = "belongs_to"


class RelationshipBehavior(str, Enum):
    """Delete behavior for relationships (v0.7.1)."""

    CASCADE = "cascade"  # Delete children when parent deleted
    RESTRICT = "restrict"  # Prevent delete if children exist
    NULLIFY = "nullify"  # Set FK to null on parent delete


class FieldType(BaseModel):
    """
    Represents a field type specification.

    Examples:
        - str(200): FieldType(kind=STR, max_length=200)
        - decimal(10,2): FieldType(kind=DECIMAL, precision=10, scale=2)
        - enum[draft,issued]: FieldType(kind=ENUM, enum_values=["draft", "issued"])
        - ref Client: FieldType(kind=REF, ref_entity="Client")

    v0.7.1 Relationship examples:
        - has_many OrderItem cascade: FieldType(kind=HAS_MANY, ref_entity="OrderItem", relationship_behavior=CASCADE)
        - has_one Profile: FieldType(kind=HAS_ONE, ref_entity="Profile")
        - embeds Address: FieldType(kind=EMBEDS, ref_entity="Address")
        - belongs_to Order: FieldType(kind=BELONGS_TO, ref_entity="Order")
    """

    kind: FieldTypeKind
    max_length: int | None = None  # for str
    precision: int | None = None  # for decimal
    scale: int | None = None  # for decimal
    enum_values: list[str] | None = None  # for enum
    ref_entity: str | None = None  # for ref, has_many, has_one, embeds, belongs_to
    relationship_behavior: RelationshipBehavior | None = None  # for has_many, has_one
    readonly: bool = False  # for relationships - cannot modify through this relationship

    model_config = ConfigDict(frozen=True)

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

    model_config = ConfigDict(frozen=True)

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
