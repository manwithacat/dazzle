"""
Field type definitions for DAZZLE IR.

This module contains the core field type system including field types,
modifiers, and field specifications.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from .dates import DateArithmeticExpr, DateLiteral
    from .expressions import Expr


class FieldTypeKind(StrEnum):
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
    # v0.9.5: Additional semantic types
    MONEY = "money"  # Currency amount with optional currency code (maps to decimal + metadata)
    FILE = "file"  # File reference/upload (stores path/URL/identifier)
    URL = "url"  # URL/URI string with validation
    # v0.10.3: Timezone type for settings
    TIMEZONE = "timezone"  # IANA timezone identifier (e.g., "Europe/London", "America/New_York")
    # v0.7.1: Relationship types with ownership semantics
    HAS_MANY = "has_many"
    HAS_ONE = "has_one"
    EMBEDS = "embeds"
    BELONGS_TO = "belongs_to"


class RelationshipBehavior(StrEnum):
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
        - has_many OrderItem cascade: FieldType(
            kind=HAS_MANY, ref_entity="OrderItem",
            relationship_behavior=CASCADE)
        - has_one Profile: FieldType(kind=HAS_ONE, ref_entity="Profile")
        - embeds Address: FieldType(kind=EMBEDS, ref_entity="Address")
        - belongs_to Order: FieldType(kind=BELONGS_TO, ref_entity="Order")

    v0.9.5 Semantic type examples:
        - money: FieldType(kind=MONEY, currency_code="GBP") - defaults to GBP
        - money(USD): FieldType(kind=MONEY, currency_code="USD")
        - file: FieldType(kind=FILE)
        - url: FieldType(kind=URL)

    v0.9.5 Many-to-many via junction table:
        - has_many Contact via ClientContact:
          FieldType(kind=HAS_MANY, ref_entity="Contact",
          via_entity="ClientContact")
    """

    kind: FieldTypeKind
    max_length: int | None = None  # for str
    precision: int | None = None  # for decimal
    scale: int | None = None  # for decimal
    enum_values: list[str] | None = None  # for enum
    ref_entity: str | None = None  # for ref, has_many, has_one, embeds, belongs_to
    relationship_behavior: RelationshipBehavior | None = None  # for has_many, has_one
    readonly: bool = False  # for relationships - cannot modify through this relationship
    # v0.9.5: Money type configuration
    currency_code: str | None = None  # for money (e.g., "GBP", "USD", "EUR")
    # v0.9.5: Many-to-many via junction table
    via_entity: str | None = None  # for has_many with junction table (m:n relationship)

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


class FieldModifier(StrEnum):
    """Modifiers that can be applied to fields."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    PK = "pk"
    UNIQUE = "unique"
    UNIQUE_NULLABLE = "unique?"
    AUTO_ADD = "auto_add"
    AUTO_UPDATE = "auto_update"
    SENSITIVE = "sensitive"


class FieldSpec(BaseModel):
    """
    Specification for a single field in an entity or foreign model.

    Attributes:
        name: Field identifier
        type: Field type specification
        modifiers: List of modifiers (required, pk, unique, etc.)
        default: Optional default value (scalar or date expression)

    v0.10.2: default can now be a date expression for date/datetime fields:
        - today, now (literals)
        - today + 7d, now - 24h (arithmetic)

    v0.29.0: default_expr for typed expression defaults:
        - field box3: money GBP = box1 + box2
        - field urgency: enum[red,amber,green] = if days < 0: "red" else: "green"
    """

    name: str
    type: FieldType
    modifiers: list[FieldModifier] = Field(default_factory=list)
    # Default can be a scalar or a date expression (DateLiteral, DateArithmeticExpr)
    default: str | int | float | bool | DateLiteral | DateArithmeticExpr | None = None
    # v0.29.0: Typed expression default (evaluated at read time)
    default_expr: Expr | None = None

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

    @property
    def is_sensitive(self) -> bool:
        """Check if field contains sensitive data (PII, credentials, etc.)."""
        return FieldModifier.SENSITIVE in self.modifiers


def _rebuild_field_spec() -> None:
    """Rebuild FieldSpec model to resolve forward references to date and expression types."""
    # Import here to avoid circular imports
    from .dates import DateArithmeticExpr, DateLiteral
    from .expressions import Expr

    FieldSpec.model_rebuild(
        _types_namespace={
            "DateLiteral": DateLiteral,
            "DateArithmeticExpr": DateArithmeticExpr,
            "Expr": Expr,
        }
    )


# Call rebuild after module initialization
_rebuild_field_spec()
