"""
Seed template types for DAZZLE IR (v0.38.0, #428).

Declarative seed templates allow entities to express formulaic,
time-dependent reference data that the framework generates on startup.

Use cases: academic years, financial years, terms, tax periods.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SeedStrategy(StrEnum):
    """Strategies for generating seed rows."""

    ROLLING_WINDOW = "rolling_window"


class SeedFieldTemplate(BaseModel):
    """A single field's template expression.

    Template strings support these variables (for rolling_window strategy):
        {y}        — start year (e.g. 2025)
        {y1}       — end year (y + 1, e.g. 2026)
        {y_short}  — last 2 digits of start year (e.g. 25)
        {y1_short} — last 2 digits of end year (e.g. 26)

    Special expression: ``y == current_year`` evaluates to true/false.
    """

    field: str
    template: str

    model_config = ConfigDict(frozen=True)


class SeedTemplateSpec(BaseModel):
    """Declarative seed template for generating reference data rows.

    Attributes:
        strategy: Generation strategy (currently only ``rolling_window``).
        window_start: Offset from current year for first generated row (e.g. -1).
        window_end: Offset from current year for last generated row (e.g. +3).
        month_anchor: Month that starts the period (default 1 = January;
            9 = September for academic years; 4 = April for UK financial years).
        match_field: Field to match on for idempotent upsert (default: first
            unique field on the entity).
        fields: Template expressions for each field.
    """

    strategy: SeedStrategy = SeedStrategy.ROLLING_WINDOW
    window_start: int = -1
    window_end: int = 3
    month_anchor: int = 1
    match_field: str | None = None
    fields: list[SeedFieldTemplate] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
