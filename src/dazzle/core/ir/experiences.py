"""
Experience types for DAZZLE IR.

This module contains experience flow specifications including
steps, transitions, and orchestrated user journeys.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation
from .surfaces import BusinessPriority, SurfaceAccessSpec


class StepKind(StrEnum):
    """Types of steps in an experience."""

    SURFACE = "surface"
    PROCESS = "process"
    INTEGRATION = "integration"


class TransitionEvent(StrEnum):
    """Commonly used transition events (for documentation/autocomplete)."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCEL = "cancel"
    CONTINUE = "continue"
    BACK = "back"
    APPROVE = "approve"
    REJECT = "reject"
    SKIP = "skip"


class StepTransition(BaseModel):
    """
    Transition from one step to another.

    Attributes:
        event: Event name that triggers transition (any string)
        next_step: Name of the next step
    """

    event: str  # Arbitrary event names supported
    next_step: str

    model_config = ConfigDict(frozen=True)


class ExperienceStep(BaseModel):
    """
    Single step in an experience flow.

    Attributes:
        name: Step identifier
        kind: Type of step
        surface: Surface name (if kind=surface)
        integration: Integration name (if kind=integration)
        action: Action name (if kind=integration)
        transitions: List of transitions to other steps
        access: Optional step-level access control (overrides experience default)
    """

    name: str
    kind: StepKind
    surface: str | None = None
    integration: str | None = None
    action: str | None = None
    transitions: list[StepTransition] = Field(default_factory=list)
    access: SurfaceAccessSpec | None = None

    model_config = ConfigDict(frozen=True)


class ExperienceSpec(BaseModel):
    """
    Specification for an orchestrated experience (flow).

    Experiences define multi-step user journeys.

    Attributes:
        name: Experience identifier
        title: Human-readable title
        start_step: Name of the starting step
        steps: List of steps in this experience
        access: Optional experience-level default access control
    """

    name: str
    title: str | None = None
    start_step: str
    steps: list[ExperienceStep] = Field(default_factory=list)
    access: SurfaceAccessSpec | None = None
    priority: BusinessPriority = BusinessPriority.MEDIUM
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)

    def get_step(self, name: str) -> ExperienceStep | None:
        """Get step by name."""
        for step in self.steps:
            if step.name == name:
                return step
        return None
