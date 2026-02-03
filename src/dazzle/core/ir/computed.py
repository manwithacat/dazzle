"""
Computed field types for DAZZLE IR.

This module contains types for computed (derived) fields that are
calculated from other fields using aggregate functions and arithmetic.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AggregateFunction(StrEnum):
    """Supported aggregate functions for computed fields."""

    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    DAYS_UNTIL = "days_until"
    DAYS_SINCE = "days_since"


class ArithmeticOperator(StrEnum):
    """Arithmetic operators for computed expressions."""

    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"


class FieldReference(BaseModel):
    """
    Reference to a field, possibly via a relation path.

    Examples:
        - FieldReference(path=["amount"]) -> amount
        - FieldReference(path=["line_items", "amount"]) -> line_items.amount
    """

    path: list[str] = Field(description="Field path (e.g., ['line_items', 'amount'])")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return ".".join(self.path)

    @property
    def is_simple(self) -> bool:
        """Check if this is a simple field (no relation traversal)."""
        return len(self.path) == 1

    @property
    def field_name(self) -> str:
        """Get the final field name."""
        return self.path[-1]

    @property
    def relation_path(self) -> list[str]:
        """Get the relation path (excluding final field)."""
        return self.path[:-1]


class AggregateCall(BaseModel):
    """
    An aggregate function call.

    Examples:
        - sum(line_items.amount)
        - count(tasks)
        - days_until(due_date)
    """

    function: AggregateFunction = Field(description="Aggregate function to apply")
    field: FieldReference = Field(description="Field to aggregate")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.function.value}({self.field})"


class ArithmeticExpr(BaseModel):
    """
    Binary arithmetic expression.

    Example: sum(items.price) * 1.2
    """

    left: ComputedExpr = Field(description="Left operand")
    operator: ArithmeticOperator = Field(description="Arithmetic operator")
    right: ComputedExpr = Field(description="Right operand")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"({self.left} {self.operator.value} {self.right})"


class LiteralValue(BaseModel):
    """A literal numeric value in a computed expression."""

    value: int | float = Field(description="The literal value")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return str(self.value)


# Union type for computed expressions
ComputedExpr = AggregateCall | FieldReference | ArithmeticExpr | LiteralValue


class ComputedFieldSpec(BaseModel):
    """
    Specification for a computed (derived) field.

    Computed fields are not stored in the database but calculated
    from other fields when the entity is retrieved.

    Examples:
        - total: computed sum(line_items.amount)
        - overdue_days: computed days_since(due_date)
        - total_with_tax: computed sum(line_items.amount) * 1.1
    """

    name: str = Field(description="Field name")
    expression: ComputedExpr = Field(description="Expression to compute the value")
    # Result type is inferred from expression:
    # - COUNT -> int
    # - SUM/AVG/MIN/MAX -> depends on field type
    # - DAYS_UNTIL/DAYS_SINCE -> int

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.name}: computed {self.expression}"

    @property
    def dependencies(self) -> set[str]:
        """
        Get all field paths this computed field depends on.

        Returns:
            Set of field path strings (e.g., {"line_items.amount", "tax_rate"})
        """
        return self._collect_dependencies(self.expression)

    def _collect_dependencies(self, expr: ComputedExpr) -> set[str]:
        """Recursively collect dependencies from expression."""
        deps: set[str] = set()

        if isinstance(expr, FieldReference):
            deps.add(str(expr))
        elif isinstance(expr, AggregateCall):
            deps.add(str(expr.field))
        elif isinstance(expr, ArithmeticExpr):
            deps.update(self._collect_dependencies(expr.left))
            deps.update(self._collect_dependencies(expr.right))
        # LiteralValue has no dependencies

        return deps


# Update forward references for recursive types
ArithmeticExpr.model_rebuild()
