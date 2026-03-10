"""Tests for computed field evaluator (#coverage)."""

from __future__ import annotations

from decimal import Decimal

from dazzle_back.runtime.computed_evaluator import (
    enrich_record_with_computed_fields,
    enrich_records_with_computed_fields,
    evaluate_computed_fields,
    evaluate_expression,
)
from dazzle_back.specs.entity import (
    AggregateFunctionKind,
    ArithmeticOperatorKind,
    ComputedExprSpec,
    ComputedFieldSpec,
)

# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------


class TestLiteralExpression:
    def test_integer_literal(self) -> None:
        expr = ComputedExprSpec(kind="literal", value=42)
        assert evaluate_expression(expr, {}) == 42

    def test_float_literal(self) -> None:
        expr = ComputedExprSpec(kind="literal", value=3.14)
        assert evaluate_expression(expr, {}) == 3.14

    def test_none_literal(self) -> None:
        expr = ComputedExprSpec(kind="literal", value=None)
        assert evaluate_expression(expr, {}) is None


# ---------------------------------------------------------------------------
# Field references
# ---------------------------------------------------------------------------


class TestFieldRefExpression:
    def test_simple_field(self) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=["amount"])
        assert evaluate_expression(expr, {"amount": 100}) == 100

    def test_missing_field(self) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=["missing"])
        assert evaluate_expression(expr, {"amount": 100}) is None

    def test_string_numeric_coercion(self) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=["price"])
        assert evaluate_expression(expr, {"price": "49.99"}) == 49.99

    def test_non_numeric_string(self) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=["name"])
        assert evaluate_expression(expr, {"name": "hello"}) is None

    def test_decimal_field(self) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=["total"])
        assert evaluate_expression(expr, {"total": Decimal("10.50")}) == Decimal("10.50")

    def test_empty_path(self) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=[])
        assert evaluate_expression(expr, {"x": 1}) is None

    def test_multi_segment_path_returns_none(self) -> None:
        """Multi-segment paths are for aggregates, not direct field refs."""
        expr = ComputedExprSpec(kind="field_ref", path=["items", "amount"])
        assert evaluate_expression(expr, {"items": [{"amount": 10}]}) is None


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


class TestAggregateExpression:
    def _agg(self, func: AggregateFunctionKind, path: list[str]) -> ComputedExprSpec:
        return ComputedExprSpec(
            kind="aggregate",
            function=func,
            field=ComputedExprSpec(kind="field_ref", path=path),
        )

    def test_count(self) -> None:
        expr = self._agg(AggregateFunctionKind.COUNT, ["items"])
        related = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
        assert evaluate_expression(expr, {}, related) == 3

    def test_count_empty(self) -> None:
        expr = self._agg(AggregateFunctionKind.COUNT, ["items"])
        assert evaluate_expression(expr, {}, {"items": []}) == 0

    def test_sum(self) -> None:
        expr = self._agg(AggregateFunctionKind.SUM, ["items", "amount"])
        related = {"items": [{"amount": 10}, {"amount": 20}, {"amount": 30}]}
        assert evaluate_expression(expr, {}, related) == 60

    def test_avg(self) -> None:
        expr = self._agg(AggregateFunctionKind.AVG, ["items", "price"])
        related = {"items": [{"price": 10}, {"price": 20}]}
        assert evaluate_expression(expr, {}, related) == 15.0

    def test_min(self) -> None:
        expr = self._agg(AggregateFunctionKind.MIN, ["scores", "value"])
        related = {"scores": [{"value": 5}, {"value": 2}, {"value": 8}]}
        assert evaluate_expression(expr, {}, related) == 2

    def test_max(self) -> None:
        expr = self._agg(AggregateFunctionKind.MAX, ["scores", "value"])
        related = {"scores": [{"value": 5}, {"value": 2}, {"value": 8}]}
        assert evaluate_expression(expr, {}, related) == 8

    def test_sum_empty_items(self) -> None:
        expr = self._agg(AggregateFunctionKind.SUM, ["items", "amount"])
        assert evaluate_expression(expr, {}, {"items": []}) is None

    def test_sum_with_none_values(self) -> None:
        expr = self._agg(AggregateFunctionKind.SUM, ["items", "amount"])
        related = {"items": [{"amount": 10}, {"amount": None}, {"amount": 30}]}
        assert evaluate_expression(expr, {}, related) == 40

    def test_sum_with_string_values(self) -> None:
        expr = self._agg(AggregateFunctionKind.SUM, ["items", "amount"])
        related = {"items": [{"amount": "10"}, {"amount": "20"}]}
        assert evaluate_expression(expr, {}, related) == 30.0

    def test_missing_relation(self) -> None:
        expr = self._agg(AggregateFunctionKind.COUNT, ["nonexistent"])
        assert evaluate_expression(expr, {}, {}) == 0

    def test_no_function(self) -> None:
        expr = ComputedExprSpec(kind="aggregate", function=None, field=None)
        assert evaluate_expression(expr, {}) is None


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


