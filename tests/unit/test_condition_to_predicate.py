"""ConditionExpr → ScopePredicate translation (Slice 2 of ADR-0024).

Replaces the legacy string round-trip through ``parse_aggregate_where``
for typed-IR aggregate where-clauses. The fetchers
(``_fetch_count_metric`` / ``_fetch_scalar_metric``) now consume
``ConditionExpr`` directly; this module pins the translation shape.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.condition_to_predicate import condition_expr_to_scope_predicate
from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    GrantCheck,
    LogicalOperator,
    RoleCheck,
    ViaCondition,
)
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Tautology,
)


def _cmp(field: str, op: ComparisonOperator, literal) -> ConditionExpr:
    return ConditionExpr(
        comparison=Comparison(field=field, operator=op, value=ConditionValue(literal=literal))
    )


def test_none_is_tautology() -> None:
    assert isinstance(condition_expr_to_scope_predicate(None), Tautology)


def test_simple_equals_to_column_check() -> None:
    pred = condition_expr_to_scope_predicate(_cmp("status", ComparisonOperator.EQUALS, "open"))
    assert isinstance(pred, ColumnCheck)
    assert pred.field == "status"
    assert pred.op == CompOp.EQ
    assert pred.value.literal == "open"


def test_not_equals_preserved() -> None:
    pred = condition_expr_to_scope_predicate(_cmp("status", ComparisonOperator.NOT_EQUALS, "done"))
    assert isinstance(pred, ColumnCheck)
    assert pred.op == CompOp.NEQ


def test_boolean_literal() -> None:
    pred = condition_expr_to_scope_predicate(_cmp("flagged", ComparisonOperator.EQUALS, True))
    assert isinstance(pred, ColumnCheck)
    assert pred.value.literal is True


def test_null_literal_routes_to_literal_null() -> None:
    pred = condition_expr_to_scope_predicate(_cmp("deleted_at", ComparisonOperator.IS, None))
    assert isinstance(pred, ColumnCheck)
    assert pred.value.literal_null is True


def test_compound_and() -> None:
    expr = ConditionExpr(
        left=_cmp("status", ComparisonOperator.EQUALS, "open"),
        operator=LogicalOperator.AND,
        right=_cmp("priority", ComparisonOperator.EQUALS, "high"),
    )
    pred = condition_expr_to_scope_predicate(expr)
    assert isinstance(pred, BoolComposite)
    assert pred.op == BoolOp.AND
    assert len(pred.children) == 2


def test_compound_or() -> None:
    expr = ConditionExpr(
        left=_cmp("status", ComparisonOperator.EQUALS, "open"),
        operator=LogicalOperator.OR,
        right=_cmp("status", ComparisonOperator.EQUALS, "doing"),
    )
    pred = condition_expr_to_scope_predicate(expr)
    assert isinstance(pred, BoolComposite)
    assert pred.op == BoolOp.OR


def test_in_list_expands_to_or_of_column_checks() -> None:
    expr = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.IN,
            value=ConditionValue(values=["open", "doing"]),
        )
    )
    pred = condition_expr_to_scope_predicate(expr)
    # IN list → OR of equality ColumnChecks.
    assert isinstance(pred, BoolComposite)
    assert pred.op == BoolOp.OR
    assert all(isinstance(c, ColumnCheck) for c in pred.children)
    assert {c.value.literal for c in pred.children} == {"open", "doing"}


def test_in_list_children_use_equality_op_not_in() -> None:
    # #1472: each expanded child compares against a SINGLE literal, so it
    # must use `=`, not `IN`. Keeping `IN` produces `col IN %s` with a
    # scalar bind — invalid SQL that silently fetched 0 on dashboards.
    expr = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.IN,
            value=ConditionValue(values=["reviewed", "released", "analysed"]),
        )
    )
    pred = condition_expr_to_scope_predicate(expr)
    assert all(c.op == CompOp.EQ for c in pred.children)


def test_in_list_compiles_to_valid_equality_sql() -> None:
    # #1472: the compiled SQL must be `= %s` per branch, never `IN %s`.
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.http.runtime.predicate_compiler import compile_predicate

    expr = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.IN,
            value=ConditionValue(values=["reviewed", "released"]),
        )
    )
    pred = condition_expr_to_scope_predicate(expr)
    sql, params = compile_predicate(pred, "AssessmentEvent", FKGraph())
    assert "IN %s" not in sql
    assert sql.count("= %s") == 2
    assert params == ["reviewed", "released"]


def test_not_in_list_expands_to_and_of_inequality() -> None:
    # #1472: `not in [a, b]` means `field != a AND field != b` — AND of
    # NEQ, not OR of NOT_IN.
    expr = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.NOT_IN,
            value=ConditionValue(values=["archived", "deleted"]),
        )
    )
    pred = condition_expr_to_scope_predicate(expr)
    assert isinstance(pred, BoolComposite)
    assert pred.op == BoolOp.AND
    assert all(c.op == CompOp.NEQ for c in pred.children)


def test_role_check_rejected() -> None:
    expr = ConditionExpr(role_check=RoleCheck(role_name="admin"))
    with pytest.raises(ValueError, match="role"):
        condition_expr_to_scope_predicate(expr)


def test_grant_check_rejected() -> None:
    expr = ConditionExpr(
        grant_check=GrantCheck(relation="member", scope_field="org_id"),
    )
    with pytest.raises(ValueError, match="grant"):
        condition_expr_to_scope_predicate(expr)


def test_via_condition_rejected() -> None:
    expr = ConditionExpr(
        via_condition=ViaCondition(junction_entity="X", bindings=[]),
    )
    with pytest.raises(ValueError, match="via"):
        condition_expr_to_scope_predicate(expr)


def test_dotted_field_rejected() -> None:
    """A dotted (FK-path) field has no FK-join compilation path in the
    aggregate where-clause builder — a flat ColumnCheck would compile to an
    invalid quoted compound identifier (e.g. "E"."a.b"). Fail loud instead
    of emitting broken SQL (#1334). FK-path traversal is the RBAC scope
    path's job (build_scope_predicate → PathCheck), not this builder's.
    """
    expr = _cmp("cohort_assessment.uploaded_by", ComparisonOperator.EQUALS, "x")
    with pytest.raises(ValueError, match="dotted field path"):
        condition_expr_to_scope_predicate(expr)
