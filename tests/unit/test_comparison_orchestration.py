"""Pure row-builder for display: comparison orchestration (#1470)."""

from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.http.runtime.workspace_region_computes import (
    build_comparison_inputs,
    build_comparison_rows,
)


def test_desc_ranking_and_bar_fraction() -> None:
    rows, mx = build_comparison_rows(
        [
            {"region": "A", "total": 92},
            {"region": "B", "total": 100},
            {"region": "C", "total": 96},
            {"region": "D", "total": 94},
            {"region": "E", "total": 98},
            {"region": "F", "total": 5},
        ],
        label_key="region",
        value_key="total",
        order="desc",
        outlier_spec=ComparisonOutlierSpec(method="iqr"),
        extra_keys=[],
    )
    assert [r["rank"] for r in rows] == [1, 2, 3, 4, 5, 6]
    assert rows[0]["label"] == "B" and rows[0]["value"] == 100
    assert rows[0]["bar_fraction"] == 1.0
    assert mx == 100
    assert rows[-1]["label"] == "F" and rows[-1]["value"] == 5
    assert rows[-1]["outlier"] == "low"  # 5 is the low outlier vs the tight high pack


def test_asc_ranking() -> None:
    rows, _ = build_comparison_rows(
        [{"k": "A", "v": 30}, {"k": "B", "v": 10}, {"k": "C", "v": 20}],
        label_key="k",
        value_key="v",
        order="asc",
        outlier_spec=ComparisonOutlierSpec(method="none"),
        extra_keys=[],
    )
    assert [r["label"] for r in rows] == ["B", "C", "A"]
    assert [r["rank"] for r in rows] == [1, 2, 3]


def test_extra_keys_columns() -> None:
    rows, _ = build_comparison_rows(
        [{"k": "A", "v": 10, "owner": "Sam"}, {"k": "B", "v": 20, "owner": "Lee"}],
        label_key="k",
        value_key="v",
        order="desc",
        outlier_spec=ComparisonOutlierSpec(method="none"),
        extra_keys=["owner"],
    )
    assert rows[0]["label"] == "B" and rows[0]["columns"] == {"owner": "Lee"}
    assert rows[1]["columns"] == {"owner": "Sam"}


def test_none_values_sort_last_and_zero_fraction() -> None:
    rows, mx = build_comparison_rows(
        [{"k": "A", "v": None}, {"k": "B", "v": 50}, {"k": "C", "v": 100}],
        label_key="k",
        value_key="v",
        order="desc",
        outlier_spec=ComparisonOutlierSpec(method="none"),
        extra_keys=[],
    )
    assert rows[0]["label"] == "C"
    assert rows[-1]["label"] == "A" and rows[-1]["value"] is None
    assert rows[-1]["bar_fraction"] == 0.0
    assert mx == 100


def test_inputs_group_mode_ranks_named_aggregate() -> None:
    # Buckets carry the primary `value` plus per-aggregate `metrics`. rank_by
    # names a specific aggregate → rank by metrics[rank_by], not value.
    buckets = [
        {"label": "North", "value": 1, "metrics": {"orders": 1, "revenue": 50}},
        {"label": "South", "value": 2, "metrics": {"orders": 2, "revenue": 90}},
    ]
    rows, mx = build_comparison_inputs(
        group_by="region",
        bucketed_metrics=buckets,
        items=[],
        columns=[],
        rank_by="revenue",
        order="desc",
        outlier_spec=ComparisonOutlierSpec(method="none"),
    )
    assert [r["label"] for r in rows] == ["South", "North"]
    assert rows[0]["value"] == 90 and mx == 90


def test_inputs_entity_row_mode() -> None:
    items = [
        {"id": "1", "name": "Alpha", "score": 10, "owner": "Sam"},
        {"id": "2", "name": "Beta", "score": 30, "owner": "Lee"},
    ]
    columns = [{"key": "name"}, {"key": "score"}, {"key": "owner"}]
    rows, _ = build_comparison_inputs(
        group_by=None,
        bucketed_metrics=[],
        items=items,
        columns=columns,
        rank_by="score",
        order="desc",
        outlier_spec=ComparisonOutlierSpec(method="none"),
    )
    assert rows[0]["label"] == "Beta" and rows[0]["value"] == 30
    assert rows[0]["columns"] == {"owner": "Lee"}  # label=name, value=score, extra=owner


def test_empty_records() -> None:
    rows, mx = build_comparison_rows(
        [],
        label_key="k",
        value_key="v",
        order="desc",
        outlier_spec=ComparisonOutlierSpec(method="iqr"),
        extra_keys=[],
    )
    assert rows == [] and mx == 0.0
