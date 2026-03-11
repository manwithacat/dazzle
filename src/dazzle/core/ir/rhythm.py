"""
Rhythm specification types for DAZZLE longitudinal UX evaluation.

Rhythms are non-Turing-complete journey maps that describe a single
persona's path through the app over temporal phases. Each phase
contains scenes — discrete actions on specific surfaces.

Structural references (persona, surface, entity, story) are validated
at link time. Semantic hints (cadence, action, expects) are free-form
strings interpreted by AI agents per domain.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation


class SceneSpec(BaseModel):
    """A single scene — a persona action on a surface within a rhythm phase."""

    name: str = Field(..., description="Scene identifier")
    title: str | None = Field(default=None, description="Human-readable title")
    surface: str = Field(..., description="Surface this scene exercises")
    actions: list[str] = Field(default_factory=list, description="Action verbs")
    entity: str | None = Field(default=None, description="Entity reference")
    expects: str | None = Field(default=None, description="Expected outcome")
    story: str | None = Field(default=None, description="Link to existing story")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


class PhaseSpec(BaseModel):
    """A named phase within a rhythm — groups scenes in temporal order."""

    name: str = Field(..., description="Phase identifier")
    scenes: list[SceneSpec] = Field(default_factory=list, description="Scenes in phase")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


class RhythmSpec(BaseModel):
    """A rhythm — a longitudinal journey map for a persona through the app."""

    name: str = Field(..., description="Rhythm identifier")
    title: str | None = Field(default=None, description="Human-readable title")
    persona: str = Field(..., description="Persona this rhythm is for")
    cadence: str | None = Field(default=None, description="Temporal frequency hint")
    phases: list[PhaseSpec] = Field(default_factory=list, description="Journey phases")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
