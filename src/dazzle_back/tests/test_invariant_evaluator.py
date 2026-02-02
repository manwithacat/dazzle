"""Tests for invariant evaluator."""

from datetime import date, timedelta

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


class TestFieldReferenceEvaluation:
    """Tests for field reference evaluation."""

    def test_simple_field_ref(self) -> None:
        """Test evaluating a simple field reference."""
        expr = InvariantExprSpec(kind="field_ref", path=["amount"])
        result = evaluate_invariant_expr(expr, {"amount": 100})
        assert result == 100

    def test_nested_field_ref(self) -> None:
        """Test evaluating a nested field reference."""
        expr = InvariantExprSpec(kind="field_ref", path=["address", "city"])
        result = evaluate_invariant_expr(expr, {"address": {"city": "New York", "zip": "10001"}})
        assert result == "New York"

    def test_missing_field_ref(self) -> None:
        """Test evaluating a missing field reference."""
        expr = InvariantExprSpec(kind="field_ref", path=["missing"])
        result = evaluate_invariant_expr(expr, {"other": 100})
        assert result is None

    def test_empty_path(self) -> None:
        """Test evaluating an empty path."""
        expr = InvariantExprSpec(kind="field_ref", path=[])
        result = evaluate_invariant_expr(expr, {"a": 1})
        assert result is None


class TestLiteralEvaluation:
    """Tests for literal value evaluation."""

    def test_integer_literal(self) -> None:
        """Test evaluating an integer literal."""
        expr = InvariantExprSpec(kind="literal", value=42)
        result = evaluate_invariant_expr(expr, {})
        assert result == 42

    def test_float_literal(self) -> None:
        """Test evaluating a float literal."""
        expr = InvariantExprSpec(kind="literal", value=3.14)
        result = evaluate_invariant_expr(expr, {})
        assert result == 3.14

    def test_string_literal(self) -> None:
        """Test evaluating a string literal."""
        expr = InvariantExprSpec(kind="literal", value="hello")
        result = evaluate_invariant_expr(expr, {})
        assert result == "hello"

    def test_boolean_literal(self) -> None:
        """Test evaluating a boolean literal."""
        expr = InvariantExprSpec(kind="literal", value=True)
        result = evaluate_invariant_expr(expr, {})
        assert result is True


class TestDurationEvaluation:
    """Tests for duration expression evaluation."""

    def test_days_duration(self) -> None:
        """Test evaluating a days duration."""
        expr = InvariantExprSpec(
            kind="duration", duration_value=14, duration_unit=DurationUnitKind.DAYS
        )
        result = evaluate_invariant_expr(expr, {})
        assert result == timedelta(days=14)

    def test_hours_duration(self) -> None:
        """Test evaluating an hours duration."""
        expr = InvariantExprSpec(
            kind="duration", duration_value=2, duration_unit=DurationUnitKind.HOURS
        )
        result = evaluate_invariant_expr(expr, {})
        assert result == timedelta(hours=2)

    def test_minutes_duration(self) -> None:
        """Test evaluating a minutes duration."""
        expr = InvariantExprSpec(
            kind="duration", duration_value=30, duration_unit=DurationUnitKind.MINUTES
        )
        result = evaluate_invariant_expr(expr, {})
        assert result == timedelta(minutes=30)


