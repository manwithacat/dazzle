"""Resolve DSL ``today`` / ``now`` date expressions to tenant calendar values.

Workspace filters, attention ``when:``, and aggregate ``where:`` used to
drop ``date_expr`` (``due_date < today``) and invent the unbounded
collection / whole-book KPI / never-overdue badge. ``today`` is the
tenant-timezone calendar day (#1597 C). Leftover / unknown stays
unresolved (caller does not invent ``IS NULL``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from dazzle.i18n.display_locale import calendar_today


def evaluate_date_expr(expr: Any) -> date | datetime | None:
    """Evaluate a date literal or ``today ± duration`` to a concrete value.

    Accepts IR ``DateLiteral`` / ``DateArithmeticExpr`` or their
    ``model_dump`` dicts (attention serializes conditions). Field-ref
    bases and leftover junk return ``None``.
    """
    if expr is None or expr == "":
        return None
    if isinstance(expr, dict) and expr.get("date_expr") is not None:
        return evaluate_date_expr(expr["date_expr"])
    base = _base_instant(expr)
    if base is None:
        return None
    op, amount, unit = _arithmetic(expr)
    if not op:
        return base
    delta = _duration_delta(amount, unit)
    if op in ("+", "add"):
        return base + delta
    if op in ("-", "subtract"):
        return base - delta
    return None


def date_expr_filter_value(expr: Any) -> str | None:
    """ISO bind for SQL filters (``due_date__lt`` / aggregate ValueRef)."""
    resolved = evaluate_date_expr(expr)
    if resolved is None:
        return None
    if isinstance(resolved, datetime):
        return resolved.isoformat()
    return resolved.isoformat()


def _get(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    src = obj if isinstance(obj, dict) else None
    for name in names:
        raw = src.get(name) if src is not None else getattr(obj, name, None)
        if raw is not None:
            return raw
    return None


def _token(raw: Any, default: str = "") -> str:
    if raw is None:
        return default
    return str(getattr(raw, "value", raw) or default)


def _base_instant(expr: Any) -> date | datetime | None:
    kind = _token(_get(expr, "kind")).strip().lower()
    if kind == "today":
        return calendar_today()
    if kind == "now":
        return datetime.now(UTC)
    left = _get(expr, "left")
    if left is None or isinstance(left, str):
        return None
    return evaluate_date_expr(left)


def _arithmetic(expr: Any) -> tuple[str, int, str]:
    op = _get(expr, "operator", "op")
    if op is None:
        return "", 0, "days"
    right = _get(expr, "right")
    value = _get(expr, "value") or _get(right, "value")
    unit = _get(expr, "unit") or _get(right, "unit")
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        return "", 0, "days"
    return _token(op), amount, _token(unit, "days")


def _duration_delta(value: int, unit: str) -> timedelta:
    token = (unit or "days").strip().lower()
    if token in ("minutes", "min"):
        return timedelta(minutes=value)
    if token in ("hours", "h", "hour"):
        return timedelta(hours=value)
    if token in ("weeks", "w", "week"):
        return timedelta(weeks=value)
    if token in ("months", "m", "month"):
        return timedelta(days=value * 30)
    if token in ("years", "y", "year"):
        return timedelta(days=value * 365)
    return timedelta(days=value)
