"""Tests for workspace layout preferences and col_span grid system."""

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

    def test_kanban_always_full_width(self) -> None:
        """Kanban regions should be col_span=12 regardless of stage defaults."""
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("command_center", region_count=4)
        # Override region 3 (which would normally get col_span=4) to KANBAN
        ws.regions[3].display = "KANBAN"
        ctx = build_workspace_context(ws)
        assert ctx.regions[3].col_span == 12

    def test_no_stage_defaults_to_12(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("", region_count=2)
        ctx = build_workspace_context(ws)
        for r in ctx.regions:
            assert r.col_span == 12


class TestApplyLayoutPreferences:
    """apply_layout_preferences merges user layout delta with DSL defaults."""

    def _make_ctx(self, region_count: int = 3) -> object:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("scanner_table", region_count=region_count)
        return build_workspace_context(ws)

    def test_no_preference_returns_unchanged(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        result = apply_layout_preferences(ctx, {})
        assert result is ctx

    def test_reorder_regions(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        original_names = [r.name for r in ctx.regions]
        reversed_order = list(reversed(original_names))
        prefs = {f"workspace.{ctx.name}.layout": json.dumps({"order": reversed_order})}
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == reversed_order

    def test_hidden_regions_flagged(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        prefs = {f"workspace.{ctx.name}.layout": json.dumps({"hidden": ["region_1"]})}
        result = apply_layout_preferences(ctx, prefs)
        assert result.regions[0].hidden is False
        assert result.regions[1].hidden is True
        assert result.regions[2].hidden is False

    def test_width_overrides(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        prefs = {
            f"workspace.{ctx.name}.layout": json.dumps({"widths": {"region_0": 4, "region_1": 8}})
        }
        result = apply_layout_preferences(ctx, prefs)
        assert result.regions[0].col_span == 4
        assert result.regions[1].col_span == 8
        assert result.regions[2].col_span == 12  # scanner_table default

    def test_deleted_dsl_region_dropped(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(2)
        prefs = {
            f"workspace.{ctx.name}.layout": json.dumps(
                {"order": ["region_0", "ghost_region", "region_1"]}
            )
        }
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == ["region_0", "region_1"]

    def test_new_dsl_region_appended(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        prefs = {f"workspace.{ctx.name}.layout": json.dumps({"order": ["region_0", "region_1"]})}
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == ["region_0", "region_1", "region_2"]

    def test_fold_count_skips_hidden_regions(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        prefs = {f"workspace.{ctx.name}.layout": json.dumps({"hidden": ["region_0"]})}
        result = apply_layout_preferences(ctx, prefs)
        # hidden regions should not affect fold_count (fold_count is unchanged)
        assert result.fold_count == ctx.fold_count

    def test_round_trip_json(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        layout = {
            "order": ["region_2", "region_0", "region_1"],
            "hidden": ["region_1"],
            "widths": {"region_0": 6, "region_2": 4},
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)

        # Verify order
        assert [r.name for r in result.regions] == ["region_2", "region_0", "region_1"]
        # Verify hidden
        assert result.regions[2].hidden is True
        # Verify widths
        assert result.regions[1].col_span == 6
        assert result.regions[0].col_span == 4

        # Serialize and deserialize — result must be JSON-serialisable via Pydantic
        serialised = result.model_dump_json()
        restored = result.__class__.model_validate_json(serialised)
        assert [r.name for r in restored.regions] == ["region_2", "region_0", "region_1"]


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
