from dazzle.core.ir import AggregateRef
from dazzle.core.ir.workspaces import ComparisonOutlierSpec, DisplayMode, WorkspaceRegion
from dazzle.http.runtime.workspace_region_computes import build_insight_inputs

_SPEC = ComparisonOutlierSpec(method="iqr")


def _region(aggregates):
    return WorkspaceRegion(
        name="ins", display=DisplayMode.INSIGHT_SUMMARY, group_by="team", aggregates=aggregates
    )


def test_build_insight_inputs_picks_first_aggregate() -> None:
    region = _region({"count": AggregateRef(func="count", entity="Alert")})
    buckets = [
        {"label": "Platform", "value": 12, "metrics": {"count": 12}},
        {"label": "ML", "value": 1, "metrics": {"count": 1}},
    ]
    nar = build_insight_inputs(
        buckets,
        region=region,
        group_label="teams",
        scope_desc="across all teams",
        outlier_spec=_SPEC,
    )
    assert nar.lines and "across 2 teams" in " ".join(nar.lines)
    assert ("Platform", 12.0) in nar.citations


def test_funcless_aggregate_treated_non_additive() -> None:
    # A DerivedMetric has no `.func` → must NOT claim a "% of total".
    from dazzle.core.ir.aggregates import DerivedMetric, DerivedMetricExpr

    region = _region({"rate": DerivedMetric(expression=DerivedMetricExpr(metric_name="count"))})
    buckets = [
        {"label": "A", "value": 80, "metrics": {"rate": 80}},
        {"label": "B", "value": 20, "metrics": {"rate": 20}},
    ]
    nar = build_insight_inputs(
        buckets,
        region=region,
        group_label="teams",
        scope_desc="across all teams",
        outlier_spec=_SPEC,
    )
    assert "%" not in " ".join(nar.lines)


def test_prefers_aggregate_with_func_over_derived() -> None:
    # When both a DerivedMetric and an AggregateRef are present, narrate the AggregateRef.
    from dazzle.core.ir.aggregates import DerivedMetric, DerivedMetricExpr

    region = _region(
        {
            "rate": DerivedMetric(expression=DerivedMetricExpr(metric_name="count")),
            "count": AggregateRef(func="count", entity="Alert"),
        }
    )
    buckets = [
        {"label": "A", "value": 0, "metrics": {"rate": 99, "count": 8}},
        {"label": "B", "value": 0, "metrics": {"rate": 1, "count": 2}},
    ]
    nar = build_insight_inputs(
        buckets,
        region=region,
        group_label="teams",
        scope_desc="across all teams",
        outlier_spec=_SPEC,
    )
    # count is additive → narrates "10 ... across" with a %, and cites the count values.
    assert "10" in " ".join(nar.lines) and "%" in " ".join(nar.lines)
    assert ("A", 8.0) in nar.citations
