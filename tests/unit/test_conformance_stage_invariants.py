"""Tests for stage-by-stage invariant verification (#603).

Tests the three stage verifiers and the round-trip checker against
the real predicate builder and compiler.
"""

from typing import Any

from dazzle.conformance.stage_invariants import (
    InvariantResult,
    StageVerification,
    verify_marker_resolution,
    verify_predicate_build,
    verify_round_trip,
    verify_sql_compilation,
)
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    Tautology,
    UserAttrCheck,
    ValueRef,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_condition(
    field: str = "status",
    op: str = "=",
    value: str | int | None = "active",
) -> Any:
    """Create a minimal ConditionExpr-like object."""
    from dazzle.core.ir.conditions import (
        Comparison,
        ComparisonOperator,
        ConditionExpr,
        ConditionValue,
    )

    return ConditionExpr(
        comparison=Comparison(
            field=field,
            operator=ComparisonOperator(op),
            value=ConditionValue(literal=value),
        )
    )


def _make_fk_graph(edges: dict[str, dict[str, str]] | None = None) -> Any:
    """Create a minimal FKGraph-like object."""
    from dazzle.core.ir.fk_graph import FKGraph

    graph = FKGraph()
    if edges:
        graph._edges = edges
    return graph


# =============================================================================
# StageVerification tests
# =============================================================================


class TestStageVerification:
    """StageVerification should capture stage results correctly."""

    def test_pass(self) -> None:
        sv = StageVerification(stage="test", passed=True, predicate_type="column_check")
        assert sv.passed
        assert sv.stage == "test"

    def test_fail_with_error(self) -> None:
        sv = StageVerification(stage="test", passed=False, error="boom")
        assert not sv.passed
        assert sv.error == "boom"


class TestInvariantResult:
    """InvariantResult should aggregate stage results."""

    def test_all_passed(self) -> None:
        result = InvariantResult(entity="Task", persona="viewer")
        result.stages.append(StageVerification(stage="a", passed=True))
        result.stages.append(StageVerification(stage="b", passed=True))
        assert result.all_passed

    def test_one_failed(self) -> None:
        result = InvariantResult(entity="Task", persona="viewer")
        result.stages.append(StageVerification(stage="a", passed=True))
        result.stages.append(StageVerification(stage="b", passed=False))
        assert not result.all_passed


# =============================================================================
# verify_predicate_build tests
# =============================================================================


class TestVerifyPredicateBuild:
    """verify_predicate_build should check ConditionExpr → ScopePredicate."""

    def test_none_produces_tautology(self) -> None:
        result = verify_predicate_build(None, "Task", _make_fk_graph(), expected_kind="tautology")
        assert result.passed
        assert result.predicate_type == "tautology"

    def test_simple_column_check(self) -> None:
        cond = _make_condition("status", "=", "active")
        result = verify_predicate_build(
            cond, "Task", _make_fk_graph(), expected_kind="column_check"
        )
        assert result.passed
        assert result.predicate_type == "column_check"

    def test_current_user_produces_user_attr_check(self) -> None:
        cond = _make_condition("owner_id", "=", "current_user")
        result = verify_predicate_build(
            cond, "Task", _make_fk_graph(), expected_kind="user_attr_check"
        )
        assert result.passed

    def test_current_user_attr_produces_user_attr_check(self) -> None:
        cond = _make_condition("school_id", "=", "current_user.school_id")
        result = verify_predicate_build(
            cond, "Task", _make_fk_graph(), expected_kind="user_attr_check"
        )
        assert result.passed

    def test_wrong_expected_kind_fails(self) -> None:
        cond = _make_condition("status", "=", "active")
        result = verify_predicate_build(
            cond, "Task", _make_fk_graph(), expected_kind="user_attr_check"
        )
        assert not result.passed
        assert "Expected predicate kind" in (result.error or "")

    def test_no_expected_kind_still_passes(self) -> None:
        cond = _make_condition("status", "=", "active")
        result = verify_predicate_build(cond, "Task", _make_fk_graph())
        assert result.passed

    def test_null_literal_produces_column_check(self) -> None:
        cond = _make_condition("revoked_at", "=", "null")
        result = verify_predicate_build(
            cond, "Task", _make_fk_graph(), expected_kind="column_check"
        )
        assert result.passed


