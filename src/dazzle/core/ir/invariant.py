"""
Invariant types for DAZZLE IR.

This module contains types for entity invariants - cross-field constraints
that must always hold true for an entity to be valid.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ComparisonOperator(str, Enum):
    """Comparison operators for invariant expressions."""

    EQ = "=="
    NE = "!="
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="


class LogicalOperator(str, Enum):
    """Logical operators for combining conditions."""

    AND = "and"
    OR = "or"


class DurationUnit(str, Enum):
    """Time units for duration expressions."""

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


class InvariantFieldRef(BaseModel):
    """
    Reference to a field in an invariant expression.

    Example: end_date, user.role
    """

    path: list[str] = Field(description="Field path (e.g., ['end_date'] or ['user', 'role'])")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return ".".join(self.path)


class InvariantLiteral(BaseModel):
    """
    A literal value in an invariant expression.

    Supports numeric, string, boolean, and null literals.
    """

    value: int | float | str | bool | None = Field(description="The literal value")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        if self.value is None:
            return "null"
        if isinstance(self.value, str):
            return f'"{self.value}"'
        return str(self.value)


class DurationExpr(BaseModel):
    """
    A duration expression (e.g., 14 days, 2 hours).

    Used in comparisons like: duration <= 14 days
    """

    value: int = Field(description="Duration value")
    unit: DurationUnit = Field(description="Duration unit")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.value} {self.unit.value}"


class ComparisonExpr(BaseModel):
    """
    A comparison expression between two operands.

    Examples:
        - end_date > start_date
        - status == "active"
        - duration <= 14 days
    """

    left: InvariantExpr = Field(description="Left operand")
    operator: ComparisonOperator = Field(description="Comparison operator")
    right: InvariantExpr = Field(description="Right operand")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"({self.left} {self.operator.value} {self.right})"


class LogicalExpr(BaseModel):
    """
    A logical expression combining two conditions.

    Examples:
        - start_date < end_date and duration <= 14 days
        - status == "draft" or status == "pending"
    """

    left: InvariantExpr = Field(description="Left condition")
    operator: LogicalOperator = Field(description="Logical operator")
    right: InvariantExpr = Field(description="Right condition")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"({self.left} {self.operator.value} {self.right})"


class NotExpr(BaseModel):
    """
    A negation expression.

    Example: not is_archived
    """

    operand: InvariantExpr = Field(description="Expression to negate")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"not {self.operand}"


# Union type for invariant expressions - using forward reference string
InvariantExpr = (
    InvariantFieldRef | InvariantLiteral | DurationExpr | ComparisonExpr | LogicalExpr | NotExpr
)


class InvariantSpec(BaseModel):
    """
    Specification for an entity invariant.

    Invariants are conditions that must always hold true for an entity.
    They are validated on create and update operations.

    Examples:
        - invariant: end_date > start_date
        - invariant: quantity >= 0
        - invariant: status != "deleted" or deleted_at is not None

    v0.7.1: Added message and code for LLM cognition
        - invariant: end_date > start_date
            message: "Check-out must be after check-in"
            code: INVALID_DATE_RANGE
    """

    expression: InvariantExpr = Field(description="The invariant condition")
    message: str | None = Field(
        default=None,
        description="Custom error message when invariant is violated",
    )
    code: str | None = Field(
        default=None,
        description="Error code for API responses and i18n",
    )

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"invariant: {self.expression}"

    @property
    def dependencies(self) -> set[str]:
        """
        Get all field paths this invariant depends on.

        Returns:
            Set of field path strings (e.g., {"start_date", "end_date"})
        """
        return self._collect_dependencies(self.expression)

    def _collect_dependencies(self, expr: InvariantExpr) -> set[str]:
        """Recursively collect dependencies from expression."""
        deps: set[str] = set()

        if isinstance(expr, InvariantFieldRef):
            deps.add(str(expr))
        elif isinstance(expr, ComparisonExpr):
            deps.update(self._collect_dependencies(expr.left))
            deps.update(self._collect_dependencies(expr.right))
        elif isinstance(expr, LogicalExpr):
            deps.update(self._collect_dependencies(expr.left))
            deps.update(self._collect_dependencies(expr.right))
        elif isinstance(expr, NotExpr):
            deps.update(self._collect_dependencies(expr.operand))
        # Literals and DurationExpr have no dependencies

        return deps


# Update forward references for recursive types
ComparisonExpr.model_rebuild()
LogicalExpr.model_rebuild()
NotExpr.model_rebuild()
