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
    from .pii import PIIAnnotation


class FieldTypeKind(StrEnum):
    """Enumeration of supported field types in DAZZLE."""

    STR = "str"
    TEXT = "text"
    INT = "int"
    DECIMAL = "decimal"
    FLOAT = "float"  # v0.46.0: IEEE 754 double precision (sensors, weights, scores)
    BOOL = "bool"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    ENUM = "enum"
    REF = "ref"
    EMAIL = "email"
    # #1288 Phase 1+validator: URL-safe identifier with built-in regex + length
    # enforcement. Bare `slug` enforces lowercase letters, digits, and single
    # internal hyphens, length 3-40 inclusive. Per-field min/max/reserved-list
    # configuration is Phase 2 (out of scope here).
    SLUG = "slug"
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
    # #1223 Phase 3a.v — derived current-row relationship for temporal entities.
    # `current_employment: latest_one Employment via person` resolves at read
    # time to "the Employment row where person = self.id AND end_date IS NULL".
    # Target entity MUST declare `temporal:` so the framework knows which
    # end_field to filter on. v0.71.165: IR + parser + validator only;
    # runtime resolution in a follow-up slice (3a.v.ii).
    LATEST_ONE = "latest_one"
    # #1227 Phase 3b — derived recursive traversal of self-referencing
    # hierarchies. `all_descendants: descendants_of self via parent_department`
    # for self-ref FKs; `all_reports: descendants_of self via ManagerLink.manager`
    # for via-junction traversal (composes with the junction's temporal:
    # default_filter for active-only walks). v0.71.174: IR + parser + validator
    # only; runtime resolution (recursive CTE) lands in 3b.ii.
    DESCENDANTS_OF = "descendants_of"
    ANCESTORS_OF = "ancestors_of"
    # #1448 — typed polymorphic reference. `poly_ref target [A, B]` owns two
    # physical columns (target_type text, target_id uuid) and replaces the
    # stringly-typed entity_type/entity_id pathology. Targets MUST be uuid-pk.
    POLY_REF = "poly_ref"


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
    ref_entity: str | None = None  # for ref, has_many, has_one, embeds, belongs_to, latest_one
    relationship_behavior: RelationshipBehavior | None = None  # for has_many, has_one
    readonly: bool = False  # for relationships - cannot modify through this relationship
    # #1223 Phase 3a.v: for latest_one — names the FK column on the target
    # entity pointing back to this entity. Required (parser refuses bare
    # `latest_one EntityName` without `via field`).
    via_field: str | None = None
    # v0.9.5: Money type configuration
    currency_code: str | None = None  # for money (e.g., "GBP", "USD", "EUR")
    # v0.9.5: Many-to-many via junction table
    via_entity: str | None = None  # for has_many with junction table (m:n relationship)
    # #1448: for poly_ref — the ordered set of legal target entity names.
    poly_targets: list[str] | None = None
    # v0.39.0: Per-field upload size limit
    max_size: int | None = None  # for file (bytes, e.g., 200*1024*1024 for 200MB)
    # #1213: file UI-mode modifier.
    # - "drag_drop" (Phase B) — documented no-op label; the default
    #   rendering already emits a drag-drop zone.
    # - "managed_upload" (Phase C) — JS switches to the
    #   ticket→S3→implicit-finalize flow via the auto-generated
    #   `/api/{entity}/upload-ticket` route. The framework's
    #   `verify_storage_field_keys` hook on entity-create POSTs
    #   provides the implicit finalize (prefix-sandbox + head_object).
    ui_mode: str | None = None  # for file: None | "drag_drop" | "managed_upload"

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
    SEARCHABLE = "searchable"  # v0.34.0: Include in full-text search
    INDEXED = "indexed"  # v0.44.0: Create database index on this field


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
    # v0.61.0: PII classification (category + sensitivity). See core/ir/pii.py.
    pii: PIIAnnotation | None = None
    # v0.61.104 (#932): names of `[storage.<name>]` blocks declared in
    # `dazzle.toml`. Only meaningful for `file` typed fields. The
    # framework's auto-generated upload-ticket / finalize routes use the
    # bindings to look up prefix templates, content-type allowlists,
    # max-bytes policies, etc. Empty tuple = no storage binding (no
    # auto-upload routes).
    #
    # v0.61.113 (#941) widened from `str | None` to `tuple[str, ...]` to
    # model fields that accept either a per-user upload OR a shared
    # asset reference:
    #
    #     source_pdf_url: file storage=cohort_pdfs|starter_packs
    #
    # The verifier accepts the s3_key against each binding in turn and
    # passes if any one matches. The first binding is the canonical
    # *upload* destination — the auto-generated upload-ticket route
    # mints presigned forms against `storage[0]`. Single-binding fields
    # are simply tuples of length one.
    storage: tuple[str, ...] = Field(default_factory=tuple)
    # #1431 migration engine: `was: OldName` rename hint (transient — present only
    # during the migration-planning pass; not persisted to the DB schema).
    renamed_from: str | None = Field(
        default=None,
        description="Previous field name declared via `was:` rename hint (#1431, transient).",
    )

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

    @property
    def is_pii(self) -> bool:
        """True if the field carries a structured PII annotation (v0.61.0)."""
        return self.pii is not None

    @property
    def is_special_category(self) -> bool:
        """True for GDPR Article 9/10 special-category data (v0.61.0)."""
        return self.pii is not None and self.pii.is_special_category

    @property
    def is_searchable(self) -> bool:
        """Check if field is included in full-text search (v0.34.0)."""
        return FieldModifier.SEARCHABLE in self.modifiers

    @property
    def is_indexed(self) -> bool:
        """Check if field should have a database index (v0.44.0)."""
        return FieldModifier.INDEXED in self.modifiers


def _rebuild_field_spec() -> None:
    """Rebuild FieldSpec model to resolve forward references to date and expression types."""
    # Import here to avoid circular imports
    from .dates import DateArithmeticExpr, DateLiteral
    from .expressions import Expr
    from .pii import PIIAnnotation

    FieldSpec.model_rebuild(
        _types_namespace={
            "DateLiteral": DateLiteral,
            "DateArithmeticExpr": DateArithmeticExpr,
            "Expr": Expr,
            "PIIAnnotation": PIIAnnotation,
        }
    )


# Call rebuild after module initialization
_rebuild_field_spec()