# =============================================================================
# verify_sql_compilation tests
# =============================================================================


class TestVerifySqlCompilation:
    """verify_sql_compilation should check ScopePredicate → SQL."""

    def test_tautology_produces_empty_sql(self) -> None:
        result = verify_sql_compilation(Tautology(), "Task", _make_fk_graph())
        assert result.passed
        assert result.actual == ""

    def test_contradiction_produces_false(self) -> None:
        result = verify_sql_compilation(
            Contradiction(), "Task", _make_fk_graph(), expected_sql_contains="FALSE"
        )
        assert result.passed

    def test_column_check_produces_equals(self) -> None:
        pred = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        result = verify_sql_compilation(
            pred, "Task", _make_fk_graph(), expected_sql_contains="= %s"
        )
        assert result.passed
        assert '"status"' in result.actual

    def test_user_attr_check_produces_placeholder(self) -> None:
        pred = UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school_id")
        result = verify_sql_compilation(
            pred, "Task", _make_fk_graph(), expected_sql_contains="= %s"
        )
        assert result.passed

    def test_wrong_expected_sql_fails(self) -> None:
        pred = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        result = verify_sql_compilation(
            pred, "Task", _make_fk_graph(), expected_sql_contains="NOT EXISTS"
        )
        assert not result.passed
        assert "SQL does not contain" in (result.error or "")

    def test_bool_composite_and(self) -> None:
        pred = BoolComposite.make(
            BoolOp.AND,
            [
                ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active")),
                ColumnCheck(field="priority", op=CompOp.GT, value=ValueRef(literal=5)),
            ],
        )
        result = verify_sql_compilation(pred, "Task", _make_fk_graph(), expected_sql_contains="AND")
        assert result.passed

    def test_null_is_produces_is_null(self) -> None:
        pred = ColumnCheck(field="deleted_at", op=CompOp.IS, value=ValueRef(literal_null=True))
        result = verify_sql_compilation(
            pred, "Task", _make_fk_graph(), expected_sql_contains="IS NULL"
        )
        assert result.passed


# =============================================================================
# verify_marker_resolution tests
# =============================================================================


class TestVerifyMarkerResolution:
    """verify_marker_resolution should resolve markers to concrete values."""

    def test_no_markers(self) -> None:
        result = verify_marker_resolution(
            ["active", 5], {"id": "u1"}, expected_resolved=["active", 5]
        )
        assert result.passed

    def test_user_attr_ref(self) -> None:
        from dazzle_back.runtime.predicate_compiler import UserAttrRef

        result = verify_marker_resolution(
            [UserAttrRef("school_id")],
            {"id": "u1", "school_id": "s1"},
            expected_resolved=["s1"],
        )
        assert result.passed

    def test_current_user_ref(self) -> None:
        from dazzle_back.runtime.predicate_compiler import CurrentUserRef

        result = verify_marker_resolution(
            [CurrentUserRef()],
            {"id": "user-uuid-123"},
            expected_resolved=["user-uuid-123"],
        )
        assert result.passed

    def test_missing_attr_fails(self) -> None:
        from dazzle_back.runtime.predicate_compiler import UserAttrRef

        result = verify_marker_resolution([UserAttrRef("missing_field")], {"id": "u1"})
        assert not result.passed
        assert "missing attribute" in (result.error or "")

    def test_missing_id_fails(self) -> None:
        from dazzle_back.runtime.predicate_compiler import CurrentUserRef

        result = verify_marker_resolution([CurrentUserRef()], {})
        assert not result.passed
        assert "missing 'id'" in (result.error or "")

    def test_wrong_resolved_value_fails(self) -> None:
        from dazzle_back.runtime.predicate_compiler import UserAttrRef

        result = verify_marker_resolution(
            [UserAttrRef("school_id")],
            {"id": "u1", "school_id": "s1"},
            expected_resolved=["s2"],
        )
        assert not result.passed
        assert "!= expected" in (result.error or "")


# =============================================================================
# verify_round_trip tests
# =============================================================================


