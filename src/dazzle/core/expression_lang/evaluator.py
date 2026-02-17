"""
Expression evaluator for Dazzle expression language.

Evaluates expression AST nodes against a context (dict of field values).
Pure evaluation — no I/O, no side effects. Does NOT use Python's eval().
This is a safe, sandboxed tree-walking interpreter over a typed AST.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from dazzle.core.ir.expressions import (
    BinaryExpr,
    BinaryOp,
    DurationLiteral,
    Expr,
    FieldRef,
    FuncCall,
    IfExpr,
    InExpr,
    Literal,
    UnaryExpr,
    UnaryOp,
)


class ExpressionEvalError(Exception):
    """Error during expression evaluation."""


def evaluate(expr: Expr, context: dict[str, Any]) -> Any:
    """Evaluate an expression against a context dict.

    This is a safe tree-walking interpreter — it does NOT use Python's
    eval(). Only the closed set of AST node types are handled.

    Args:
        expr: Parsed expression AST.
        context: Dict of field name -> value. Nested dicts for relation paths.

    Returns:
        The computed value.

    Raises:
        ExpressionEvalError: If evaluation fails.
    """
    return _interpret(expr, context)


def _interpret(expr: Expr, ctx: dict[str, Any]) -> Any:
    """Dispatch evaluation to the appropriate handler."""
    if isinstance(expr, Literal):
        return expr.value

    if isinstance(expr, FieldRef):
        return _interpret_field_ref(expr, ctx)

    if isinstance(expr, DurationLiteral):
        return _interpret_duration(expr)

    if isinstance(expr, BinaryExpr):
        return _interpret_binary(expr, ctx)

    if isinstance(expr, UnaryExpr):
        return _interpret_unary(expr, ctx)

    if isinstance(expr, FuncCall):
        return _interpret_func_call(expr, ctx)

    if isinstance(expr, InExpr):
        return _interpret_in(expr, ctx)

    if isinstance(expr, IfExpr):
        return _interpret_if(expr, ctx)

    raise ExpressionEvalError(f"Unknown expression type: {type(expr).__name__}")


def _interpret_field_ref(expr: FieldRef, ctx: dict[str, Any]) -> Any:
    """Resolve a field reference against the context."""
    current: Any = ctx
    for segment in expr.path:
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
        elif hasattr(current, segment):
            current = getattr(current, segment)
        else:
            return None
    return current


def _interpret_duration(expr: DurationLiteral) -> timedelta:
    """Convert a duration literal to a timedelta."""
    unit_map = {
        "d": lambda v: timedelta(days=v),
        "h": lambda v: timedelta(hours=v),
        "w": lambda v: timedelta(weeks=v),
        "min": lambda v: timedelta(minutes=v),
        # Months and years are approximate
        "m": lambda v: timedelta(days=v * 30),
        "y": lambda v: timedelta(days=v * 365),
    }
    factory = unit_map.get(expr.unit)
    if factory is None:
        raise ExpressionEvalError(f"Unknown duration unit: {expr.unit}")
    return factory(expr.value)


def _interpret_binary(expr: BinaryExpr, ctx: dict[str, Any]) -> Any:
    """Evaluate a binary expression."""
    # Short-circuit for logical operators
    if expr.op == BinaryOp.AND:
        left = _interpret(expr.left, ctx)
        if not left:
            return left
        return _interpret(expr.right, ctx)

    if expr.op == BinaryOp.OR:
        left = _interpret(expr.left, ctx)
        if left:
            return left
        return _interpret(expr.right, ctx)

    left = _interpret(expr.left, ctx)
    right = _interpret(expr.right, ctx)

    # Null-safe comparisons
    if expr.op == BinaryOp.EQ:
        return left == right
    if expr.op == BinaryOp.NE:
        return left != right

    # Null propagation for arithmetic/comparison
    if left is None or right is None:
        if expr.op in (BinaryOp.LT, BinaryOp.GT, BinaryOp.LE, BinaryOp.GE):
            return False
        return None

    # Arithmetic
    if expr.op == BinaryOp.ADD:
        return _add(left, right)
    if expr.op == BinaryOp.SUB:
        return _sub(left, right)
    if expr.op == BinaryOp.MUL:
        return left * right
    if expr.op == BinaryOp.DIV:
        if right == 0:
            raise ExpressionEvalError("Division by zero")
        return left / right
    if expr.op == BinaryOp.MOD:
        if right == 0:
            raise ExpressionEvalError("Modulo by zero")
        return left % right

    # Comparison
    if expr.op == BinaryOp.LT:
        return left < right
    if expr.op == BinaryOp.GT:
        return left > right
    if expr.op == BinaryOp.LE:
        return left <= right
    if expr.op == BinaryOp.GE:
        return left >= right

    raise ExpressionEvalError(f"Unknown binary op: {expr.op}")


def _add(left: Any, right: Any) -> Any:
    """Type-aware addition supporting date + timedelta."""
    if isinstance(left, (date, datetime)) and isinstance(right, timedelta):
        return left + right
    if isinstance(left, timedelta) and isinstance(right, (date, datetime)):
        return right + left
    if isinstance(left, str) and isinstance(right, str):
        return left + right
    return left + right


def _sub(left: Any, right: Any) -> Any:
    """Type-aware subtraction supporting date - timedelta, date - date."""
    if isinstance(left, (date, datetime)) and isinstance(right, timedelta):
        return left - right
    if isinstance(left, (date, datetime)) and isinstance(right, (date, datetime)):
        return left - right
    return left - right


def _interpret_unary(expr: UnaryExpr, ctx: dict[str, Any]) -> Any:
    """Evaluate a unary expression."""
    val = _interpret(expr.operand, ctx)
    if expr.op == UnaryOp.NOT:
        return not val
    if expr.op == UnaryOp.NEG:
        if val is None:
            return None
        return -val
    raise ExpressionEvalError(f"Unknown unary op: {expr.op}")


def _interpret_func_call(expr: FuncCall, ctx: dict[str, Any]) -> Any:
    """Evaluate a built-in function call (closed set, no user-defined functions)."""
    name = expr.name

    # Synthetic list function from parser
    if name == "__list__":
        return [_interpret(a, ctx) for a in expr.args]

    # Date functions
    if name == "today":
        return date.today()
    if name == "now":
        return datetime.now()

    if name == "days_until":
        if len(expr.args) != 1:
            raise ExpressionEvalError("days_until() takes exactly 1 argument")
        target = _interpret(expr.args[0], ctx)
        if target is None:
            return None
        today = date.today()
        if isinstance(target, datetime):
            target = target.date()
        if isinstance(target, date):
            return (target - today).days
        raise ExpressionEvalError(f"days_until() requires a date, got {type(target).__name__}")

    if name == "days_since":
        if len(expr.args) != 1:
            raise ExpressionEvalError("days_since() takes exactly 1 argument")
        target = _interpret(expr.args[0], ctx)
        if target is None:
            return None
        today = date.today()
        if isinstance(target, datetime):
            target = target.date()
        if isinstance(target, date):
            return (today - target).days
        raise ExpressionEvalError(f"days_since() requires a date, got {type(target).__name__}")

    # String functions
    if name == "concat":
        parts = [_interpret(a, ctx) for a in expr.args]
        return "".join(str(p) for p in parts if p is not None)

    if name == "len":
        if len(expr.args) != 1:
            raise ExpressionEvalError("len() takes exactly 1 argument")
        val = _interpret(expr.args[0], ctx)
        if val is None:
            return 0
        return len(val)

    # Math functions
    if name == "abs":
        if len(expr.args) != 1:
            raise ExpressionEvalError("abs() takes exactly 1 argument")
        val = _interpret(expr.args[0], ctx)
        if val is None:
            return None
        return abs(val)

    if name == "min":
        vals = [_interpret(a, ctx) for a in expr.args]
        vals = [v for v in vals if v is not None]
        return min(vals) if vals else None

    if name == "max":
        vals = [_interpret(a, ctx) for a in expr.args]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None

    if name == "round":
        if not expr.args:
            raise ExpressionEvalError("round() takes 1-2 arguments")
        val = _interpret(expr.args[0], ctx)
        if val is None:
            return None
        ndigits = int(_interpret(expr.args[1], ctx)) if len(expr.args) > 1 else 0
        return round(val, ndigits)

    # Coalesce (first non-null)
    if name == "coalesce":
        for arg in expr.args:
            val = _interpret(arg, ctx)
            if val is not None:
                return val
        return None

    raise ExpressionEvalError(f"Unknown function: {name}()")


def _interpret_in(expr: InExpr, ctx: dict[str, Any]) -> bool:
    """Evaluate an 'in' / 'not in' expression."""
    val = _interpret(expr.value, ctx)
    items = [_interpret(item, ctx) for item in expr.items]
    result = val in items
    return not result if expr.negated else result


def _interpret_if(expr: IfExpr, ctx: dict[str, Any]) -> Any:
    """Evaluate an if/elif/else expression."""
    if _interpret(expr.condition, ctx):
        return _interpret(expr.then_expr, ctx)

    for cond, val in expr.elif_branches:
        if _interpret(cond, ctx):
            return _interpret(val, ctx)

    return _interpret(expr.else_expr, ctx)
