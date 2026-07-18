"""#1626 — aggregate where current_user must not bind as a string literal."""

from __future__ import annotations

from dazzle.core.ir.condition_to_predicate import condition_expr_to_scope_predicate
from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    LogicalOperator,
)
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.http.runtime.predicate_compiler import CurrentUserRef, compile_predicate


def test_current_user_literal_becomes_current_user_ref() -> None:
    where = ConditionExpr(
        left=ConditionExpr(
            comparison=Comparison(
                field="status",
                operator=ComparisonOperator.EQUALS,
                value=ConditionValue(literal="in_progress"),
            )
        ),
        operator=LogicalOperator.AND,
        right=ConditionExpr(
            comparison=Comparison(
                field="assigned_to",
                operator=ComparisonOperator.EQUALS,
                value=ConditionValue(literal="current_user"),
            )
        ),
    )
    pred = condition_expr_to_scope_predicate(where)
    sql, params = compile_predicate(pred, "Task", FKGraph())
    assert "assigned_to" in sql
    assert any(isinstance(p, CurrentUserRef) for p in params)
    assert "current_user" not in params
