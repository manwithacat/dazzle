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
    check, via condition, or a dotted (FK-path) field — those aren't part
    of the aggregate where-clause grammar and have no SQL-compilation path
    here. FK-path traversal belongs to the RBAC scope path
    (``build_scope_predicate`` → ``PathCheck``), not aggregate where-clauses.
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

    if "." in field_name:
        # Dotted (FK-path) fields have no compilation path here: this
        # builder emits a flat ColumnCheck, which compile_predicate would
        # render as a quoted compound identifier (e.g. "E"."a.b") — invalid
        # SQL, silently. FK-path traversal is the RBAC scope path's job
        # (build_scope_predicate → PathCheck → compile_predicate nested
        # join), not the aggregate where-clause grammar's. Fail loud rather
        # than emit broken SQL (#1334). Mirrors the role/grant/via rejects.
        raise ValueError(
            f"dotted field path {field_name!r} is not supported in aggregate "
            "where-clauses (no FK-join compilation path); use a direct column"
        )

    op = _operator_to_comp_op(cmp.operator.value)
    val = cmp.value

    if val.is_list and val.values is not None:
        # IN / NOT IN against a list of literals. ScopePredicate's
        # ColumnCheck stores a single ValueRef, so a multi-value list
        # expands to a boolean composite of per-element checks. Each
        # element compares against ONE literal, so it must use `=` / `!=`
        # — NOT the list operator. Keeping `IN`/`NOT IN` here compiled to
        # `col IN %s` with a scalar bind: invalid SQL that the count
        # fetcher swallowed, silently returning 0 (#1472). De Morgan:
        #   `x in [a, b]`     → (x = a) OR  (x = b)
        #   `x not in [a, b]` → (x != a) AND (x != b)
        is_not_in = op is CompOp.NOT_IN
        elem_op = CompOp.NEQ if is_not_in else CompOp.EQ
        bool_op = BoolOp.AND if is_not_in else BoolOp.OR
        return BoolComposite.make(
            bool_op,
            [
                ColumnCheck(field=field_name, op=elem_op, value=ValueRef(literal=v))
                for v in val.values
            ],
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
