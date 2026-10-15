"""
Computed field types for DAZZLE IR.

This module contains types for computed (derived) fields that are
calculated from other fields using aggregate functions and arithmetic.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from .expressions import FieldPath, InfixExpr, expr_field_dependencies

if TYPE_CHECKING:
    from .expressions import Expr


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


class FieldReference(FieldPath, BaseModel):
    """
    Reference to a field, possibly via a relation path.

    Examples:
        - FieldReference(path=["amount"]) -> amount
        - FieldReference(path=["line_items", "amount"]) -> line_items.amount
    """

    path: list[str] = Field(description="Field path (e.g., ['line_items', 'amount'])")

    model_config = ConfigDict(frozen=True)

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


class ArithmeticExpr(InfixExpr, BaseModel):
    """
    Binary arithmetic expression.

    Example: sum(items.price) * 1.2
    """

    left: ComputedExpr = Field(description="Left operand")
    operator: ArithmeticOperator = Field(description="Arithmetic operator")
    right: ComputedExpr = Field(description="Right operand")

    model_config = ConfigDict(frozen=True)


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

    v0.30.0: computed_expr uses unified Expr type from expression_lang.
        When present, the evaluator prefers computed_expr over the legacy
        expression field.
    """

    name: str = Field(description="Field name")
    expression: ComputedExpr | None = Field(
        default=None, description="Legacy expression to compute the value"
    )
    computed_expr: Expr | None = Field(
        default=None, description="Typed expression (preferred over legacy expression)"
    )

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        expr = self.computed_expr if self.computed_expr is not None else self.expression
        return f"{self.name}: computed {expr}"

    @property
    def dependencies(self) -> set[str]:
        """
        Get all field paths this computed field depends on.

        Returns:
            Set of field path strings (e.g., {"line_items.amount", "tax_rate"})
        """
        if self.computed_expr is not None:
            return expr_field_dependencies(self.computed_expr)
        if self.expression is not None:
            return self._collect_dependencies(self.expression)
        return set()

    def _collect_dependencies(self, expr: ComputedExpr) -> set[str]:
        """Recursively collect dependencies from legacy expression."""
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


def _rebuild_computed_field_spec() -> None:
    """Rebuild ComputedFieldSpec to resolve forward reference to Expr."""
    from .expressions import Expr

    ComputedFieldSpec.model_rebuild(_types_namespace={"Expr": Expr})


_rebuild_computed_field_spec()