class TestComparisonEvaluation:
    """Tests for comparison expression evaluation."""

    def test_equality_true(self) -> None:
        """Test equality comparison that is true."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["status"]),
            comparison_op=InvariantComparisonKind.EQ,
            comparison_right=InvariantExprSpec(kind="literal", value="active"),
        )
        result = evaluate_invariant_expr(expr, {"status": "active"})
        assert result is True

    def test_equality_false(self) -> None:
        """Test equality comparison that is false."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["status"]),
            comparison_op=InvariantComparisonKind.EQ,
            comparison_right=InvariantExprSpec(kind="literal", value="active"),
        )
        result = evaluate_invariant_expr(expr, {"status": "inactive"})
        assert result is False

    def test_not_equal_true(self) -> None:
        """Test not-equal comparison that is true."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["count"]),
            comparison_op=InvariantComparisonKind.NE,
            comparison_right=InvariantExprSpec(kind="literal", value=0),
        )
        result = evaluate_invariant_expr(expr, {"count": 5})
        assert result is True

    def test_greater_than(self) -> None:
        """Test greater-than comparison."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
            comparison_op=InvariantComparisonKind.GT,
            comparison_right=InvariantExprSpec(kind="literal", value=0),
        )
        assert evaluate_invariant_expr(expr, {"quantity": 10}) is True
        assert evaluate_invariant_expr(expr, {"quantity": 0}) is False

    def test_less_than(self) -> None:
        """Test less-than comparison."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["price"]),
            comparison_op=InvariantComparisonKind.LT,
            comparison_right=InvariantExprSpec(kind="literal", value=100),
        )
        assert evaluate_invariant_expr(expr, {"price": 50}) is True
        assert evaluate_invariant_expr(expr, {"price": 100}) is False

    def test_greater_equal(self) -> None:
        """Test greater-or-equal comparison."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["age"]),
            comparison_op=InvariantComparisonKind.GE,
            comparison_right=InvariantExprSpec(kind="literal", value=18),
        )
        assert evaluate_invariant_expr(expr, {"age": 18}) is True
        assert evaluate_invariant_expr(expr, {"age": 21}) is True
        assert evaluate_invariant_expr(expr, {"age": 17}) is False

    def test_less_equal(self) -> None:
        """Test less-or-equal comparison."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["score"]),
            comparison_op=InvariantComparisonKind.LE,
            comparison_right=InvariantExprSpec(kind="literal", value=100),
        )
        assert evaluate_invariant_expr(expr, {"score": 100}) is True
        assert evaluate_invariant_expr(expr, {"score": 90}) is True
        assert evaluate_invariant_expr(expr, {"score": 101}) is False

    def test_comparison_with_none_left(self) -> None:
        """Test comparison with None on left side."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["missing"]),
            comparison_op=InvariantComparisonKind.GT,
            comparison_right=InvariantExprSpec(kind="literal", value=0),
        )
        result = evaluate_invariant_expr(expr, {})
        assert result is False

    def test_field_comparison(self) -> None:
        """Test comparing two fields."""
        # end_date > start_date
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["end_date"]),
            comparison_op=InvariantComparisonKind.GT,
            comparison_right=InvariantExprSpec(kind="field_ref", path=["start_date"]),
        )
        assert (
            evaluate_invariant_expr(
                expr, {"start_date": date(2024, 1, 1), "end_date": date(2024, 1, 15)}
            )
            is True
        )
        assert (
            evaluate_invariant_expr(
                expr, {"start_date": date(2024, 1, 15), "end_date": date(2024, 1, 1)}
            )
            is False
        )


class TestDateComparisons:
    """Tests for date-specific comparison operations."""

    def test_date_string_comparison(self) -> None:
        """Test comparing dates as ISO strings."""
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["due_date"]),
            comparison_op=InvariantComparisonKind.GT,
            comparison_right=InvariantExprSpec(kind="field_ref", path=["start_date"]),
        )
        result = evaluate_invariant_expr(
            expr, {"start_date": "2024-01-01", "due_date": "2024-01-15"}
        )
        assert result is True

    def test_date_vs_duration_future(self) -> None:
        """Test date > duration (future threshold)."""
        future_date = date.today() + timedelta(days=20)
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["due_date"]),
            comparison_op=InvariantComparisonKind.GT,
            comparison_right=InvariantExprSpec(
                kind="duration", duration_value=14, duration_unit=DurationUnitKind.DAYS
            ),
        )
        # due_date > today + 14 days
        result = evaluate_invariant_expr(expr, {"due_date": future_date})
        assert result is True

    def test_date_vs_duration_too_soon(self) -> None:
        """Test date > duration where date is too soon."""
        near_date = date.today() + timedelta(days=7)
        expr = InvariantExprSpec(
            kind="comparison",
            comparison_left=InvariantExprSpec(kind="field_ref", path=["due_date"]),
            comparison_op=InvariantComparisonKind.GT,
            comparison_right=InvariantExprSpec(
                kind="duration", duration_value=14, duration_unit=DurationUnitKind.DAYS
            ),
        )
        # due_date (7 days from now) > today + 14 days is False
        result = evaluate_invariant_expr(expr, {"due_date": near_date})
        assert result is False


