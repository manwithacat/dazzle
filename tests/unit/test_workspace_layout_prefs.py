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
        """v1 hidden regions are dropped during auto-migration to v2."""
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        prefs = {f"workspace.{ctx.name}.layout": json.dumps({"hidden": ["region_1"]})}
        result = apply_layout_preferences(ctx, prefs)
        assert len(result.regions) == 2
        assert all(r.name != "region_1" for r in result.regions)

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

    def test_fold_count_after_hidden_drop(self) -> None:
        """Hidden regions are dropped in v2 migration; fold_count unchanged."""
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        prefs = {f"workspace.{ctx.name}.layout": json.dumps({"hidden": ["region_0"]})}
        result = apply_layout_preferences(ctx, prefs)
        # hidden regions are dropped (not present), fold_count is unchanged
        assert result.fold_count == ctx.fold_count
        assert len(result.regions) == 2

    def test_round_trip_json(self) -> None:
        """v1 layout auto-migrates to v2; hidden regions are dropped."""
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

        # region_1 is hidden → dropped in v2 migration
        assert [r.name for r in result.regions] == ["region_2", "region_0"]
        # Verify widths preserved
        assert result.regions[1].col_span == 6  # region_0
        assert result.regions[0].col_span == 4  # region_2

        # Serialize and deserialize — result must be JSON-serialisable via Pydantic
        serialised = result.model_dump_json()
        restored = result.__class__.model_validate_json(serialised)
        assert [r.name for r in restored.regions] == ["region_2", "region_0"]


class TestLayoutV2:
    """v2 layout schema — card-instance model."""

    def _make_ctx(self, region_count: int = 3) -> object:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = _make_workspace("scanner_table", region_count=region_count)
        return build_workspace_context(ws)

    def test_v2_card_order(self) -> None:
        """v2 cards list determines region order."""
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(3)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "region_2", "col_span": 12, "row_order": 0},
                {"id": "c2", "region": "region_0", "col_span": 6, "row_order": 1},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == ["region_2", "region_0"]
        assert result.regions[0].col_span == 12
        assert result.regions[1].col_span == 6

    def test_v2_duplicate_regions(self) -> None:
        """Same DSL region can appear multiple times in v2."""
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(2)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "region_0", "col_span": 6, "row_order": 0},
                {"id": "c2", "region": "region_0", "col_span": 6, "row_order": 1},
                {"id": "c3", "region": "region_1", "col_span": 12, "row_order": 2},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert len(result.regions) == 3
        assert result.regions[0].name == "region_0"
        assert result.regions[1].name == "region_0"
        assert result.regions[2].name == "region_1"

    def test_v2_ghost_region_skipped(self) -> None:
        """Cards referencing non-existent DSL regions are skipped."""
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(2)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "region_0", "col_span": 12, "row_order": 0},
                {"id": "c2", "region": "ghost_region", "col_span": 6, "row_order": 1},
                {"id": "c3", "region": "region_1", "col_span": 12, "row_order": 2},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert [r.name for r in result.regions] == ["region_0", "region_1"]

    def test_v2_col_span_3_allowed(self) -> None:
        """col_span=3 is valid in v2 (quarter-width cards)."""
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(2)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "region_0", "col_span": 3, "row_order": 0},
                {"id": "c2", "region": "region_1", "col_span": 12, "row_order": 1},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        assert result.regions[0].col_span == 3

    def test_v2_invalid_col_span_keeps_default(self) -> None:
        """Invalid col_span keeps the DSL default."""
        import json

        from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences

        ctx = self._make_ctx(2)
        layout = {
            "version": 2,
            "cards": [
                {"id": "c1", "region": "region_0", "col_span": 5, "row_order": 0},
            ],
        }
        prefs = {f"workspace.{ctx.name}.layout": json.dumps(layout)}
        result = apply_layout_preferences(ctx, prefs)
        # scanner_table default is 12
        assert result.regions[0].col_span == 12


class TestV1ToV2Migration:
    """migrate_v1_to_v2 converts old layout format to card instances."""

    def test_order_and_width_preserved(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {"order": ["b", "a"], "hidden": [], "widths": {"b": 6, "a": 4}}
        result = migrate_v1_to_v2(v1, ["a", "b"])
        assert result["version"] == 2
        cards = result["cards"]
        assert len(cards) == 2
        assert cards[0]["region"] == "b"
        assert cards[0]["col_span"] == 6
        assert cards[0]["row_order"] == 0
        assert cards[1]["region"] == "a"
        assert cards[1]["col_span"] == 4
        assert cards[1]["row_order"] == 1

    def test_hidden_cards_dropped(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {"order": ["a", "b", "c"], "hidden": ["b"], "widths": {}}
        result = migrate_v1_to_v2(v1, ["a", "b", "c"])
        regions = [c["region"] for c in result["cards"]]
        assert "b" not in regions
        assert regions == ["a", "c"]

    def test_ghost_regions_dropped(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {"order": ["a", "ghost", "b"], "hidden": [], "widths": {}}
        result = migrate_v1_to_v2(v1, ["a", "b"])
        regions = [c["region"] for c in result["cards"]]
        assert regions == ["a", "b"]

    def test_unique_id_assignment(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {"order": ["x", "y", "z"], "hidden": [], "widths": {}}
        result = migrate_v1_to_v2(v1, ["x", "y", "z"])
        ids = [c["id"] for c in result["cards"]]
        assert ids == ["migrated-0", "migrated-1", "migrated-2"]
        # All unique
        assert len(set(ids)) == 3

    def test_new_dsl_regions_appended(self) -> None:
        """Regions in DSL but not in v1 order are appended."""
        from dazzle_ui.runtime.workspace_renderer import migrate_v1_to_v2

        v1 = {"order": ["a"], "hidden": [], "widths": {}}
        result = migrate_v1_to_v2(v1, ["a", "b"])
        regions = [c["region"] for c in result["cards"]]
        assert regions == ["a", "b"]


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
