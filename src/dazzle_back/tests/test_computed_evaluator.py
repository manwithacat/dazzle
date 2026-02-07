"""Tests for computed field evaluator."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from dazzle_back.runtime.computed_evaluator import (
    enrich_record_with_computed_fields,
    evaluate_computed_fields,
    evaluate_expression,
)
from dazzle_back.specs.entity import (
    AggregateFunctionKind,
    ArithmeticOperatorKind,
    ComputedExprSpec,
    ComputedFieldSpec,
)


class TestExpressionEvaluation:
    """Tests for expression evaluation."""

    def test_literal_value(self) -> None:
        """Test evaluating a literal value."""
        expr = ComputedExprSpec(kind="literal", value=42)
        result = evaluate_expression(expr, {})
        assert result == 42

    def test_literal_float(self) -> None:
        """Test evaluating a float literal."""
        expr = ComputedExprSpec(kind="literal", value=0.1)
        result = evaluate_expression(expr, {})
        assert result == 0.1

    def test_field_reference(self) -> None:
        """Test evaluating a simple field reference."""
        expr = ComputedExprSpec(kind="field_ref", path=["amount"])
        result = evaluate_expression(expr, {"amount": 100})
        assert result == 100

    def test_field_reference_decimal(self) -> None:
        """Test evaluating a field reference with Decimal value."""
        expr = ComputedExprSpec(kind="field_ref", path=["price"])
        result = evaluate_expression(expr, {"price": Decimal("99.99")})
        assert result == Decimal("99.99")

    def test_field_reference_missing(self) -> None:
        """Test evaluating a missing field reference."""
        expr = ComputedExprSpec(kind="field_ref", path=["missing"])
        result = evaluate_expression(expr, {"other": 100})
        assert result is None

    def test_arithmetic_addition(self) -> None:
        """Test evaluating addition."""
        expr = ComputedExprSpec(
            kind="arithmetic",
            left=ComputedExprSpec(kind="field_ref", path=["a"]),
            operator=ArithmeticOperatorKind.ADD,
            right=ComputedExprSpec(kind="field_ref", path=["b"]),
        )
        result = evaluate_expression(expr, {"a": 10, "b": 5})
        assert result == 15

    def test_arithmetic_subtraction(self) -> None:
        """Test evaluating subtraction."""
        expr = ComputedExprSpec(
            kind="arithmetic",
            left=ComputedExprSpec(kind="field_ref", path=["a"]),
            operator=ArithmeticOperatorKind.SUBTRACT,
            right=ComputedExprSpec(kind="field_ref", path=["b"]),
        )
        result = evaluate_expression(expr, {"a": 10, "b": 3})
        assert result == 7

    def test_arithmetic_multiplication(self) -> None:
        """Test evaluating multiplication."""
        expr = ComputedExprSpec(
            kind="arithmetic",
            left=ComputedExprSpec(kind="field_ref", path=["quantity"]),
            operator=ArithmeticOperatorKind.MULTIPLY,
            right=ComputedExprSpec(kind="field_ref", path=["price"]),
        )
        result = evaluate_expression(expr, {"quantity": 5, "price": 10.50})
        assert result == 52.5

    def test_arithmetic_division(self) -> None:
        """Test evaluating division."""
        expr = ComputedExprSpec(
            kind="arithmetic",
            left=ComputedExprSpec(kind="field_ref", path=["total"]),
            operator=ArithmeticOperatorKind.DIVIDE,
            right=ComputedExprSpec(kind="field_ref", path=["count"]),
        )
        result = evaluate_expression(expr, {"total": 100, "count": 4})
        assert result == 25

    def test_arithmetic_division_by_zero(self) -> None:
        """Test division by zero returns None."""
        expr = ComputedExprSpec(
            kind="arithmetic",
            left=ComputedExprSpec(kind="literal", value=10),
            operator=ArithmeticOperatorKind.DIVIDE,
            right=ComputedExprSpec(kind="literal", value=0),
        )
        result = evaluate_expression(expr, {})
        assert result is None

    def test_arithmetic_with_literal(self) -> None:
        """Test arithmetic with literal value."""
        expr = ComputedExprSpec(
            kind="arithmetic",
            left=ComputedExprSpec(kind="field_ref", path=["price"]),
            operator=ArithmeticOperatorKind.MULTIPLY,
            right=ComputedExprSpec(kind="literal", value=1.1),
        )
        result = evaluate_expression(expr, {"price": 100})
        assert result == pytest.approx(110)


class TestAggregateEvaluation:
    """Tests for aggregate function evaluation."""

    def test_count_empty(self) -> None:
        """Test count on empty list."""
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.COUNT,
            field=ComputedExprSpec(kind="field_ref", path=["items"]),
        )
        result = evaluate_expression(expr, {}, {"items": []})
        assert result == 0

    def test_count_items(self) -> None:
        """Test count on list of items."""
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.COUNT,
            field=ComputedExprSpec(kind="field_ref", path=["items"]),
        )
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = evaluate_expression(expr, {}, {"items": items})
        assert result == 3

    def test_sum_values(self) -> None:
        """Test sum on field values."""
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.SUM,
            field=ComputedExprSpec(kind="field_ref", path=["items", "amount"]),
        )
        items = [{"amount": 10}, {"amount": 20}, {"amount": 30}]
        result = evaluate_expression(expr, {}, {"items": items})
        assert result == 60

    def test_avg_values(self) -> None:
        """Test average on field values."""
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.AVG,
            field=ComputedExprSpec(kind="field_ref", path=["items", "score"]),
        )
        items = [{"score": 80}, {"score": 90}, {"score": 100}]
        result = evaluate_expression(expr, {}, {"items": items})
        assert result == 90

    def test_min_values(self) -> None:
        """Test min on field values."""
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.MIN,
            field=ComputedExprSpec(kind="field_ref", path=["items", "price"]),
        )
        items = [{"price": 50}, {"price": 25}, {"price": 75}]
        result = evaluate_expression(expr, {}, {"items": items})
        assert result == 25

    def test_max_values(self) -> None:
        """Test max on field values."""
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.MAX,
            field=ComputedExprSpec(kind="field_ref", path=["items", "price"]),
        )
        items = [{"price": 50}, {"price": 25}, {"price": 75}]
        result = evaluate_expression(expr, {}, {"items": items})
        assert result == 75


class TestDateFunctions:
    """Tests for date-based aggregate functions."""

    def test_days_until_future(self) -> None:
        """Test days_until with future date."""
        future_date = date.today() + timedelta(days=10)
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.DAYS_UNTIL,
            field=ComputedExprSpec(kind="field_ref", path=["due_date"]),
        )
        result = evaluate_expression(expr, {"due_date": future_date})
        assert result == 10

    def test_days_until_past(self) -> None:
        """Test days_until with past date (negative result)."""
        past_date = date.today() - timedelta(days=5)
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.DAYS_UNTIL,
            field=ComputedExprSpec(kind="field_ref", path=["due_date"]),
        )
        result = evaluate_expression(expr, {"due_date": past_date})
        assert result == -5

    def test_days_since_past(self) -> None:
        """Test days_since with past date."""
        past_date = date.today() - timedelta(days=7)
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.DAYS_SINCE,
            field=ComputedExprSpec(kind="field_ref", path=["created_at"]),
        )
        result = evaluate_expression(expr, {"created_at": past_date})
        assert result == 7

    def test_days_until_string_date(self) -> None:
        """Test days_until with ISO string date."""
        future_date = (date.today() + timedelta(days=3)).isoformat()
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.DAYS_UNTIL,
            field=ComputedExprSpec(kind="field_ref", path=["due_date"]),
        )
        result = evaluate_expression(expr, {"due_date": future_date})
        assert result == 3

    def test_days_since_datetime(self) -> None:
        """Test days_since with datetime object."""
        # Use date subtraction for consistent test
        past_date = date.today() - timedelta(days=14)
        past_datetime = datetime.combine(past_date, datetime.min.time())
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.DAYS_SINCE,
            field=ComputedExprSpec(kind="field_ref", path=["start_date"]),
        )
        result = evaluate_expression(expr, {"start_date": past_datetime})
        assert result == 14

    def test_days_until_none(self) -> None:
        """Test days_until with None date."""
        expr = ComputedExprSpec(
            kind="aggregate",
            function=AggregateFunctionKind.DAYS_UNTIL,
            field=ComputedExprSpec(kind="field_ref", path=["due_date"]),
        )
        result = evaluate_expression(expr, {"due_date": None})
        assert result is None


class TestComputedFields:
    """Tests for computed field evaluation."""

    def test_evaluate_single_computed_field(self) -> None:
        """Test evaluating a single computed field."""
        computed_fields = [
            ComputedFieldSpec(
                name="total_with_tax",
                expression=ComputedExprSpec(
                    kind="arithmetic",
                    left=ComputedExprSpec(kind="field_ref", path=["total"]),
                    operator=ArithmeticOperatorKind.MULTIPLY,
                    right=ComputedExprSpec(kind="literal", value=1.1),
                ),
            )
        ]

        result = evaluate_computed_fields({"total": 100}, computed_fields)
        assert "total_with_tax" in result
        assert result["total_with_tax"] == pytest.approx(110)

    def test_evaluate_multiple_computed_fields(self) -> None:
        """Test evaluating multiple computed fields."""
        computed_fields = [
            ComputedFieldSpec(
                name="tax",
                expression=ComputedExprSpec(
                    kind="arithmetic",
                    left=ComputedExprSpec(kind="field_ref", path=["subtotal"]),
                    operator=ArithmeticOperatorKind.MULTIPLY,
                    right=ComputedExprSpec(kind="literal", value=0.1),
                ),
            ),
            ComputedFieldSpec(
                name="total",
                expression=ComputedExprSpec(
                    kind="arithmetic",
                    left=ComputedExprSpec(kind="field_ref", path=["subtotal"]),
                    operator=ArithmeticOperatorKind.MULTIPLY,
                    right=ComputedExprSpec(kind="literal", value=1.1),
                ),
            ),
        ]

        result = evaluate_computed_fields({"subtotal": 100}, computed_fields)
        assert result["tax"] == pytest.approx(10)
        assert result["total"] == pytest.approx(110)

    def test_enrich_record(self) -> None:
        """Test enriching a record with computed fields."""
        computed_fields = [
            ComputedFieldSpec(
                name="doubled",
                expression=ComputedExprSpec(
                    kind="arithmetic",
                    left=ComputedExprSpec(kind="field_ref", path=["value"]),
                    operator=ArithmeticOperatorKind.MULTIPLY,
                    right=ComputedExprSpec(kind="literal", value=2),
                ),
            )
        ]

        record = {"id": 1, "value": 25}
        enriched = enrich_record_with_computed_fields(record, computed_fields)

        assert enriched["id"] == 1
        assert enriched["value"] == 25
        assert enriched["doubled"] == 50

    def test_aggregate_with_arithmetic(self) -> None:
        """Test aggregate combined with arithmetic."""
        # sum(items.amount) * 1.1
        computed_fields = [
            ComputedFieldSpec(
                name="total_with_tax",
                expression=ComputedExprSpec(
                    kind="arithmetic",
                    left=ComputedExprSpec(
                        kind="aggregate",
                        function=AggregateFunctionKind.SUM,
                        field=ComputedExprSpec(kind="field_ref", path=["items", "amount"]),
                    ),
                    operator=ArithmeticOperatorKind.MULTIPLY,
                    right=ComputedExprSpec(kind="literal", value=1.1),
                ),
            )
        ]

        items = [{"amount": 10}, {"amount": 20}, {"amount": 30}]
        result = evaluate_computed_fields({}, computed_fields, {"items": items})

        assert result["total_with_tax"] == pytest.approx(66)  # 60 * 1.1
