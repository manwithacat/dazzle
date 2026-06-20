"""#1359 slice 1: derived metrics — IR, parser, KPI evaluation.

`completion_rate: round(done / total * 100)` — arithmetic over metric names
declared earlier in the same `aggregate:` block. Evaluated in Python after
the scope-filtered aggregate queries; zero extra queries.
"""

from pathlib import Path

import pytest

from dazzle.core.errors import ParseError
from dazzle.core.ir import DerivedMetric, DerivedMetricExpr
from dazzle.core.parser import parse_modules
from dazzle.http.runtime.workspace_aggregation import (
    _evaluate_derived_expr,
    _evaluate_derived_metrics,
)

WORKSPACE_TEMPLATE = """module t

app t "T"

entity Task "Task":
  id: uuid pk
  status: enum[todo,done]=todo

workspace dash "Dash":
  purpose: "x"
  stage: "command_center"

  task_metrics:
    source: Task
    display: metrics
    aggregate:
{metrics}
"""


def _parse_region(tmp_path: Path, metric_lines: list[str]):
    metrics = "\n".join(f"      {line}" for line in metric_lines)
    f = tmp_path / "app.dsl"
    f.write_text(WORKSPACE_TEMPLATE.format(metrics=metrics), encoding="utf-8")
    (module,) = parse_modules([f])
    return module.fragment.workspaces[0].regions[0]


class TestParsing:
    def test_demand_case_parses(self, tmp_path: Path) -> None:
        region = _parse_region(
            tmp_path,
            [
                "total: count(Task)",
                "done: count(Task where status = done)",
                "completion_rate: round(done / total * 100)",
            ],
        )
        derived = region.aggregates["completion_rate"]
        assert isinstance(derived, DerivedMetric)
        assert set(derived.referenced_metrics()) == {"done", "total"}
        # The plain aggregates are untouched.
        assert not isinstance(region.aggregates["total"], DerivedMetric)

    def test_derived_may_reference_earlier_derived(self, tmp_path: Path) -> None:
        region = _parse_region(
            tmp_path,
            [
                "total: count(Task)",
                "half: total / 2",
                "quarter: half / 2",
            ],
        )
        assert isinstance(region.aggregates["quarter"], DerivedMetric)

    def test_unknown_metric_name_errors_with_declared_list(self, tmp_path: Path) -> None:
        with pytest.raises(ParseError, match="declared so far: total"):
            _parse_region(
                tmp_path,
                ["total: count(Task)", "rate: done / total"],
            )

    def test_forward_reference_rejected(self, tmp_path: Path) -> None:
        # `rate` references `done`, which is declared LATER — order matters.
        with pytest.raises(ParseError, match="EARLIER"):
            _parse_region(
                tmp_path,
                [
                    "total: count(Task)",
                    "rate: done / total",
                    "done: count(Task where status = done)",
                ],
            )

    def test_unknown_function_errors(self, tmp_path: Path) -> None:
        with pytest.raises(ParseError, match="unknown derived-metric function 'sqrt'"):
            _parse_region(
                tmp_path,
                ["total: count(Task)", "x: sqrt(total)"],
            )


