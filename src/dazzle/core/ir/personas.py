"""
Persona specification types for DAZZLE IR.

This module contains formal persona definitions. Personas represent
different user roles that can be impersonated during development
and testing.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PersonaSpec(BaseModel):
    """
    Formal persona definition.

    Represents a user role that can be impersonated during development.
    Used for persona switching, route selection, and fixture loading.

    Attributes:
        id: Unique identifier for the persona (e.g., "teacher", "student")
        label: Human-readable display name
        description: Optional description of the persona's goals and context
        goals: List of goals this persona is trying to accomplish
        proficiency_level: Technical skill level of this persona
        default_workspace: Default workspace to show for this persona
        default_route: Default route to navigate to on persona switch
        backed_by: Optional entity name that this persona is backed by.
            When set, the framework can resolve ``current_user`` to a
            specific domain entity row at runtime — enabling scope-rule
            cascading, auto-injection for ``ref <Entity>`` fields on
            create forms, and form pre-selection for the persona's own
            entity record. Added in cycle 248 (closes EX-045).
            Example: ``persona tester: backed_by: Tester``.
        link_via: The field name used to join the auth user to the
            backing entity. Defaults to ``"email"`` — meaning the
            framework looks up the backing entity row where
            ``<entity>.<link_via> == current_user.email``. Can be
            overridden to ``"id"`` or any other unique field that
            appears on both the backing entity and the auth user.
    """

    id: str
    label: str
    description: str | None = None
    goals: list[str] = Field(default_factory=list)
    proficiency_level: Literal["novice", "intermediate", "expert"] = "intermediate"
    default_workspace: str | None = None
    default_route: str | None = None
    backed_by: str | None = None  # Entity name (e.g. "Tester")
    link_via: str = "email"  # Join field (default: email)

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"Persona({self.id}: {self.label})"