class TestArithmeticExpression:
    def _arith(
        self,
        op: ArithmeticOperatorKind,
        left: ComputedExprSpec,
        right: ComputedExprSpec,
    ) -> ComputedExprSpec:
        return ComputedExprSpec(kind="arithmetic", left=left, right=right, operator=op)

    def test_add(self) -> None:
        expr = self._arith(
            ArithmeticOperatorKind.ADD,
            ComputedExprSpec(kind="field_ref", path=["a"]),
            ComputedExprSpec(kind="field_ref", path=["b"]),
        )
        assert evaluate_expression(expr, {"a": 10, "b": 5}) == 15.0

    def test_subtract(self) -> None:
        expr = self._arith(
            ArithmeticOperatorKind.SUBTRACT,
            ComputedExprSpec(kind="literal", value=100),
            ComputedExprSpec(kind="field_ref", path=["discount"]),
        )
        assert evaluate_expression(expr, {"discount": 15}) == 85.0

    def test_multiply(self) -> None:
        expr = self._arith(
            ArithmeticOperatorKind.MULTIPLY,
            ComputedExprSpec(kind="field_ref", path=["price"]),
            ComputedExprSpec(kind="literal", value=0.1),
        )
        result = evaluate_expression(expr, {"price": 200})
        assert result is not None
        assert abs(result - 20.0) < 0.001

    def test_divide(self) -> None:
        expr = self._arith(
            ArithmeticOperatorKind.DIVIDE,
            ComputedExprSpec(kind="field_ref", path=["total"]),
            ComputedExprSpec(kind="literal", value=4),
        )
        assert evaluate_expression(expr, {"total": 100}) == 25.0

    def test_divide_by_zero(self) -> None:
        expr = self._arith(
            ArithmeticOperatorKind.DIVIDE,
            ComputedExprSpec(kind="literal", value=10),
            ComputedExprSpec(kind="literal", value=0),
        )
        assert evaluate_expression(expr, {}) is None

    def test_none_operand(self) -> None:
        expr = self._arith(
            ArithmeticOperatorKind.ADD,
            ComputedExprSpec(kind="field_ref", path=["missing"]),
            ComputedExprSpec(kind="literal", value=5),
        )
        assert evaluate_expression(expr, {}) is None

    def test_missing_parts(self) -> None:
        expr = ComputedExprSpec(kind="arithmetic", left=None, right=None, operator=None)
        assert evaluate_expression(expr, {}) is None


# ---------------------------------------------------------------------------
# Unknown kind
# ---------------------------------------------------------------------------


class TestUnknownKind:
    def test_returns_none(self) -> None:
        from unittest.mock import MagicMock

        expr = MagicMock()
        expr.kind = "unknown_kind"
        assert evaluate_expression(expr, {}) is None


# ---------------------------------------------------------------------------
# Date functions
# ---------------------------------------------------------------------------


