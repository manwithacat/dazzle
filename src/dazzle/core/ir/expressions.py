"""
Unified expression types for DAZZLE IR.

This module defines a typed expression AST that subsumes the ad-hoc
expression systems in computed.py, conditions.py, and invariant.py.

Supports:
- Arithmetic: +, -, *, /, %
- Comparison: ==, !=, <, >, <=, >=
- Logic: and, or, not
- Field references: amount, contact.name, self->contact->aml_status
- Function calls: today(), days_until(due_date), count(Task where status == "open")
- Conditionals: if/elif/else
- Membership: x in [a, b, c]
- Duration literals: 7d, 9m, 1y
- Null checks: x is null, x is not null
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Expression type system
# ---------------------------------------------------------------------------


class ExprType(StrEnum):
    """Types that expressions can evaluate to."""

    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"
    DATE = "date"
    DATETIME = "datetime"
    MONEY = "money"
    DURATION = "duration"
    NULL = "null"
    ANY = "any"


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


class BinaryOp(StrEnum):
    """Binary operators for expressions."""

    # Arithmetic
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    MOD = "%"
    # Comparison
    EQ = "=="
    NE = "!="
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    # Logical
    AND = "and"
    OR = "or"


class UnaryOp(StrEnum):
    """Unary operators for expressions."""

    NEG = "-"
    NOT = "not"


# ---------------------------------------------------------------------------
# AST node types
# ---------------------------------------------------------------------------


class Literal(BaseModel):
    """A literal value: int, float, str, bool, or None (null)."""

    value: int | float | str | bool | None = Field(description="The literal value")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        if self.value is None:
            return "null"
        if isinstance(self.value, str):
            return f'"{self.value}"'
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        return str(self.value)


class FieldRef(BaseModel):
    """
    Reference to a field, possibly through relations.

    Examples:
        - FieldRef(path=["amount"]) → amount
        - FieldRef(path=["contact", "name"]) → contact.name
        - FieldRef(path=["self", "contact", "aml_status"]) → self->contact->aml_status
    """

    path: list[str] = Field(description="Field path segments")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return ".".join(self.path)

    @property
    def is_simple(self) -> bool:
        """Single field, no relation traversal."""
        return len(self.path) == 1

    @property
    def field_name(self) -> str:
        """The final field name."""
        return self.path[-1]


class DurationLiteral(BaseModel):
    """
    A duration literal: 7d, 9m, 1y, 24h, 2w.

    Units: d=days, h=hours, m=months, y=years, w=weeks, min=minutes.
    """

    value: int = Field(description="Numeric value")
    unit: str = Field(description="Duration unit (d, h, m, y, w, min)")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.value}{self.unit}"


class BinaryExpr(BaseModel):
    """Binary operation: left op right."""

    op: BinaryOp
    left: Expr
    right: Expr

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"({self.left} {self.op.value} {self.right})"


class UnaryExpr(BaseModel):
    """Unary operation: op operand."""

    op: UnaryOp
    operand: Expr

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        if self.op == UnaryOp.NOT:
            return f"not {self.operand}"
        return f"-{self.operand}"


class FuncCall(BaseModel):
    """
    Function call: name(arg1, arg2, ...).

    Built-in functions:
    - Date: today(), now(), days_until(x), days_since(x)
    - Aggregate: count(Entity where ...), sum(Entity.field where ...)
    - String: concat(a, b), format_date(x, pattern)
    """

    name: str = Field(description="Function name")
    args: list[Expr] = Field(default_factory=list, description="Arguments")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        args_str = ", ".join(str(a) for a in self.args)
        return f"{self.name}({args_str})"


class InExpr(BaseModel):
    """
    Membership test: value in [a, b, c] or value not in [a, b, c].
    """

    value: Expr = Field(description="Value to test")
    items: list[Expr] = Field(description="Items to check against")
    negated: bool = Field(default=False, description="True for 'not in'")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        items_str = ", ".join(str(i) for i in self.items)
        op = "not in" if self.negated else "in"
        return f"({self.value} {op} [{items_str}])"


class IfExpr(BaseModel):
    """
    Conditional expression: if cond: val elif cond: val else: val.
    """

    condition: Expr = Field(description="If condition")
    then_expr: Expr = Field(description="Value when condition is true")
    elif_branches: list[tuple[Expr, Expr]] = Field(
        default_factory=list, description="(condition, value) pairs"
    )
    else_expr: Expr = Field(description="Value when all conditions are false")

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        parts = [f"if {self.condition}: {self.then_expr}"]
        for cond, val in self.elif_branches:
            parts.append(f"elif {cond}: {val}")
        parts.append(f"else: {self.else_expr}")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Union type
# ---------------------------------------------------------------------------

Expr = Literal | FieldRef | DurationLiteral | BinaryExpr | UnaryExpr | FuncCall | InExpr | IfExpr

# Rebuild models for recursive forward references
BinaryExpr.model_rebuild()
UnaryExpr.model_rebuild()
FuncCall.model_rebuild()
InExpr.model_rebuild()
IfExpr.model_rebuild()
