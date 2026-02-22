"""Shared expression evaluation utilities.

Provides dotted-path resolution, simple condition evaluation for experience
flows, and typed expression evaluation for surface ``when:`` conditions.
"""

from __future__ import annotations

from typing import Any


def resolve_dotted_path(
    path: str, data: dict[str, Any], *, strip_prefix: str | None = "context"
) -> Any:
    """Resolve a dotted path like ``context.company.id`` against a data dict.

    Args:
        path: Dotted path string (e.g. ``"context.company.id"``).
        data: Dictionary to navigate.
        strip_prefix: If set, strip this leading segment from the path
            (default ``"context"`` since data keys are context-relative).

    Returns:
        The resolved value, or ``None`` if any segment is missing.
    """
    parts = path.split(".")
    if strip_prefix and parts and parts[0] == strip_prefix:
        parts = parts[1:]
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def resolve_prefill_expression(expression: str, data: dict[str, Any]) -> Any:
    """Resolve a prefill expression against state data.

    - String literal (starts/ends with ``"``): strip quotes, return string.
    - Dotted path (``context.X.Y``): navigate ``data["X"]["Y"]``.
    """
    if expression.startswith('"') and expression.endswith('"'):
        return expression[1:-1]
    return resolve_dotted_path(expression, data)


def _parse_literal(value: str) -> Any:
    """Parse a string literal into a typed Python value."""
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def evaluate_simple_condition(when_expr: str, data: dict[str, Any]) -> bool:
    """Evaluate a simple condition expression against state data.

    Supports: ``context.X.Y = value``, ``context.X.Y != value``,
    and comparison operators ``>``, ``<``, ``>=``, ``<=``.

    Returns ``True`` if the condition is met or no operator is found.
    Returns ``False`` if the left side resolves to ``None``.
    """
    for op in ("!=", ">=", "<=", "=", ">", "<"):
        if f" {op} " not in when_expr:
            continue

        left, right = when_expr.split(f" {op} ", 1)
        resolved = resolve_dotted_path(left.strip(), data)
        if resolved is None:
            return False

        rval = _parse_literal(right.strip())

        if op == "=":
            return resolved == rval
        if op == "!=":
            return resolved != rval
        if op == ">":
            return resolved > rval
        if op == "<":
            return resolved < rval
        if op == ">=":
            return resolved >= rval
        if op == "<=":
            return resolved <= rval
        break

    return True


def evaluate_when_expr(when_expr_str: str, data: dict[str, Any]) -> bool:
    """Evaluate a serialized ``when:`` expression against record data.

    Uses the typed expression parser and evaluator from the core expression
    language, so it handles all operator types, ``in``/``not in``, ``and``/``or``,
    function calls, etc.

    Args:
        when_expr_str: Serialized expression string (from ``str(Expr)``).
        data: Record dict (flat field→value mapping).

    Returns:
        ``True`` if the expression evaluates to a truthy value, or if the
        expression is empty or cannot be parsed/evaluated (fail-open: show
        the field rather than hide it).
    """
    if not when_expr_str:
        return True
    try:
        from dazzle.core.expression_lang.evaluator import evaluate
        from dazzle.core.expression_lang.parser import parse_expr

        expr = parse_expr(when_expr_str)
        result = evaluate(expr, data)
        return bool(result)
    except Exception:
        # Fail open — show the field if evaluation fails
        return True
