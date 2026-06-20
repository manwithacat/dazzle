"""Transitional ConditionExpr → legacy where-clause stringifier.

Per ADR-0024, the top-level aggregate machinery now consumes typed
:class:`AggregateRef` end-to-end. What remains string-typed is the
``where`` argument to the internal ``_fetch_count_metric`` /
``_fetch_scalar_metric`` fetchers — they call into
``parse_aggregate_where`` which produces a ``ScopePredicate`` for the
SQL compiler. Slice 2 retires that string boundary by folding
``parse_aggregate_where`` into the main predicate parser; until then
this module bridges ``ConditionExpr → string`` at the fetcher boundary.

Lives under :mod:`dazzle.core.ir` rather than ``back/runtime`` because
multiple layers (back/runtime fetchers, ui/runtime card builders) need
to call it, and ``ui/`` is forbidden from importing from ``back/`` by
the layering invariant (import-linter contracts; ``test_import_contracts.py``).
"""

from __future__ import annotations

from .conditions import ConditionExpr


def condition_expr_to_legacy_where(expr: ConditionExpr | None) -> str | None:
    """Render a :class:`ConditionExpr` back to the legacy where-clause
    string form that ``parse_aggregate_where`` accepts.

    Returns ``None`` for ``None`` input. Compound conditions render with
    ``and`` / ``or`` between operands. The output matches the same shape
    a DSL author would write — round-trips through ``parse_aggregate_where``.

    **Scope:** only the comparison forms the aggregate where-clause
    grammar supported pre-migration (``field = value``, ``field in [...]``,
    AND/OR compositions). Function calls, role checks, grant checks, and
    via-conditions raise ``ValueError`` — they have no legacy string
    representation and were never accepted by the regex grammar.
    """
    if expr is None:
        return None

    if expr.is_compound:
        assert expr.left is not None and expr.right is not None
        left = condition_expr_to_legacy_where(expr.left)
        right = condition_expr_to_legacy_where(expr.right)
        op = "and" if expr.operator and expr.operator.value == "and" else "or"
        return f"{left} {op} {right}"

    cmp = expr.comparison
    if cmp is None:
        raise ValueError(
            "ConditionExpr without a comparison cannot be stringified for "
            "legacy aggregate where-clauses (role/grant/via checks have no "
            "legacy string form)"
        )

    field = cmp.field
    op = cmp.operator.value
    val = cmp.value

    if val.is_list and val.values is not None:
        items = ", ".join(_render_literal(v) for v in val.values)
        return f"{field} {op} [{items}]"

    if val.is_date_expr:
        raise ValueError(
            f"date expressions in aggregate where-clauses require the typed "
            f"runtime path (Slice 1f); {field!r} uses a date-arith RHS"
        )

    return f"{field} {op} {_render_literal(val.literal)}"


def _render_literal(value: object) -> str:
    """Render a literal RHS for the legacy string form.

    Booleans render lowercase (``true`` / ``false``) to match the
    aggregate where-clause grammar's expectations. ``None`` renders as
    ``null``. Other types use ``str()``.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