class TestEvaluation:
    def _derived(self, *lines: str, tmp_path: Path) -> dict:
        return {}

    def test_ratio_with_round(self) -> None:
        expr = DerivedMetricExpr(
            function_name="round",
            function_args=(
                DerivedMetricExpr(
                    binary_op="*",
                    binary_left=DerivedMetricExpr(
                        binary_op="/",
                        binary_left=DerivedMetricExpr(metric_name="done"),
                        binary_right=DerivedMetricExpr(metric_name="total"),
                    ),
                    binary_right=DerivedMetricExpr(number_literal=100),
                ),
            ),
        )
        assert _evaluate_derived_expr(expr, {"done": 3, "total": 4}) == 75

    def test_division_by_zero_yields_zero(self) -> None:
        expr = DerivedMetricExpr(
            binary_op="/",
            binary_left=DerivedMetricExpr(metric_name="done"),
            binary_right=DerivedMetricExpr(metric_name="total"),
        )
        assert _evaluate_derived_expr(expr, {"done": 5, "total": 0}) == 0

    def test_missing_reference_coerces_to_zero(self) -> None:
        expr = DerivedMetricExpr(metric_name="ghost")
        assert _evaluate_derived_expr(expr, {}) == 0

    def test_round_two_args(self) -> None:
        expr = DerivedMetricExpr(
            function_name="round",
            function_args=(
                DerivedMetricExpr(number_literal=2.345),
                DerivedMetricExpr(number_literal=1),
            ),
        )
        assert _evaluate_derived_expr(expr, {}) == 2.3

    def test_ordered_pass_resolves_chains(self) -> None:
        aggregates = {
            "half": DerivedMetric(
                expression=DerivedMetricExpr(
                    binary_op="/",
                    binary_left=DerivedMetricExpr(metric_name="total"),
                    binary_right=DerivedMetricExpr(number_literal=2),
                )
            ),
            "quarter": DerivedMetric(
                expression=DerivedMetricExpr(
                    binary_op="/",
                    binary_left=DerivedMetricExpr(metric_name="half"),
                    binary_right=DerivedMetricExpr(number_literal=2),
                )
            ),
        }
        results = {"total": 100}
        _evaluate_derived_metrics(aggregates, results, ["half", "quarter"])
        assert results["half"] == 50
        assert results["quarter"] == 25


class TestPerBucketEvaluation:
    """#1359 slice 2: derived metrics in grouped charts evaluate per bucket."""

    def test_derived_applied_to_each_bucket_row(self) -> None:
        from dazzle.http.runtime.workspace_aggregation import _apply_derived_to_bucket_rows

        aggregates = {
            "total": object(),  # stands in for AggregateRef — only DerivedMetric is read
            "done": object(),
            "rate": DerivedMetric(
                expression=DerivedMetricExpr(
                    function_name="round",
                    function_args=(
                        DerivedMetricExpr(
                            binary_op="*",
                            binary_left=DerivedMetricExpr(
                                binary_op="/",
                                binary_left=DerivedMetricExpr(metric_name="done"),
                                binary_right=DerivedMetricExpr(metric_name="total"),
                            ),
                            binary_right=DerivedMetricExpr(number_literal=100),
                        ),
                    ),
                )
            ),
        }
        rows = [
            {"label": "alpha", "value": 4, "metrics": {"total": 4, "done": 3}},
            {"label": "beta", "value": 10, "metrics": {"total": 10, "done": 0}},
            {"label": "empty", "value": 0, "metrics": {"total": 0, "done": 0}},
        ]
        _apply_derived_to_bucket_rows(aggregates, rows)
        assert rows[0]["metrics"]["rate"] == 75
        assert rows[1]["metrics"]["rate"] == 0
        assert rows[2]["metrics"]["rate"] == 0  # division by zero → 0, per bucket

    def test_no_derived_entries_is_a_noop(self) -> None:
        from dazzle.http.runtime.workspace_aggregation import _apply_derived_to_bucket_rows

        rows = [{"label": "a", "value": 1, "metrics": {"n": 1}}]
        _apply_derived_to_bucket_rows({"n": object()}, rows)
        assert rows == [{"label": "a", "value": 1, "metrics": {"n": 1}}]

    def test_chained_derived_per_bucket(self) -> None:
        from dazzle.http.runtime.workspace_aggregation import _apply_derived_to_bucket_rows

        aggregates = {
            "total": object(),
            "half": DerivedMetric(
                expression=DerivedMetricExpr(
                    binary_op="/",
                    binary_left=DerivedMetricExpr(metric_name="total"),
                    binary_right=DerivedMetricExpr(number_literal=2),
                )
            ),
            "quarter": DerivedMetric(
                expression=DerivedMetricExpr(
                    binary_op="/",
                    binary_left=DerivedMetricExpr(metric_name="half"),
                    binary_right=DerivedMetricExpr(number_literal=2),
                )
            ),
        }
        rows = [{"label": "a", "value": 100, "metrics": {"total": 100}}]
        _apply_derived_to_bucket_rows(aggregates, rows)
        assert rows[0]["metrics"]["half"] == 50
        assert rows[0]["metrics"]["quarter"] == 25
