"""
Type inference and checking for Dazzle expression language.

Infers expression result types from field type context and validates
type compatibility of operations at specification time (not runtime).
"""

from __future__ import annotations

from dazzle.core.ir.expressions import (
    BinaryExpr,
    BinaryOp,
    DurationLiteral,
    Expr,
    ExprType,
    FieldRef,
    FuncCall,
    IfExpr,
    InExpr,
    Literal,
    UnaryExpr,
    UnaryOp,
)


class ExpressionTypeError(Exception):
    """Type error in an expression."""


# Type context maps field paths to their types
FieldTypeContext = dict[str, ExprType]


def infer_type(
    expr: Expr,
    field_types: FieldTypeContext | None = None,
) -> ExprType:
    """Infer the result type of an expression.

    Args:
        expr: Expression AST node.
        field_types: Optional mapping of field path -> ExprType.
            If not provided, field references return ANY.

    Returns:
        The inferred ExprType.

    Raises:
        ExpressionTypeError: If types are incompatible.
    """
    ctx = field_types or {}
    return _infer(expr, ctx)


def _infer(expr: Expr, ctx: FieldTypeContext) -> ExprType:
    """Dispatch type inference."""
    if isinstance(expr, Literal):
        return _infer_literal(expr)

    if isinstance(expr, FieldRef):
        path = ".".join(expr.path)
        return ctx.get(path, ExprType.ANY)

    if isinstance(expr, DurationLiteral):
        return ExprType.DURATION

    if isinstance(expr, BinaryExpr):
        return _infer_binary(expr, ctx)

    if isinstance(expr, UnaryExpr):
        return _infer_unary(expr, ctx)

    if isinstance(expr, FuncCall):
        return _infer_func(expr, ctx)

    if isinstance(expr, InExpr):
        return ExprType.BOOL

    if isinstance(expr, IfExpr):
        return _infer_if(expr, ctx)

    return ExprType.ANY


def _infer_literal(expr: Literal) -> ExprType:
    """Infer type of a literal."""
    if expr.value is None:
        return ExprType.NULL
    if isinstance(expr.value, bool):
        return ExprType.BOOL
    if isinstance(expr.value, int):
        return ExprType.INT
    if isinstance(expr.value, float):
        return ExprType.FLOAT
    if isinstance(expr.value, str):
        return ExprType.STR
    return ExprType.ANY


_ARITHMETIC_OPS = {BinaryOp.ADD, BinaryOp.SUB, BinaryOp.MUL, BinaryOp.DIV, BinaryOp.MOD}
_COMPARISON_OPS = {BinaryOp.EQ, BinaryOp.NE, BinaryOp.LT, BinaryOp.GT, BinaryOp.LE, BinaryOp.GE}
_LOGICAL_OPS = {BinaryOp.AND, BinaryOp.OR}

# Which types support arithmetic
_NUMERIC_TYPES = {ExprType.INT, ExprType.FLOAT, ExprType.MONEY}


def _infer_binary(expr: BinaryExpr, ctx: FieldTypeContext) -> ExprType:
    """Infer result type of a binary expression."""
    if expr.op in _COMPARISON_OPS:
        return ExprType.BOOL

    if expr.op in _LOGICAL_OPS:
        return ExprType.BOOL

    # Arithmetic
    left_t = _infer(expr.left, ctx)
    right_t = _infer(expr.right, ctx)

    # ANY propagates
    if left_t == ExprType.ANY or right_t == ExprType.ANY:
        return ExprType.ANY

    # Date + Duration -> Date
    if expr.op == BinaryOp.ADD:
        if left_t == ExprType.DATE and right_t == ExprType.DURATION:
            return ExprType.DATE
        if left_t == ExprType.DATETIME and right_t == ExprType.DURATION:
            return ExprType.DATETIME
        if left_t == ExprType.DURATION and right_t in (ExprType.DATE, ExprType.DATETIME):
            return right_t

    # Date - Duration -> Date; Date - Date -> Duration
    if expr.op == BinaryOp.SUB:
        if left_t == ExprType.DATE and right_t == ExprType.DURATION:
            return ExprType.DATE
        if left_t == ExprType.DATETIME and right_t == ExprType.DURATION:
            return ExprType.DATETIME
        if left_t in (ExprType.DATE, ExprType.DATETIME) and right_t in (
            ExprType.DATE,
            ExprType.DATETIME,
        ):
            return ExprType.DURATION

    # String + String -> String
    if expr.op == BinaryOp.ADD and left_t == ExprType.STR and right_t == ExprType.STR:
        return ExprType.STR

    # Numeric arithmetic
    if left_t in _NUMERIC_TYPES and right_t in _NUMERIC_TYPES:
        # Money operations
        if left_t == ExprType.MONEY or right_t == ExprType.MONEY:
            if expr.op in (BinaryOp.ADD, BinaryOp.SUB):
                return ExprType.MONEY
            if expr.op in (BinaryOp.MUL, BinaryOp.DIV):
                # money * scalar or money / scalar -> money
                return ExprType.MONEY

        # Float wins over int
        if ExprType.FLOAT in (left_t, right_t):
            return ExprType.FLOAT
        if expr.op == BinaryOp.DIV:
            return ExprType.FLOAT
        return ExprType.INT

    return ExprType.ANY


def _infer_unary(expr: UnaryExpr, ctx: FieldTypeContext) -> ExprType:
    """Infer result type of a unary expression."""
    if expr.op == UnaryOp.NOT:
        return ExprType.BOOL
    # Negation preserves type
    return _infer(expr.operand, ctx)


# Return types for built-in functions
_FUNC_RETURN_TYPES: dict[str, ExprType] = {
    "today": ExprType.DATE,
    "now": ExprType.DATETIME,
    "days_until": ExprType.INT,
    "days_since": ExprType.INT,
    "concat": ExprType.STR,
    "len": ExprType.INT,
    "abs": ExprType.ANY,  # Same as input
    "round": ExprType.ANY,  # Same as input
    "coalesce": ExprType.ANY,  # Same as first non-null
    "__list__": ExprType.ANY,
}


def _infer_func(expr: FuncCall, ctx: FieldTypeContext) -> ExprType:
    """Infer result type of a function call."""
    result = _FUNC_RETURN_TYPES.get(expr.name)
    if result is not None:
        # For abs/round, try to return the operand type
        if expr.name in ("abs", "round") and expr.args:
            operand_type = _infer(expr.args[0], ctx)
            if operand_type in _NUMERIC_TYPES:
                return operand_type
        return result

    # min/max return the type of their arguments
    if expr.name in ("min", "max") and expr.args:
        return _infer(expr.args[0], ctx)

    return ExprType.ANY


def _infer_if(expr: IfExpr, ctx: FieldTypeContext) -> ExprType:
    """Infer result type of a conditional — type of then branch."""
    return _infer(expr.then_expr, ctx)
