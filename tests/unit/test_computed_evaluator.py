"""Tests for computed field evaluator (#coverage)."""

from decimal import Decimal

import pytest

from dazzle.http.runtime.computed_evaluator import (
    enrich_record_with_computed_fields,
    enrich_records_with_computed_fields,
    evaluate_computed_fields,
    evaluate_expression,
)
from dazzle.http.specs.entity import (
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

    def test_string_numeric_coercion(self) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=["price"])
        assert evaluate_expression(expr, {"price": "49.99"}) == 49.99

    def test_decimal_field(self) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=["total"])
        assert evaluate_expression(expr, {"total": Decimal("10.50")}) == Decimal("10.50")

    @pytest.mark.parametrize(
        "path,record",
        [
            (["missing"], {"amount": 100}),
            (["name"], {"name": "hello"}),
            ([], {"x": 1}),
            (["items", "amount"], {"items": [{"amount": 10}]}),
        ],
        ids=[
            "test_missing_field",
            "test_non_numeric_string",
            "test_empty_path",
            "test_multi_segment_path_returns_none",
        ],
    )
    def test_field_ref_returns_none(self, path: list[str], record: dict) -> None:
        expr = ComputedExprSpec(kind="field_ref", path=path)
        assert evaluate_expression(expr, record) is None


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


class TestAggregateExpression:
    """Test aggregate function evaluation over related record sets."""

    def _agg(self, func: AggregateFunctionKind, path: list[str]) -> ComputedExprSpec:
        return ComputedExprSpec(
            kind="aggregate",
            function=func,
            field=ComputedExprSpec(kind="field_ref", path=path),
        )

    @pytest.mark.parametrize(
        "func,path,related,expected",
        [
            (  # test_count
                AggregateFunctionKind.COUNT,
                ["items"],
                {"items": [{"id": 1}, {"id": 2}, {"id": 3}]},
                3,
            ),
            (  # test_count_empty
                AggregateFunctionKind.COUNT,
                ["items"],
                {"items": []},
                0,
            ),
            (  # test_sum
                AggregateFunctionKind.SUM,
                ["items", "amount"],
                {"items": [{"amount": 10}, {"amount": 20}, {"amount": 30}]},
                60,
            ),
            (  # test_avg
                AggregateFunctionKind.AVG,
                ["items", "price"],
                {"items": [{"price": 10}, {"price": 20}]},
                15.0,
            ),
            (  # test_min
                AggregateFunctionKind.MIN,
                ["scores", "value"],
                {"scores": [{"value": 5}, {"value": 2}, {"value": 8}]},
                2,
            ),
            (  # test_max
                AggregateFunctionKind.MAX,
                ["scores", "value"],
                {"scores": [{"value": 5}, {"value": 2}, {"value": 8}]},
                8,
            ),
            (  # test_sum_empty_items: SUM over empty list returns None
                AggregateFunctionKind.SUM,
                ["items", "amount"],
                {"items": []},
                None,
            ),
            (  # test_sum_with_none_values: None values are skipped
                AggregateFunctionKind.SUM,
                ["items", "amount"],
                {"items": [{"amount": 10}, {"amount": None}, {"amount": 30}]},
                40,
            ),
            (  # test_sum_with_string_values: numeric strings are coerced
                AggregateFunctionKind.SUM,
                ["items", "amount"],
                {"items": [{"amount": "10"}, {"amount": "20"}]},
                30.0,
            ),
            (  # test_missing_relation: missing key returns 0 for COUNT
                AggregateFunctionKind.COUNT,
                ["nonexistent"],
                {},
                0,
            ),
        ],
        ids=[
            "test_count",
            "test_count_empty",
            "test_sum",
            "test_avg",
            "test_min",
            "test_max",
            "test_sum_empty_items",
            "test_sum_with_none_values",
            "test_sum_with_string_values",
            "test_missing_relation",
        ],
    )
    def test_aggregate_expression(
        self,
        func: AggregateFunctionKind,
        path: list[str],
        related: dict,
        expected: object,
    ) -> None:
        expr = self._agg(func, path)
        assert evaluate_expression(expr, {}, related) == expected

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

    @pytest.mark.parametrize(
        ("func", "field", "offset_days", "make_value", "expected"),
        [
            (
                AggregateFunctionKind.DAYS_UNTIL,
                "due_date",
                10,
                lambda d: d.isoformat(),
                10,
            ),
            (
                AggregateFunctionKind.DAYS_SINCE,
                "created",
                -7,
                lambda d: d.isoformat(),
                7,
            ),
            (
                AggregateFunctionKind.DAYS_UNTIL,
                "deadline",
                5,
                lambda d: f"{d.isoformat()}T12:00:00Z",
                5,
            ),
            (
                AggregateFunctionKind.DAYS_UNTIL,
                "due",
                3,
                lambda d: d,
                3,
            ),
        ],
        ids=[
            "test_days_until_future",
            "test_days_since_past",
            "test_days_until_with_datetime_string",
            "test_days_until_with_date_object",
        ],
    )
    def test_date_function(
        self,
        func: AggregateFunctionKind,
        field: str,
        offset_days: int,
        make_value: object,
        expected: int,
    ) -> None:
        from datetime import date, timedelta

        target_date = date.today() + timedelta(days=offset_days)
        expr = self._date_agg(func, field)
        result = evaluate_expression(expr, {field: make_value(target_date)})
        assert result == expected

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
