"""
Date expression types for DAZZLE IR.

This module contains types for date arithmetic expressions used in
field defaults, conditions, and invariants.

Examples:
    - today + 7d (date field default)
    - now - 24h (datetime field default)
    - due_date < today + 7d (condition)
    - end_date < start_date + 30d (invariant)
"""

from __future__ import annotations  # required: DateExpr forward-references in DateArithmeticExpr

from enum import StrEnum
from typing import Annotated, Union

from pydantic import BaseModel, ConfigDict, Field

from .invariant import DurationUnit


class DateLiteralKind(StrEnum):
    """Date literal keywords."""

    TODAY = "today"  # Current date (date type)
    NOW = "now"  # Current datetime (datetime type)
    # Calendar anchors (#1800) — the first day of the current period in the
    # tenant calendar. Conditions only (filter: / where: / when:). Week is
    # the ISO week (Monday), matching date_trunc('week').
    START_OF_WEEK = "start_of_week"
    START_OF_MONTH = "start_of_month"
    START_OF_QUARTER = "start_of_quarter"
    START_OF_YEAR = "start_of_year"


#: Periods accepted by ``start_of(<period>)`` (#1800). Named periods such as
#: ``term`` are parked in DD-017.
CALENDAR_PERIODS: tuple[str, ...] = ("week", "month", "quarter", "year")


class DateLiteral(BaseModel):
    """
    A date literal: today, now, or a calendar anchor.

    Examples:
        - today - Current date
        - now - Current datetime
        - start_of(week) - Monday of the current ISO week (#1800)
    """

    kind: DateLiteralKind = Field(description="The date literal keyword")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        if self.kind.value.startswith("start_of_"):
            return f"start_of({self.kind.value.removeprefix('start_of_')})"
        return self.kind.value


class DateArithmeticOp(StrEnum):
    """Operators for date arithmetic."""

    ADD = "+"
    SUBTRACT = "-"


class DurationLiteral(BaseModel):
    """
    A duration value with unit.

    Examples:
        - 7d (7 days)
        - 24h (24 hours)
        - 30min (30 minutes)
        - 2w (2 weeks)
        - 3m (3 months)
        - 1y (1 year)
    """

    value: int = Field(description="Duration value (must be positive)")
    unit: DurationUnit = Field(description="Duration unit")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        # Compact notation
        unit_abbrev = {
            DurationUnit.MINUTES: "min",
            DurationUnit.HOURS: "h",
            DurationUnit.DAYS: "d",
            DurationUnit.WEEKS: "w",
            DurationUnit.MONTHS: "m",
            DurationUnit.YEARS: "y",
        }
        return f"{self.value}{unit_abbrev[self.unit]}"


class DateArithmeticExpr(BaseModel):
    """
    A date arithmetic expression.

    Examples:
        - today + 7d
        - now - 24h
        - start_date + 30d
    """

    left: DateExpr = Field(description="Left operand (date literal or field ref)")
    operator: DateArithmeticOp = Field(description="Arithmetic operator (+ or -)")
    right: DurationLiteral = Field(description="Duration to add/subtract")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.left} {self.operator.value} {self.right}"


# Forward reference for recursive type
# DateExpr can be: DateLiteral, DateArithmeticExpr, or a field reference (str)
DateExpr = Annotated[
    Union[DateLiteral, "DateArithmeticExpr", str],
    Field(
        description="A date expression: literal (today/now), arithmetic (today + 7d), or field ref"
    ),
]

# Rebuild model to resolve forward references
DateArithmeticExpr.model_rebuild()
