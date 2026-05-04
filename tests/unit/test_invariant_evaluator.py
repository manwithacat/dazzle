"""Tests for invariant evaluator (#coverage)."""

from datetime import date, datetime, timedelta

import pytest

from dazzle_back.runtime.invariant_evaluator import (
    InvariantViolationError,
    check_invariants_for_create,
    check_invariants_for_update,
    evaluate_invariant_expr,
    validate_invariant,
    validate_invariants,
)
from dazzle_back.specs.entity import (
    DurationUnitKind,
    InvariantComparisonKind,
    InvariantExprSpec,
    InvariantLogicalKind,
    InvariantSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field_ref(*path: str) -> InvariantExprSpec:
    return InvariantExprSpec(kind="field_ref", path=list(path))


def _literal(value: object) -> InvariantExprSpec:
    return InvariantExprSpec(kind="literal", value=value)


def _comparison(
    left: InvariantExprSpec,
    op: InvariantComparisonKind,
    right: InvariantExprSpec,
) -> InvariantExprSpec:
    return InvariantExprSpec(
        kind="comparison",
        comparison_left=left,
        comparison_op=op,
        comparison_right=right,
    )


def _logical(
    left: InvariantExprSpec,
    op: InvariantLogicalKind,
    right: InvariantExprSpec,
) -> InvariantExprSpec:
    return InvariantExprSpec(
        kind="logical",
        logical_left=left,
        logical_op=op,
        logical_right=right,
    )


# ---------------------------------------------------------------------------
# Literal + Field ref
# ---------------------------------------------------------------------------


class TestBasicExpressions:
    @pytest.mark.parametrize(
        ("expr", "record", "expected"),
        [
            (_literal(42), {}, 42),
            (_literal("active"), {}, "active"),
            (_field_ref("amount"), {"amount": 100}, 100),
            (_field_ref("x"), {}, None),
            (_field_ref("address", "city"), {"address": {"city": "London"}}, "London"),
            (InvariantExprSpec(kind="field_ref", path=[]), {}, None),
            (_field_ref("x", "y"), {"x": 5}, None),
        ],
        ids=[
            "test_literal",
            "test_literal_string",
            "test_field_ref_simple",
            "test_field_ref_missing",
            "test_field_ref_nested",
            "test_field_ref_empty_path",
            "test_field_ref_nested_non_dict",
        ],
    )
    def test_evaluate(self, expr: InvariantExprSpec, record: dict, expected: object) -> None:
        result = evaluate_invariant_expr(expr, record)
        if expected is None:
            assert result is None
        else:
            assert result == expected


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------


class TestDuration:
    def test_days(self) -> None:
        expr = InvariantExprSpec(
            kind="duration", duration_value=14, duration_unit=DurationUnitKind.DAYS
        )
        result = evaluate_invariant_expr(expr, {})
        assert result == timedelta(days=14)

    def test_hours(self) -> None:
        expr = InvariantExprSpec(
            kind="duration", duration_value=2, duration_unit=DurationUnitKind.HOURS
        )
        assert evaluate_invariant_expr(expr, {}) == timedelta(hours=2)

    def test_minutes(self) -> None:
        expr = InvariantExprSpec(
            kind="duration", duration_value=30, duration_unit=DurationUnitKind.MINUTES
        )
        assert evaluate_invariant_expr(expr, {}) == timedelta(minutes=30)

    def test_default_unit(self) -> None:
        expr = InvariantExprSpec(kind="duration", duration_value=5, duration_unit=None)
        assert evaluate_invariant_expr(expr, {}) == timedelta(days=5)

    def test_none_value(self) -> None:
        expr = InvariantExprSpec(
            kind="duration", duration_value=None, duration_unit=DurationUnitKind.DAYS
        )
        assert evaluate_invariant_expr(expr, {}) == timedelta(days=0)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


class TestComparison:
    @pytest.mark.parametrize(
        ("left_field", "op", "right_value", "record", "expected"),
        [
            # eq
            ("status", InvariantComparisonKind.EQ, "active", {"status": "active"}, True),
            ("status", InvariantComparisonKind.EQ, "active", {"status": "pending"}, False),
            # ne / gt / lt / ge / le
            ("x", InvariantComparisonKind.NE, 0, {"x": 5}, True),
            ("amount", InvariantComparisonKind.GT, 0, {"amount": 10}, True),
            ("amount", InvariantComparisonKind.GT, 0, {"amount": 0}, False),
            ("x", InvariantComparisonKind.LT, 100, {"x": 50}, True),
            ("qty", InvariantComparisonKind.GE, 0, {"qty": 0}, True),
            ("x", InvariantComparisonKind.LE, 10, {"x": 10}, True),
            ("x", InvariantComparisonKind.LE, 10, {"x": 11}, False),
            # null handling
            ("x", InvariantComparisonKind.EQ, None, {}, True),  # both None → equal
            ("x", InvariantComparisonKind.NE, None, {"x": 5}, True),
            # SQL CHECK semantics: null vs ordered comparison → true (#491)
            ("x", InvariantComparisonKind.GT, 0, {}, True),
        ],
        ids=[
            "eq_true",
            "eq_false",
            "ne",
            "gt_above",
            "gt_at_threshold",
            "lt",
            "ge_at_zero",
            "le_at_threshold",
            "le_above_threshold",
            "none_eq_none",
            "none_ne_value",
            "none_ordered_returns_true",
        ],
    )
    def test_field_vs_literal(self, left_field, op, right_value, record, expected) -> None:
        expr = _comparison(_field_ref(left_field), op, _literal(right_value))
        assert evaluate_invariant_expr(expr, record) is expected

    def test_incompatible_types(self) -> None:
        """`'text' > 5` is incomparable; gracefully returns False rather than raising."""
        expr = _comparison(_literal("text"), InvariantComparisonKind.GT, _literal(5))
        assert evaluate_invariant_expr(expr, {}) is False

    def test_missing_parts(self) -> None:
        """A comparison with no left/right operands evaluates to False, not crash."""
        expr = InvariantExprSpec(kind="comparison")
        assert evaluate_invariant_expr(expr, {}) is False


# ---------------------------------------------------------------------------
# Date comparisons
# ---------------------------------------------------------------------------


class TestDateComparisons:
    def test_date_gt_date(self) -> None:
        expr = _comparison(
            _field_ref("end_date"), InvariantComparisonKind.GT, _field_ref("start_date")
        )
        record = {"start_date": "2025-01-01", "end_date": "2025-12-31"}
        assert evaluate_invariant_expr(expr, record) is True

    def test_date_string_normalization(self) -> None:
        expr = _comparison(_field_ref("a"), InvariantComparisonKind.EQ, _field_ref("b"))
        record = {"a": "2025-06-15T12:00:00Z", "b": "2025-06-15"}
        assert evaluate_invariant_expr(expr, record) is True

    def test_datetime_object_normalization(self) -> None:
        expr = _comparison(_field_ref("a"), InvariantComparisonKind.EQ, _field_ref("b"))
        record = {"a": datetime(2025, 6, 15, 10, 30), "b": date(2025, 6, 15)}
        assert evaluate_invariant_expr(expr, record) is True

    def test_date_plus_timedelta(self) -> None:
        """field > 14 days means field > today + 14 days."""
        future = date.today() + timedelta(days=20)
        dur = InvariantExprSpec(
            kind="duration", duration_value=14, duration_unit=DurationUnitKind.DAYS
        )
        expr = _comparison(_field_ref("due_date"), InvariantComparisonKind.GT, dur)
        assert evaluate_invariant_expr(expr, {"due_date": future.isoformat()}) is True

    def test_decimal_normalization(self) -> None:
        from decimal import Decimal

        expr = _comparison(_field_ref("a"), InvariantComparisonKind.EQ, _literal(10.5))
        assert evaluate_invariant_expr(expr, {"a": Decimal("10.5")}) is True


# ---------------------------------------------------------------------------
# Logical
# ---------------------------------------------------------------------------


class TestLogical:
    def test_and_both_true(self) -> None:
        left = _comparison(_field_ref("a"), InvariantComparisonKind.GT, _literal(0))
        right = _comparison(_field_ref("b"), InvariantComparisonKind.GT, _literal(0))
        expr = _logical(left, InvariantLogicalKind.AND, right)
        assert evaluate_invariant_expr(expr, {"a": 1, "b": 1}) is True

    def test_and_one_false(self) -> None:
        left = _comparison(_field_ref("a"), InvariantComparisonKind.GT, _literal(0))
        right = _comparison(_field_ref("b"), InvariantComparisonKind.GT, _literal(0))
        expr = _logical(left, InvariantLogicalKind.AND, right)
        assert evaluate_invariant_expr(expr, {"a": 1, "b": -1}) is False

    def test_or_one_true(self) -> None:
        left = _comparison(_field_ref("status"), InvariantComparisonKind.EQ, _literal("active"))
        right = _comparison(_field_ref("status"), InvariantComparisonKind.EQ, _literal("pending"))
        expr = _logical(left, InvariantLogicalKind.OR, right)
        assert evaluate_invariant_expr(expr, {"status": "pending"}) is True

    def test_or_both_false(self) -> None:
        left = _comparison(_field_ref("x"), InvariantComparisonKind.EQ, _literal(1))
        right = _comparison(_field_ref("x"), InvariantComparisonKind.EQ, _literal(2))
        expr = _logical(left, InvariantLogicalKind.OR, right)
        assert evaluate_invariant_expr(expr, {"x": 3}) is False

    def test_missing_parts(self) -> None:
        expr = InvariantExprSpec(kind="logical")
        assert evaluate_invariant_expr(expr, {}) is False


# ---------------------------------------------------------------------------
# NOT
# ---------------------------------------------------------------------------


class TestNot:
    def test_not_true(self) -> None:
        inner = _comparison(_field_ref("active"), InvariantComparisonKind.EQ, _literal(True))
        expr = InvariantExprSpec(kind="not", not_operand=inner)
        assert evaluate_invariant_expr(expr, {"active": False}) is True

    def test_not_false(self) -> None:
        inner = _comparison(_field_ref("x"), InvariantComparisonKind.GT, _literal(0))
        expr = InvariantExprSpec(kind="not", not_operand=inner)
        assert evaluate_invariant_expr(expr, {"x": 5}) is False

    def test_not_missing_operand(self) -> None:
        expr = InvariantExprSpec(kind="not", not_operand=None)
        assert evaluate_invariant_expr(expr, {}) is False


# ---------------------------------------------------------------------------
# Unknown kind
# ---------------------------------------------------------------------------


class TestUnknownKind:
    def test_returns_none(self) -> None:
        from unittest.mock import MagicMock

        expr = MagicMock()
        expr.kind = "magic"
        assert evaluate_invariant_expr(expr, {}) is None


# ---------------------------------------------------------------------------
# Invariant validation
# ---------------------------------------------------------------------------


class TestValidation:
    def _invariant(self, expr: InvariantExprSpec, message: str = "failed") -> InvariantSpec:
        return InvariantSpec(expression=expr, message=message)

    def test_validate_passes(self) -> None:
        expr = _comparison(_field_ref("amount"), InvariantComparisonKind.GT, _literal(0))
        assert validate_invariant(self._invariant(expr), {"amount": 10}) is True

    def test_validate_fails(self) -> None:
        expr = _comparison(_field_ref("amount"), InvariantComparisonKind.GT, _literal(0))
        assert validate_invariant(self._invariant(expr), {"amount": -1}) is False

    def test_validate_invariants_returns_violations(self) -> None:
        inv1 = self._invariant(
            _comparison(_field_ref("a"), InvariantComparisonKind.GT, _literal(0)),
            "a must be positive",
        )
        inv2 = self._invariant(
            _comparison(_field_ref("b"), InvariantComparisonKind.GT, _literal(0)),
            "b must be positive",
        )
        violations = validate_invariants([inv1, inv2], {"a": 1, "b": -1})
        assert len(violations) == 1
        assert violations[0].message == "b must be positive"

    def test_validate_invariants_raises(self) -> None:
        inv = self._invariant(
            _comparison(_field_ref("x"), InvariantComparisonKind.GT, _literal(0)),
            "x must be positive",
        )
        with pytest.raises(InvariantViolationError, match="x must be positive"):
            validate_invariants([inv], {"x": -1}, raise_on_violation=True)

    def test_check_invariants_for_create(self) -> None:
        inv = self._invariant(
            _comparison(_field_ref("qty"), InvariantComparisonKind.GE, _literal(0)), "qty >= 0"
        )
        check_invariants_for_create([inv], {"qty": 5})  # should not raise

    def test_check_invariants_for_create_violation(self) -> None:
        inv = self._invariant(
            _comparison(_field_ref("qty"), InvariantComparisonKind.GE, _literal(0)), "qty >= 0"
        )
        with pytest.raises(InvariantViolationError):
            check_invariants_for_create([inv], {"qty": -1})

    def test_check_invariants_for_update(self) -> None:
        inv = self._invariant(
            _comparison(_field_ref("end"), InvariantComparisonKind.GT, _field_ref("start")),
            "end > start",
        )
        check_invariants_for_update([inv], {"start": 1, "end": 5}, {"end": 10})  # should not raise

    def test_check_invariants_for_update_violation(self) -> None:
        inv = self._invariant(
            _comparison(_field_ref("end"), InvariantComparisonKind.GT, _field_ref("start")),
            "end > start",
        )
        with pytest.raises(InvariantViolationError):
            check_invariants_for_update([inv], {"start": 10, "end": 20}, {"end": 5})


# ---------------------------------------------------------------------------
# InvariantViolationError
# ---------------------------------------------------------------------------


class TestViolationError:
    def test_attributes(self) -> None:
        inv = InvariantSpec(expression=_literal(True), message="test message")
        exc = InvariantViolationError("test message", inv)
        assert exc.message == "test message"
        assert exc.invariant is inv