class TestLogicalOperators:
    """Tests for logical operator evaluation."""

    def test_and_both_true(self) -> None:
        """Test AND when both operands are true."""
        # quantity > 0 AND price > 0
        expr = InvariantExprSpec(
            kind="logical",
            logical_left=InvariantExprSpec(
                kind="comparison",
                comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                comparison_op=InvariantComparisonKind.GT,
                comparison_right=InvariantExprSpec(kind="literal", value=0),
            ),
            logical_op=InvariantLogicalKind.AND,
            logical_right=InvariantExprSpec(
                kind="comparison",
                comparison_left=InvariantExprSpec(kind="field_ref", path=["price"]),
                comparison_op=InvariantComparisonKind.GT,
                comparison_right=InvariantExprSpec(kind="literal", value=0),
            ),
        )
        result = evaluate_invariant_expr(expr, {"quantity": 5, "price": 10})
        assert result is True

    def test_and_one_false(self) -> None:
        """Test AND when one operand is false."""
        # quantity > 0 AND price > 0
        expr = InvariantExprSpec(
            kind="logical",
            logical_left=InvariantExprSpec(
                kind="comparison",
                comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                comparison_op=InvariantComparisonKind.GT,
                comparison_right=InvariantExprSpec(kind="literal", value=0),
            ),
            logical_op=InvariantLogicalKind.AND,
            logical_right=InvariantExprSpec(
                kind="comparison",
                comparison_left=InvariantExprSpec(kind="field_ref", path=["price"]),
                comparison_op=InvariantComparisonKind.GT,
                comparison_right=InvariantExprSpec(kind="literal", value=0),
            ),
        )
        result = evaluate_invariant_expr(expr, {"quantity": 5, "price": 0})
        assert result is False

    def test_or_one_true(self) -> None:
        """Test OR when one operand is true."""
        # is_admin OR is_owner
        expr = InvariantExprSpec(
            kind="logical",
            logical_left=InvariantExprSpec(kind="field_ref", path=["is_admin"]),
            logical_op=InvariantLogicalKind.OR,
            logical_right=InvariantExprSpec(kind="field_ref", path=["is_owner"]),
        )
        assert evaluate_invariant_expr(expr, {"is_admin": True, "is_owner": False}) is True
        assert evaluate_invariant_expr(expr, {"is_admin": False, "is_owner": True}) is True
        assert evaluate_invariant_expr(expr, {"is_admin": False, "is_owner": False}) is False

    def test_not_operator(self) -> None:
        """Test NOT operator."""
        # NOT is_deleted
        expr = InvariantExprSpec(
            kind="not",
            not_operand=InvariantExprSpec(kind="field_ref", path=["is_deleted"]),
        )
        assert evaluate_invariant_expr(expr, {"is_deleted": False}) is True
        assert evaluate_invariant_expr(expr, {"is_deleted": True}) is False


class TestInvariantValidation:
    """Tests for invariant validation."""

    def test_validate_simple_invariant_pass(self) -> None:
        """Test validating a simple invariant that passes."""
        invariant = InvariantSpec(
            expression=InvariantExprSpec(
                kind="comparison",
                comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                comparison_op=InvariantComparisonKind.GT,
                comparison_right=InvariantExprSpec(kind="literal", value=0),
            ),
            message="Quantity must be positive",
        )
        result = validate_invariant(invariant, {"quantity": 10})
        assert result is True

    def test_validate_simple_invariant_fail(self) -> None:
        """Test validating a simple invariant that fails."""
        invariant = InvariantSpec(
            expression=InvariantExprSpec(
                kind="comparison",
                comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                comparison_op=InvariantComparisonKind.GT,
                comparison_right=InvariantExprSpec(kind="literal", value=0),
            ),
            message="Quantity must be positive",
        )
        result = validate_invariant(invariant, {"quantity": 0})
        assert result is False

    def test_validate_multiple_invariants_all_pass(self) -> None:
        """Test validating multiple invariants that all pass."""
        invariants = [
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                    comparison_op=InvariantComparisonKind.GT,
                    comparison_right=InvariantExprSpec(kind="literal", value=0),
                ),
            ),
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["price"]),
                    comparison_op=InvariantComparisonKind.GE,
                    comparison_right=InvariantExprSpec(kind="literal", value=0),
                ),
            ),
        ]
        violations = validate_invariants(invariants, {"quantity": 10, "price": 5})
        assert len(violations) == 0

    def test_validate_multiple_invariants_one_fails(self) -> None:
        """Test validating multiple invariants where one fails."""
        invariants = [
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                    comparison_op=InvariantComparisonKind.GT,
                    comparison_right=InvariantExprSpec(kind="literal", value=0),
                ),
            ),
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["price"]),
                    comparison_op=InvariantComparisonKind.GT,
                    comparison_right=InvariantExprSpec(kind="literal", value=0),
                ),
            ),
        ]
        violations = validate_invariants(invariants, {"quantity": 10, "price": -5})
        assert len(violations) == 1

    def test_validate_with_raise_on_violation(self) -> None:
        """Test validating with raise_on_violation=True."""
        invariants = [
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                    comparison_op=InvariantComparisonKind.GT,
                    comparison_right=InvariantExprSpec(kind="literal", value=0),
                ),
                message="Quantity must be positive",
            ),
        ]
        with pytest.raises(InvariantViolationError) as exc_info:
            validate_invariants(invariants, {"quantity": 0}, raise_on_violation=True)
        assert exc_info.value.message == "Quantity must be positive"


