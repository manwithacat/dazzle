"""IR model for the per-entity `fitness:` block.

Used by the Agent-Led Fitness methodology. The `repr_fields` list is the
compact projection used by `FitnessDiff.RowChange` when recording row
changes — it should capture domain-essential fields (status, FK links,
lifecycle timestamps), not UI-optimised columns.

v1 ships this as a lint warning when missing; v1.1 will make it fatal.
"""

from pydantic import BaseModel, ConfigDict, Field


class FitnessSpec(BaseModel):
    """Per-entity fitness configuration.

    Controls how this entity is represented in fitness evaluation.
    """

    repr_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True, extra="forbid")
