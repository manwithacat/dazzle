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

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation


class PhaseKind(StrEnum):
    """Temporal nature of a rhythm phase."""

    ONBOARDING = "onboarding"
    ACTIVE = "active"
    PERIODIC = "periodic"
    AMBIENT = "ambient"
    OFFBOARDING = "offboarding"


class SceneSpec(BaseModel):
    """A single scene — a persona action on a surface within a rhythm phase."""

    name: str = Field(..., description="Scene identifier")
    title: str | None = Field(default=None, description="Human-readable title")
    surface: str = Field(..., description="Surface or workspace this scene exercises")
    actions: list[str] = Field(default_factory=list, description="Action verbs")
    entity: str | None = Field(default=None, description="Entity reference")
    expects: str | None = Field(default=None, description="Expected outcome")
    story: str | None = Field(default=None, description="Link to existing story")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


class PhaseSpec(BaseModel):
    """A named phase within a rhythm — groups scenes in temporal order."""

    name: str = Field(..., description="Phase identifier")
    kind: PhaseKind | None = Field(default=None, description="Phase kind hint")
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


# ---------------------------------------------------------------------------
# Evaluation output models
# ---------------------------------------------------------------------------


class SceneDimensionScore(BaseModel):
    """Score for a single evaluation dimension of a scene."""

    dimension: Literal["arrival", "orientation", "action", "completion", "confidence"]
    score: Literal["pass", "partial", "fail", "skip"]
    evidence: str = Field(..., description="What the agent observed")
    root_cause: str | None = Field(default=None, description="Only on partial/fail")

    model_config = ConfigDict(frozen=True)


class SceneEvaluation(BaseModel):
    """Agent-produced evaluation of a scene across five dimensions."""

    scene_name: str
    phase_name: str
    dimensions: list[SceneDimensionScore]
    gap_type: Literal["capability", "surface", "workflow", "feedback", "none"]
    story_ref: str | None = None

    model_config = ConfigDict(frozen=True)


class Gap(BaseModel):
    """A single gap identified by analysis."""

    kind: Literal[
        "capability",
        "surface",
        "workflow",
        "feedback",
        "ambient",
        "unmapped",
        "orphan",
        "unscored",
    ]
    severity: Literal["blocking", "degraded", "advisory"]
    scene: str | None = None
    phase: str | None = None
    rhythm: str
    persona: str
    story_ref: str | None = None
    surface_ref: str | None = None
    description: str

    model_config = ConfigDict(frozen=True)


class GapsSummary(BaseModel):
    """Aggregate gap counts."""

    total: int
    by_kind: dict[str, int]
    by_severity: dict[str, int]
    by_persona: dict[str, int]

    model_config = ConfigDict(frozen=True)


class GapsReport(BaseModel):
    """Full gaps analysis output."""

    gaps: list[Gap]
    summary: GapsSummary
    roadmap_order: list[Gap]

    model_config = ConfigDict(frozen=True)


class LifecycleStep(BaseModel):
    """Status of one step in the operating model lifecycle."""

    step: int
    name: str
    status: Literal["complete", "partial", "not_started"]
    evidence: str
    suggestions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class LifecycleReport(BaseModel):
    """Full lifecycle status report."""

    steps: list[LifecycleStep]
    current_focus: str
    maturity: Literal["new_domain", "building", "evaluating", "mature"]

    model_config = ConfigDict(frozen=True)
