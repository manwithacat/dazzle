"""Insight summary must not dump aggregate key ``count`` as English (oral #152)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir import AggregateRef
from dazzle.core.ir.workspaces import ComparisonOutlierSpec, DisplayMode, WorkspaceRegion
from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_computes import build_insight_inputs
from dazzle.render.fragment.insight import (
    clerk_insight_group_noun,
    clerk_insight_measure_noun,
)
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeInsight:
    name = "alert_insight"
    title = "Alert insight"
    display = "insight_summary"
    empty_message = "No alerts"


_SPEC = ComparisonOutlierSpec(method="iqr")


def test_ops_dashboard_alert_insight_is_count_by_system() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    region = None
    for ws in spec.workspaces:
        for r in ws.regions:
            if r.name == "alert_insight":
                region = r
                break
    assert region is not None
    gb = getattr(region, "group_by", None)
    assert gb == "system" or getattr(gb, "field", None) == "system"
    aggs = getattr(region, "aggregates", None) or {}
    assert "count" in aggs
    ref = aggs["count"]
    assert getattr(ref, "func", None) == "count"
    assert getattr(ref, "entity", None) == "Alert"


def test_count_aggregate_uses_entity_plural_not_key() -> None:
    assert clerk_insight_measure_noun("count", "count", "Alert") == "alerts"
    assert clerk_insight_measure_noun("count", "count", "Invoice") == "invoices"
    assert clerk_insight_measure_noun("count") == "items"


def test_named_measure_is_clerk_lowercased() -> None:
    assert clerk_insight_measure_noun("open_invoices", "sum", "") == "open invoices"


def test_leftover_measure_stays_put() -> None:
    assert clerk_insight_measure_noun("zzz", "count", "Alert") == "zzz"
    assert clerk_insight_measure_noun("2abc", "count", "Alert") == "2abc"


def test_group_noun_pluralizes_field() -> None:
    assert clerk_insight_group_noun("system") == "systems"
    assert clerk_insight_group_noun("service_type") == "service types"
    assert clerk_insight_group_noun("zzz") == "zzz"


def test_build_insight_inputs_narrates_alerts_not_count() -> None:
    region = WorkspaceRegion(
        name="ins",
        display=DisplayMode.INSIGHT_SUMMARY,
        group_by="system",
        aggregates={"count": AggregateRef(func="count", entity="Alert")},
    )
    buckets = [
        {"label": "Auth", "value": 8, "metrics": {"count": 8}},
        {"label": "Billing", "value": 4, "metrics": {"count": 4}},
        {"label": "zzz", "value": 1, "metrics": {"count": 1}},
    ]
    nar = build_insight_inputs(
        buckets,
        region=region,
        group_label=clerk_insight_group_noun("system"),
        scope_desc=f"across all {clerk_insight_group_noun('system')}",
        outlier_spec=_SPEC,
    )
    joined = " ".join(nar.lines)
    assert "13 alerts across 3 systems" in joined
    assert " count " not in f" {joined} "
    assert "across 3 system." not in joined
    assert ("zzz", 1.0) in nar.citations


def test_insight_html_shows_alerts_not_count_token() -> None:
    region = WorkspaceRegion(
        name="ins",
        display=DisplayMode.INSIGHT_SUMMARY,
        group_by="system",
        aggregates={"count": AggregateRef(func="count", entity="Alert")},
    )
    buckets = [
        {"label": "Auth", "value": 8, "metrics": {"count": 8}},
        {"label": "zzz", "value": 1, "metrics": {"count": 1}},
    ]
    nar = build_insight_inputs(
        buckets,
        region=region,
        group_label=clerk_insight_group_noun("system"),
        scope_desc="across all systems",
        outlier_spec=_SPEC,
    )
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeInsight(),
            {"insight_narrative": nar, "empty_message": "No alerts"},
        )
    )
    assert "alerts across" in html
    assert ">count<" not in html
    assert " 9 count " not in html
    assert "zzz" in html
    assert "No alerts" not in html
