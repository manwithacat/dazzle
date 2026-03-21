"""Tests for workspace layout preferences and col_span grid system."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _skip_if_missing() -> None:
    pytest.importorskip("pydantic")


class TestColSpanDefaults:
    """Each stage assigns correct default col_span values."""

    def test_focus_metric_first_region_full_width(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("focus_metric", region_count=3)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].col_span == 12
        assert ctx.regions[1].col_span == 6
        assert ctx.regions[2].col_span == 6

    def test_dual_pane_flow_all_half(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("dual_pane_flow", region_count=2)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].col_span == 6
        assert ctx.regions[1].col_span == 6

    def test_scanner_table_all_full(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("scanner_table", region_count=2)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].col_span == 12
        assert ctx.regions[1].col_span == 12

    def test_monitor_wall_all_half(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("monitor_wall", region_count=4)
        ctx = build_workspace_context(ws)
        for r in ctx.regions:
            assert r.col_span == 6

    def test_command_center_cycle(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("command_center", region_count=6)
        ctx = build_workspace_context(ws)
        spans = [r.col_span for r in ctx.regions]
        assert spans == [12, 6, 6, 4, 4, 4]

    def test_no_stage_defaults_to_12(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("", region_count=2)
        ctx = build_workspace_context(ws)
        for r in ctx.regions:
            assert r.col_span == 12


def _make_workspace(stage: str, region_count: int = 3) -> object:
    from types import SimpleNamespace

    regions = []
    for i in range(region_count):
        regions.append(
            SimpleNamespace(
                name=f"region_{i}",
                source=f"Entity{i}",
                sources=[],
                display="LIST",
                filter=None,
                sort=[],
                limit=None,
                action=None,
                group_by=None,
                aggregates={},
                date_field=None,
                date_range=False,
                heatmap_rows=None,
                heatmap_columns=None,
                heatmap_value=None,
                heatmap_thresholds=None,
                progress_stages=None,
                progress_complete_at=None,
                empty_message=None,
                source_filters=None,
            )
        )
    return SimpleNamespace(
        name="test_workspace",
        title="Test Workspace",
        purpose="",
        stage=stage,
        regions=regions,
        nav_groups=[],
        context_selector=None,
        sse_url="",
        fold_count=None,
        access=None,
    )
