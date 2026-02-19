"""
View types for DAZZLE IR.

Read-only derived/aggregate data definitions for dashboards and reports.

DSL Syntax (v0.25.0):

    view MonthlySales "Monthly Sales Summary":
      source: Order
      filter: status = completed
      group_by: [customer, month(created_at)]
      fields:
        customer: ref Customer
        month: str
        total_amount: sum(amount)
        order_count: count()
        avg_order: avg(amount)

v0.34.0 Date-range reporting:

    view WeeklySales "Weekly Sales":
      source: Order
      date_field: created_at
      time_bucket: week
      fields:
        total: sum(amount)
        count: count()
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .computed import ComputedExpr
from .conditions import ConditionExpr
from .fields import FieldType


class TimeBucket(StrEnum):
    """Time bucketing intervals for date-range reporting (v0.34.0)."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class ViewFieldSpec(BaseModel):
    """A field within a view definition."""

    name: str
    title: str | None = None
    expression: ComputedExpr | None = None
    field_type: FieldType | None = None

    model_config = ConfigDict(frozen=True)


class ViewSpec(BaseModel):
    """
    A view (read-only derived data) definition.

    Attributes:
        name: View identifier
        title: Human-readable title
        source_entity: Entity to derive data from
        filter_condition: Optional filter expression
        group_by: Fields to group results by
        fields: Derived/aggregated fields
        date_field: Field to use for date-range filtering (v0.34.0)
        time_bucket: Bucketing interval for time-series aggregation (v0.34.0)
    """

    name: str
    title: str | None = None
    source_entity: str = ""
    filter_condition: ConditionExpr | None = None
    group_by: list[str] = Field(default_factory=list)
    fields: list[ViewFieldSpec] = Field(default_factory=list)
    # v0.34.0: Date-range reporting
    date_field: str | None = None
    time_bucket: TimeBucket | None = None

    model_config = ConfigDict(frozen=True)
