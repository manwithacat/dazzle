"""
Archetype types for DAZZLE IR.

Archetypes are reusable templates that can be extended by entities.
They define common field patterns (audit trails, soft delete, etc.)
that can be composed into entities.

v0.7.1: Added for LLM cognition
v0.10.3: Added ArchetypeKind for semantic archetypes (settings, tenant)
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .computed import ComputedFieldSpec
from .fields import FieldSpec
from .invariant import InvariantSpec


class ArchetypeKind(str, Enum):
    """
    Kind of semantic archetype.

    v0.10.3: Added for settings and multi-tenancy support.
    v0.10.4: Added USER and USER_MEMBERSHIP for user management.

    CUSTOM: User-defined archetype (existing behavior)
    SETTINGS: Singleton entity with admin-only access (system-wide config)
    TENANT: Tenant root entity for multi-tenancy
    TENANT_SETTINGS: Per-tenant settings (scoped to tenant admins)
    USER: Core user entity with auth fields (email, password_hash, OAuth support)
    USER_MEMBERSHIP: User-tenant relationship with per-tenant personas
    """

    CUSTOM = "custom"
    SETTINGS = "settings"
    TENANT = "tenant"
    TENANT_SETTINGS = "tenant_settings"
    USER = "user"
    USER_MEMBERSHIP = "user_membership"


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