class TestVerifyRoundTrip:
    """verify_round_trip should chain all three stages."""

    def test_tautology_round_trip(self) -> None:
        result = verify_round_trip(
            condition=None,
            entity_name="Task",
            fk_graph=_make_fk_graph(),
            expected_predicate_kind="tautology",
        )
        assert result.all_passed
        assert len(result.stages) == 2  # No stage 3 without user_context

    def test_column_check_round_trip(self) -> None:
        cond = _make_condition("status", "=", "active")
        result = verify_round_trip(
            condition=cond,
            entity_name="Task",
            fk_graph=_make_fk_graph(),
            expected_predicate_kind="column_check",
            expected_sql_contains="= %s",
        )
        assert result.all_passed
        assert len(result.stages) == 2

    def test_user_attr_full_round_trip(self) -> None:
        cond = _make_condition("school_id", "=", "current_user.school_id")
        result = verify_round_trip(
            condition=cond,
            entity_name="Task",
            fk_graph=_make_fk_graph(),
            expected_predicate_kind="user_attr_check",
            expected_sql_contains="= %s",
            user_context={"id": "u1", "school_id": "school-123"},
            expected_resolved_params=["school-123"],
        )
        assert result.all_passed
        assert len(result.stages) == 3

    def test_stage1_failure_short_circuits(self) -> None:
        cond = _make_condition("status", "=", "active")
        result = verify_round_trip(
            condition=cond,
            entity_name="Task",
            fk_graph=_make_fk_graph(),
            expected_predicate_kind="exists_check",  # Wrong — will fail stage 1
        )
        assert not result.all_passed
        assert len(result.stages) == 1  # Short-circuited after stage 1

    def test_stage2_failure_short_circuits(self) -> None:
        cond = _make_condition("status", "=", "active")
        result = verify_round_trip(
            condition=cond,
            entity_name="Task",
            fk_graph=_make_fk_graph(),
            expected_predicate_kind="column_check",
            expected_sql_contains="NOT EXISTS",  # Wrong — will fail stage 2
        )
        assert not result.all_passed
        assert len(result.stages) == 2  # Short-circuited after stage 2

    def test_marker_resolution_failure(self) -> None:
        cond = _make_condition("school_id", "=", "current_user.school_id")
        result = verify_round_trip(
            condition=cond,
            entity_name="Task",
            fk_graph=_make_fk_graph(),
            user_context={"id": "u1"},  # Missing school_id
        )
        assert not result.all_passed
        assert len(result.stages) == 3


# =============================================================================
# BoolComposite simplification invariants
# =============================================================================


class TestBoolCompositeSimplifiation:
    """BoolComposite.make() algebraic laws should be verifiable."""

    def test_and_tautology_identity(self) -> None:
        """AND(x, Tautology) → x."""
        x = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        result = BoolComposite.make(BoolOp.AND, [x, Tautology()])
        assert isinstance(result, ColumnCheck)
        assert result.field == "status"

    def test_and_contradiction_absorption(self) -> None:
        """AND(x, Contradiction) → Contradiction."""
        x = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        result = BoolComposite.make(BoolOp.AND, [x, Contradiction()])
        assert isinstance(result, Contradiction)

    def test_or_tautology_absorption(self) -> None:
        """OR(x, Tautology) → Tautology."""
        x = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        result = BoolComposite.make(BoolOp.OR, [x, Tautology()])
        assert isinstance(result, Tautology)

    def test_or_contradiction_identity(self) -> None:
        """OR(x, Contradiction) → x."""
        x = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        result = BoolComposite.make(BoolOp.OR, [x, Contradiction()])
        assert isinstance(result, ColumnCheck)

    def test_not_tautology_contradiction(self) -> None:
        """NOT(Tautology) → Contradiction."""
        result = BoolComposite.make(BoolOp.NOT, [Tautology()])
        assert isinstance(result, Contradiction)

    def test_not_contradiction_tautology(self) -> None:
        """NOT(Contradiction) → Tautology."""
        result = BoolComposite.make(BoolOp.NOT, [Contradiction()])
        assert isinstance(result, Tautology)

    def test_double_negation_elimination(self) -> None:
        """NOT(NOT(x)) → x."""
        x = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        inner = BoolComposite.make(BoolOp.NOT, [x])
        result = BoolComposite.make(BoolOp.NOT, [inner])
        assert isinstance(result, ColumnCheck)
        assert result.field == "status"
