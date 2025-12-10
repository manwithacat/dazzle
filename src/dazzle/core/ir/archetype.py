"""
Archetype types for DAZZLE IR.

Archetypes are reusable templates that can be extended by entities.
They define common field patterns (audit trails, soft delete, etc.)
that can be composed into entities.

v0.7.1: Added for LLM cognition
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .computed import ComputedFieldSpec
from .fields import FieldSpec
from .invariant import InvariantSpec


class ArchetypeSpec(BaseModel):
    """
    Specification for a reusable archetype.

    Archetypes define common patterns that can be inherited by entities.
    When an entity uses `extends: ArchetypeName`, the archetype's fields,
    computed fields, and invariants are merged into the entity.

    Examples:
        archetype Auditable:
          created_at: datetime auto_add
          updated_at: datetime auto_update
          created_by: ref User

        archetype SoftDeletable:
          deleted_at: datetime
          is_deleted: bool = false

        entity Invoice "Invoice":
          extends: Auditable, SoftDeletable
          amount: decimal(10,2) required
    """

    name: str
    fields: list[FieldSpec] = Field(default_factory=list)
    computed_fields: list[ComputedFieldSpec] = Field(default_factory=list)
    invariants: list[InvariantSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
