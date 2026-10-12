"""Tests for UI Semantic Layout IR types."""

from dazzle.core.ir import AttentionSignalKind, Stage


class TestLayoutArchetype:
    """Tests for Stage enum."""

    def test_archetype_combined(self):
        """Combined: all archetypes defined + individual values."""
        expected = {
            "focus_metric",
            "scanner_table",
            "dual_pane_flow",
            "monitor_wall",
            "command_center",
        }
        assert {a.value for a in Stage} == expected
        assert Stage.FOCUS_METRIC.value == "focus_metric"
        assert Stage.SCANNER_TABLE.value == "scanner_table"
        assert Stage.DUAL_PANE_FLOW.value == "dual_pane_flow"
        assert Stage.MONITOR_WALL.value == "monitor_wall"
        assert Stage.COMMAND_CENTER.value == "command_center"


class TestAttentionSignalKind:
    """Tests for LayoutSignalKind enum."""

    def test_signal_kind_combined(self):
        """Combined: all expected kinds defined + individual kind values."""
        expected = {
            "kpi",
            "alert_feed",
            "table",
            "item_list",
            "detail_view",
            "task_list",
            "form",
            "chart",
            "search",
            "filter",
        }
        assert {k.value for k in AttentionSignalKind} == expected
        assert AttentionSignalKind.KPI.value == "kpi"
        assert AttentionSignalKind.TABLE.value == "table"
        assert AttentionSignalKind.FORM.value == "form"
        assert AttentionSignalKind.CHART.value == "chart"
