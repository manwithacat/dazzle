"""
Persona specification types for DAZZLE IR.

This module contains formal persona definitions for the Dazzle Bar
developer overlay. Personas represent different user roles that can
be impersonated during development and testing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PersonaSpec(BaseModel):
    """
    Formal persona definition for Dazzle Bar.

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
    """

    id: str
    label: str
    description: str | None = None
    goals: list[str] = Field(default_factory=list)
    proficiency_level: Literal["novice", "intermediate", "expert"] = "intermediate"
    default_workspace: str | None = None
    default_route: str | None = None

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"Persona({self.id}: {self.label})"
