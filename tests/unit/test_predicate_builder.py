"""Tests for the ConditionExpr → ScopePredicate converter."""

from __future__ import annotations

import pytest

from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    GrantCheck,
    LogicalOperator,
    RoleCheck,
    ViaBinding,
    ViaCondition,
)
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.predicate_builder import build_scope_predicate
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_graph() -> FKGraph:
    """FKGraph with no entities."""
    return FKGraph()


@pytest.fixture()
def feedback_graph() -> FKGraph:
    """FKGraph with Feedback → Manuscript FK for path tests."""
    graph = FKGraph()
    graph._edges = {"Feedback": {"manuscript_id": "Manuscript"}}
    graph._fields = {
        "Feedback": {"id", "manuscript_id", "content", "owner"},
        "Manuscript": {"id", "student_id"},
    }
    return graph


# ---------------------------------------------------------------------------
# None condition
# ---------------------------------------------------------------------------


def test_none_condition_returns_tautology(empty_graph: FKGraph) -> None:
    result = build_scope_predicate(None, "Task", empty_graph)
    assert isinstance(result, Tautology)


# ---------------------------------------------------------------------------
# Simple comparisons
# ---------------------------------------------------------------------------


def test_simple_field_equals_literal(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(
        comparison=Comparison(
            field="status",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="active"),
        )
    )
    result = build_scope_predicate(condition, "Task", empty_graph)
    assert isinstance(result, ColumnCheck)
    assert result.field == "status"
    assert result.op == CompOp.EQ
    assert result.value == ValueRef(literal="active")


