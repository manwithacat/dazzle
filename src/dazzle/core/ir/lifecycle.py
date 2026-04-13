"""IR models for entity lifecycle declarations (ADR-0020).

Supports the fitness methodology's progress_evaluator by providing:
- Ordered states (progress direction is well-defined)
- Evidence predicates per transition (distinguishes motion from work)
"""

from pydantic import BaseModel, ConfigDict, Field


class LifecycleStateSpec(BaseModel):
    """One named state in an entity lifecycle, with a progress order."""

    name: str = Field(..., description="State name (matches an enum value on the entity)")
    order: int = Field(..., ge=0, description="Progress order (0 = earliest)")

    model_config = ConfigDict(frozen=True)


class LifecycleTransitionSpec(BaseModel):
    """One allowed transition in an entity lifecycle."""

    from_state: str = Field(..., description="Source state name")
    to_state: str = Field(..., description="Destination state name")
    evidence: str | None = Field(
        default=None,
        description=(
            "Boolean predicate over entity fields that must hold for this transition "
            "to count as valid progress. Uses the scope-rule predicate algebra syntax. "
            "When None, the transition is always valid (no evidence required)."
        ),
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Persona roles authorized to perform this transition",
    )

    model_config = ConfigDict(frozen=True)


class LifecycleSpec(BaseModel):
    """Entity lifecycle declaration (ADR-0020).

    Attached to an EntitySpec via its `lifecycle` field. Consumed by the
    fitness methodology's progress_evaluator to distinguish motion from work.
    """

    status_field: str = Field(
        ...,
        description="Name of the entity's enum field that holds the current state",
    )
    states: list[LifecycleStateSpec] = Field(
        ...,
        min_length=1,
        description="Ordered states. `order` values must form a total order.",
    )
    transitions: list[LifecycleTransitionSpec] = Field(
        default_factory=list,
        description="Allowed transitions between states",
    )

    model_config = ConfigDict(frozen=True)
