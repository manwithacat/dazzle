"""
Condition expression types for DAZZLE IR.

This module contains types for expressing conditions used in access control,
attention signals, filters, and other conditional logic.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from .dates import DateArithmeticExpr, DateLiteral


class ComparisonOperator(str, Enum):
    """Operators for condition expressions."""

    EQUALS = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    IN = "in"
    NOT_IN = "not in"
    IS = "is"
    IS_NOT = "is not"


class LogicalOperator(str, Enum):
    """Logical operators for combining conditions."""

    AND = "and"
    OR = "or"


class ConditionValue(BaseModel):
    """
    A value in a condition expression.

    Can be a literal (string, number, boolean, null), a list of values,
    or a date expression (v0.10.2).

    v0.10.2: Added date_expr for date arithmetic in conditions:
        - due_date < today + 7d
        - created_at > now - 24h
    """

    literal: str | int | float | bool | None = None
    values: list[str | int | float | bool] | None = None  # For 'in' operator
    # v0.10.2: Date expression support
    date_expr: DateLiteral | DateArithmeticExpr | None = None

    model_config = ConfigDict(frozen=True)

    @property
    def is_list(self) -> bool:
        """Check if this is a list value."""
        return self.values is not None

    @property
    def is_date_expr(self) -> bool:
        """Check if this is a date expression value."""
        return self.date_expr is not None


class FunctionCall(BaseModel):
    """
    A function call in a condition expression.

    Examples:
        - days_since(last_inspection_date)
        - count(observations)
    """

    name: str
    argument: str  # Field name

    model_config = ConfigDict(frozen=True)


class RoleCheck(BaseModel):
    """
    A role check in a condition expression.

    Examples:
        - role(admin)
        - role(editor)

    Used in access rules to check if user has a specific role.
    """

    role_name: str

    model_config = ConfigDict(frozen=True)


class Comparison(BaseModel):
    """
    A single comparison in a condition expression.

    Examples:
        - condition_status in [SevereStress, Dead]
        - days_since(last_inspection_date) > 30
        - steward is null
    """

    field: str | None = None  # Direct field reference
    function: FunctionCall | None = None  # Function call
    operator: ComparisonOperator
    value: ConditionValue

    model_config = ConfigDict(frozen=True)

    @property
    def left_operand(self) -> str:
        """Get the left side of the comparison as a string."""
        if self.function:
            return f"{self.function.name}({self.function.argument})"
        return self.field or ""


class ConditionExpr(BaseModel):
    """
    A condition expression that can be simple or compound.

    Examples:
        - condition_status in [SevereStress, Dead]
        - days_since(last_inspection_date) > 30 and steward is null
        - role(admin) or owner_id = current_user
    """

    comparison: Comparison | None = None  # Simple comparison condition
    role_check: RoleCheck | None = None  # Role-based condition (v0.7.0)
    left: ConditionExpr | None = None  # For compound conditions
    operator: LogicalOperator | None = None  # AND/OR
    right: ConditionExpr | None = None  # For compound conditions

    model_config = ConfigDict(frozen=True)

    @property
    def is_compound(self) -> bool:
        """Check if this is a compound (AND/OR) condition."""
        return self.operator is not None

    @property
    def is_role_check(self) -> bool:
        """Check if this is a role check condition."""
        return self.role_check is not None


def _rebuild_condition_value() -> None:
    """Rebuild ConditionValue model to resolve forward references to date types."""
    # Import here to avoid circular imports
    from .dates import DateArithmeticExpr, DateLiteral

    ConditionValue.model_rebuild(
        _types_namespace={"DateLiteral": DateLiteral, "DateArithmeticExpr": DateArithmeticExpr}
    )


# Call rebuild after module initialization
_rebuild_condition_value()