def test_field_equals_current_user(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(
        comparison=Comparison(
            field="owner_id",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )
    result = build_scope_predicate(condition, "Task", empty_graph)
    assert isinstance(result, UserAttrCheck)
    assert result.field == "owner_id"
    assert result.op == CompOp.EQ
    assert result.user_attr == "entity_id"


def test_field_equals_current_user_dot_attr(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(
        comparison=Comparison(
            field="school_id",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user.school"),
        )
    )
    result = build_scope_predicate(condition, "Task", empty_graph)
    assert isinstance(result, UserAttrCheck)
    assert result.field == "school_id"
    assert result.op == CompOp.EQ
    assert result.user_attr == "school"


# ---------------------------------------------------------------------------
# Dotted left-side → PathCheck
# ---------------------------------------------------------------------------


def test_dotted_field_becomes_path_check(feedback_graph: FKGraph) -> None:
    condition = ConditionExpr(
        comparison=Comparison(
            field="manuscript.student_id",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )
    result = build_scope_predicate(condition, "Feedback", feedback_graph)
    assert isinstance(result, PathCheck)
    assert result.path == ["manuscript", "student_id"]
    assert result.op == CompOp.EQ
    assert result.value == ValueRef(current_user=True)


# ---------------------------------------------------------------------------
# Null literal → IS / IS NOT
# ---------------------------------------------------------------------------


def test_field_equals_null(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(
        comparison=Comparison(
            field="deleted_at",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="null"),
        )
    )
    result = build_scope_predicate(condition, "Task", empty_graph)
    assert isinstance(result, ColumnCheck)
    assert result.field == "deleted_at"
    assert result.op == CompOp.IS
    assert result.value == ValueRef(literal_null=True)


def test_field_not_equals_null(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(
        comparison=Comparison(
            field="deleted_at",
            operator=ComparisonOperator.NOT_EQUALS,
            value=ConditionValue(literal="null"),
        )
    )
    result = build_scope_predicate(condition, "Task", empty_graph)
    assert isinstance(result, ColumnCheck)
    assert result.field == "deleted_at"
    assert result.op == CompOp.IS_NOT
    assert result.value == ValueRef(literal_null=True)


# ---------------------------------------------------------------------------
# Via condition → ExistsCheck
# ---------------------------------------------------------------------------


def test_via_condition_becomes_exists_check(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(
        via_condition=ViaCondition(
            junction_entity="JunctionEntity",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user"),
                ViaBinding(junction_field="contact", target="id"),
            ],
            negated=False,
        )
    )
    result = build_scope_predicate(condition, "Contact", empty_graph)
    assert isinstance(result, ExistsCheck)
    assert result.target_entity == "JunctionEntity"
    assert result.negated is False
    assert result.bindings == [
        ExistsBinding(junction_field="agent", target="current_user", operator="="),
        ExistsBinding(junction_field="contact", target="id", operator="="),
    ]


def test_negated_via_condition(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(
        via_condition=ViaCondition(
            junction_entity="Blocklist",
            bindings=[
                ViaBinding(junction_field="blocked_user", target="current_user"),
                ViaBinding(junction_field="target", target="id"),
            ],
            negated=True,
        )
    )
    result = build_scope_predicate(condition, "User", empty_graph)
    assert isinstance(result, ExistsCheck)
    assert result.negated is True


# ---------------------------------------------------------------------------
# Boolean composites
# ---------------------------------------------------------------------------


def test_and_compound(empty_graph: FKGraph) -> None:
    left = ConditionExpr(
        comparison=Comparison(
            field="active",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="true"),
        )
    )
    right = ConditionExpr(
        comparison=Comparison(
            field="owner_id",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )
    condition = ConditionExpr(operator=LogicalOperator.AND, left=left, right=right)
    result = build_scope_predicate(condition, "Task", empty_graph)
    assert isinstance(result, BoolComposite)
    assert result.op == BoolOp.AND
    assert len(result.children) == 2


def test_or_compound(empty_graph: FKGraph) -> None:
    left = ConditionExpr(
        comparison=Comparison(
            field="owner_id",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )
    right = ConditionExpr(
        comparison=Comparison(
            field="shared",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="true"),
        )
    )
    condition = ConditionExpr(operator=LogicalOperator.OR, left=left, right=right)
    result = build_scope_predicate(condition, "Task", empty_graph)
    assert isinstance(result, BoolComposite)
    assert result.op == BoolOp.OR
    assert len(result.children) == 2


def test_not_compound(empty_graph: FKGraph) -> None:
    inner = ConditionExpr(
        comparison=Comparison(
            field="archived",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="true"),
        )
    )
    condition = ConditionExpr(operator=LogicalOperator.NOT, left=inner)
    result = build_scope_predicate(condition, "Task", empty_graph)
    # NOT(ColumnCheck) → BoolComposite(NOT, [ColumnCheck])
    assert isinstance(result, BoolComposite)
    assert result.op == BoolOp.NOT
    assert len(result.children) == 1
    assert isinstance(result.children[0], ColumnCheck)


# ---------------------------------------------------------------------------
# Role / grant checks raise ValueError
# ---------------------------------------------------------------------------


def test_role_check_raises(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(role_check=RoleCheck(role_name="admin"))
    with pytest.raises(ValueError, match="permit:"):
        build_scope_predicate(condition, "Task", empty_graph)


def test_grant_check_raises(empty_graph: FKGraph) -> None:
    condition = ConditionExpr(
        grant_check=GrantCheck(relation="acting_hod", scope_field="department")
    )
    with pytest.raises(ValueError, match="permit:"):
        build_scope_predicate(condition, "Task", empty_graph)


# ---------------------------------------------------------------------------
# All ComparisonOperator variants pass through correctly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cond_op,expected_op",
    [
        (ComparisonOperator.EQUALS, CompOp.EQ),
        (ComparisonOperator.NOT_EQUALS, CompOp.NEQ),
        (ComparisonOperator.GREATER_THAN, CompOp.GT),
        (ComparisonOperator.LESS_THAN, CompOp.LT),
        (ComparisonOperator.GREATER_EQUAL, CompOp.GTE),
        (ComparisonOperator.LESS_EQUAL, CompOp.LTE),
        (ComparisonOperator.IN, CompOp.IN),
        (ComparisonOperator.NOT_IN, CompOp.NOT_IN),
        (ComparisonOperator.IS, CompOp.IS),
        (ComparisonOperator.IS_NOT, CompOp.IS_NOT),
    ],
)
def test_operator_mapping(
    cond_op: ComparisonOperator,
    expected_op: CompOp,
    empty_graph: FKGraph,
) -> None:
    condition = ConditionExpr(
        comparison=Comparison(
            field="amount",
            operator=cond_op,
            value=ConditionValue(literal="42"),
        )
    )
    result = build_scope_predicate(condition, "Order", empty_graph)
    assert isinstance(result, ColumnCheck)
    assert result.op == expected_op