class TestDateFunctions:
    def _date_agg(self, func: AggregateFunctionKind, field: str) -> ComputedExprSpec:
        return ComputedExprSpec(
            kind="aggregate",
            function=func,
            field=ComputedExprSpec(kind="field_ref", path=[field]),
        )

    def test_days_until_future(self) -> None:
        from datetime import date, timedelta

        future = date.today() + timedelta(days=10)
        expr = self._date_agg(AggregateFunctionKind.DAYS_UNTIL, "due_date")
        result = evaluate_expression(expr, {"due_date": future.isoformat()})
        assert result == 10

    def test_days_since_past(self) -> None:
        from datetime import date, timedelta

        past = date.today() - timedelta(days=7)
        expr = self._date_agg(AggregateFunctionKind.DAYS_SINCE, "created")
        result = evaluate_expression(expr, {"created": past.isoformat()})
        assert result == 7

    def test_days_until_with_datetime_string(self) -> None:
        from datetime import date, timedelta

        future = date.today() + timedelta(days=5)
        expr = self._date_agg(AggregateFunctionKind.DAYS_UNTIL, "deadline")
        result = evaluate_expression(expr, {"deadline": f"{future.isoformat()}T12:00:00Z"})
        assert result == 5

    def test_days_until_with_date_object(self) -> None:
        from datetime import date, timedelta

        future = date.today() + timedelta(days=3)
        expr = self._date_agg(AggregateFunctionKind.DAYS_UNTIL, "due")
        assert evaluate_expression(expr, {"due": future}) == 3

    def test_days_with_none_value(self) -> None:
        expr = self._date_agg(AggregateFunctionKind.DAYS_UNTIL, "due")
        assert evaluate_expression(expr, {"due": None}) is None

    def test_days_with_invalid_string(self) -> None:
        expr = self._date_agg(AggregateFunctionKind.DAYS_UNTIL, "due")
        assert evaluate_expression(expr, {"due": "not-a-date"}) is None


# ---------------------------------------------------------------------------
# High-level: evaluate_computed_fields / enrich
# ---------------------------------------------------------------------------


class TestComputedFieldEvaluation:
    def test_evaluate_computed_fields(self) -> None:
        fields = [
            ComputedFieldSpec(
                name="tax",
                expression=ComputedExprSpec(
                    kind="arithmetic",
                    left=ComputedExprSpec(kind="field_ref", path=["subtotal"]),
                    right=ComputedExprSpec(kind="literal", value=0.1),
                    operator=ArithmeticOperatorKind.MULTIPLY,
                ),
            ),
        ]
        result = evaluate_computed_fields({"subtotal": 200}, fields)
        assert abs(result["tax"] - 20.0) < 0.001

    def test_enrich_record(self) -> None:
        fields = [
            ComputedFieldSpec(
                name="total",
                expression=ComputedExprSpec(kind="field_ref", path=["amount"]),
            ),
        ]
        enriched = enrich_record_with_computed_fields({"id": "1", "amount": 50}, fields)
        assert enriched["id"] == "1"
        assert enriched["amount"] == 50
        assert enriched["total"] == 50

    def test_enrich_records_empty_fields(self) -> None:
        records = [{"id": "1"}, {"id": "2"}]
        result = enrich_records_with_computed_fields(records, [])
        assert result == records

    def test_enrich_records_with_related_data(self) -> None:
        fields = [
            ComputedFieldSpec(
                name="item_count",
                expression=ComputedExprSpec(
                    kind="aggregate",
                    function=AggregateFunctionKind.COUNT,
                    field=ComputedExprSpec(kind="field_ref", path=["items"]),
                ),
            ),
        ]
        records = [{"id": "r1"}, {"id": "r2"}]
        related_map = {
            "r1": {"items": [{"x": 1}, {"x": 2}]},
            "r2": {"items": [{"x": 1}]},
        }
        result = enrich_records_with_computed_fields(records, fields, related_map)
        assert result[0]["item_count"] == 2
        assert result[1]["item_count"] == 1
