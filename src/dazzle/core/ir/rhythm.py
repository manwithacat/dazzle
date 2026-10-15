"""
Rhythm specification types for DAZZLE longitudinal UX evaluation.

Rhythms are non-Turing-complete journey maps that describe a single
persona's path through the app over temporal phases. Each phase
contains scenes — discrete actions on specific surfaces.

Structural references (persona, surface, entity, story) are validated
at link time. Semantic hints (cadence, action, expects) are free-form
strings interpreted by AI agents per domain.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation


class PhaseKind(StrEnum):
    """Temporal nature of a rhythm phase."""

    ONBOARDING = "onboarding"
    GATE = "gate"
    ACTIVE = "active"
    PERIODIC = "periodic"
    AMBIENT = "ambient"
    OFFBOARDING = "offboarding"


class SceneSpec(BaseModel):
    """A single scene — a persona action on a surface within a rhythm phase."""

    name: str = Field(..., description="Scene identifier")
    title: str | None = Field(default=None, description="Human-readable title")
    # Optional at parse time: a scene that cites a story may omit `on:` and have
    # its surface derived from the story at link time (#1559 slice 3). After a
    # successful link it is always populated (derivation failure is a link error).
    surface: str | None = Field(
        default=None, description="Surface or workspace this scene exercises"
    )
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
    cadence: str | None = Field(default=None, description="Temporal cadence hint for this phase")
    depends_on: str | None = Field(
        default=None, description="Phase name this phase depends on (must complete first)"
    )
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
# Gap analysis models
# ---------------------------------------------------------------------------


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