class TestCreateUpdateChecks:
    """Tests for create/update invariant checking."""

    def test_check_invariants_for_create_pass(self) -> None:
        """Test checking invariants for create that passes."""
        invariants = [
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["end_date"]),
                    comparison_op=InvariantComparisonKind.GT,
                    comparison_right=InvariantExprSpec(kind="field_ref", path=["start_date"]),
                ),
                message="End date must be after start date",
            ),
        ]
        # Should not raise
        check_invariants_for_create(
            invariants,
            {"start_date": date(2024, 1, 1), "end_date": date(2024, 1, 15)},
        )

    def test_check_invariants_for_create_fail(self) -> None:
        """Test checking invariants for create that fails."""
        invariants = [
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["end_date"]),
                    comparison_op=InvariantComparisonKind.GT,
                    comparison_right=InvariantExprSpec(kind="field_ref", path=["start_date"]),
                ),
                message="End date must be after start date",
            ),
        ]
        with pytest.raises(InvariantViolationError) as exc_info:
            check_invariants_for_create(
                invariants,
                {"start_date": date(2024, 1, 15), "end_date": date(2024, 1, 1)},
            )
        assert "End date must be after start date" in exc_info.value.message

    def test_check_invariants_for_update_pass(self) -> None:
        """Test checking invariants for update that passes."""
        invariants = [
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                    comparison_op=InvariantComparisonKind.GE,
                    comparison_right=InvariantExprSpec(kind="literal", value=0),
                ),
            ),
        ]
        # Should not raise
        check_invariants_for_update(
            invariants,
            {"id": 1, "quantity": 10, "name": "Test"},
            {"quantity": 5},
        )

    def test_check_invariants_for_update_fail(self) -> None:
        """Test checking invariants for update that fails."""
        invariants = [
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["quantity"]),
                    comparison_op=InvariantComparisonKind.GE,
                    comparison_right=InvariantExprSpec(kind="literal", value=0),
                ),
                message="Quantity cannot be negative",
            ),
        ]
        with pytest.raises(InvariantViolationError):
            check_invariants_for_update(
                invariants,
                {"id": 1, "quantity": 10, "name": "Test"},
                {"quantity": -5},
            )

    def test_check_invariants_for_update_merges_correctly(self) -> None:
        """Test that update merges current record with updates."""
        # Invariant: end_date > start_date
        invariants = [
            InvariantSpec(
                expression=InvariantExprSpec(
                    kind="comparison",
                    comparison_left=InvariantExprSpec(kind="field_ref", path=["end_date"]),
                    comparison_op=InvariantComparisonKind.GT,
                    comparison_right=InvariantExprSpec(kind="field_ref", path=["start_date"]),
                ),
            ),
        ]
        current = {
            "id": 1,
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 1, 15),
        }
        # Update only end_date, keeping existing start_date
        check_invariants_for_update(
            invariants,
            current,
            {"end_date": date(2024, 1, 20)},
        )
        # Should pass because merged record has end_date > start_date
