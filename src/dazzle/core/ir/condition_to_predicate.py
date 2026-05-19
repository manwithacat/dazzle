"""Translate :class:`ConditionExpr` to :class:`ScopePredicate`.

The aggregate-runtime fetchers compile their ``where:`` clause to SQL
via :func:`compile_predicate`, which takes :class:`ScopePredicate`.
Pre-ADR-0024 these clauses arrived as strings and were parsed via
``parse_aggregate_where``; per Slice 2 of the migration the where-clause
arrives as a typed :class:`ConditionExpr` (parsed at DSL-parse time
through the main condition parser) and is translated to the predicate
algebra here.

The translation is mechanical: ConditionExpr's three comparison shapes
(field-vs-literal, field-vs-list, compound AND/OR) map directly to the
corresponding ``ScopePredicate`` nodes. Roles, grants, and via-conditions
inside a ConditionExpr are NOT supported in aggregate where-clauses —
they don't appear in the regex-era grammar and have no defined
SQL-compilation path for the aggregate fetchers.
"""

from __future__ import annotations

from .conditions import ConditionExpr, LogicalOperator
from .predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    ScopePredicate,
    Tautology,
    ValueRef,
)


def condition_expr_to_scope_predicate(expr: ConditionExpr | None) -> ScopePredicate:
    """Translate a :class:`ConditionExpr` to a :class:`ScopePredicate`
    suitable for :func:`compile_predicate`.

    Returns a :class:`Tautology` for ``None`` input — matches the
    "no where-clause" path through the aggregate runtime.

    Raises ``ValueError`` when the input contains a role check, grant
    check, or via condition — those aren't part of the aggregate
    where-clause grammar.
    """
    if expr is None:
        return Tautology()

    if expr.is_compound:
        assert expr.left is not None and expr.right is not None
        left = condition_expr_to_scope_predicate(expr.left)
        right = condition_expr_to_scope_predicate(expr.right)
        if expr.operator is LogicalOperator.AND:
            return BoolComposite.make(BoolOp.AND, [left, right])
        return BoolComposite.make(BoolOp.OR, [left, right])

    if expr.role_check is not None:
        raise ValueError(
            "role checks are not valid in aggregate where-clauses (no SQL compilation path)"
        )
    if expr.grant_check is not None:
        raise ValueError(
            "grant checks are not valid in aggregate where-clauses (no SQL compilation path)"
        )
    if expr.via_condition is not None:
        raise ValueError(
            "via conditions are not valid in aggregate where-clauses "
            "(use the cohort_strip primary_aggregate `via:` field instead)"
        )

    cmp = expr.comparison
    if cmp is None or cmp.field is None:
        # Empty ConditionExpr (or function-call comparison with no
        # field) — treat as Tautology, matching ``parse_aggregate_where``
        # for empty / whitespace input.
        return Tautology()

    field_name: str = cmp.field
    op = _operator_to_comp_op(cmp.operator.value)
    val = cmp.value

    if val.is_list and val.values is not None:
        # IN / NOT IN against a list of literals. ScopePredicate's
        # ColumnCheck stores a single ValueRef, so a multi-value list
        # expands to an OR-composite of individual ColumnChecks —
        # matches parse_aggregate_where's behaviour.
        return BoolComposite.make(
            BoolOp.OR,
            [ColumnCheck(field=field_name, op=op, value=ValueRef(literal=v)) for v in val.values],
        )

    if val.is_date_expr:
        # Date arithmetic on aggregate where-clauses wasn't supported
        # by the regex grammar either; defer to a future slice when
        # consumers need it.
        raise ValueError(
            f"date expressions in aggregate where-clauses are not yet "
            f"supported by the typed runtime path; field {field_name!r}"
        )

    if val.literal is None:
        return ColumnCheck(field=field_name, op=op, value=ValueRef(literal_null=True))

    return ColumnCheck(field=field_name, op=op, value=ValueRef(literal=val.literal))


def _operator_to_comp_op(op_str: str) -> CompOp:
    """Map ``ComparisonOperator`` string values to ``CompOp`` enum values.

    Both enums use the same string surface (``"="``, ``"!="``, ``"in"``,
    etc.) so the lookup is a direct enum cast.
    """
    return CompOp(op_str)
