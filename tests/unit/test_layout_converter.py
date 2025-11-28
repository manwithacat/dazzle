"""Tests for DSL to Layout IR converter."""

from dazzle.core.ir import (
    AppSpec,
    AttentionSignalKind,
    DomainSpec,
    WorkspaceRegion,
    WorkspaceSpec,
)
from dazzle.ui.layout_engine import (
    convert_workspace_to_layout,
    convert_workspaces_to_layouts,
    enrich_app_spec_with_layouts,
)


class TestWorkspaceConversion:
    """Tests for workspace conversion."""

    def test_convert_simple_workspace(self):
        """Test converting a simple workspace with one region."""
        workspace = WorkspaceSpec(
            name="dashboard",
            title="Dashboard",
            purpose="Team overview",
            regions=[
                WorkspaceRegion(
                    name="tasks",
                    source="Task",
                )
            ],
        )

        layout = convert_workspace_to_layout(workspace)

        assert layout.id == "dashboard"
        assert layout.label == "Dashboard"
        assert len(layout.attention_signals) == 1

        signal = layout.attention_signals[0]
        assert signal.id == "tasks"
        assert signal.label == "tasks"  # WorkspaceRegion uses name for label
        assert signal.kind == AttentionSignalKind.TABLE
        assert signal.source == "Task"
        # Base weight for simple region
        assert signal.attention_weight == 0.5

    def test_convert_workspace_with_aggregate(self):
        """Test that aggregates become KPI signals."""
        workspace = WorkspaceSpec(
            name="metrics",
            title="Metrics",
            regions=[
                WorkspaceRegion(
                    name="total_tasks",
                    source="Task",
                    aggregates={"count": "Task"},
                )
            ],
        )

        layout = convert_workspace_to_layout(workspace)

        signal = layout.attention_signals[0]
        assert signal.kind == AttentionSignalKind.KPI
        # Aggregates should have high weight
        assert signal.attention_weight >= 0.7

    def test_convert_multiple_workspaces(self):
        """Test converting multiple workspaces."""
        app_spec = AppSpec(
            name="test_app",
            domain=DomainSpec(entities=[]),
            workspaces=[
                WorkspaceSpec(
                    name="dashboard",
                    title="Dashboard",
                    regions=[
                        WorkspaceRegion(
                            name="tasks",
                            source="Task",
                        )
                    ],
                ),
                WorkspaceSpec(
                    name="reports",
                    title="Reports",
                    regions=[
                        WorkspaceRegion(
                            name="data",
                            source="Report",
                        )
                    ],
                ),
            ],
        )

        layouts = convert_workspaces_to_layouts(app_spec)

        assert len(layouts) == 2
        assert layouts[0].id == "dashboard"
        assert layouts[1].id == "reports"

    def test_enrich_app_spec(self):
        """Test enriching AppSpec with layouts."""
        app_spec = AppSpec(
            name="test_app",
            domain=DomainSpec(entities=[]),
            workspaces=[
                WorkspaceSpec(
                    name="dashboard",
                    title="Dashboard",
                    regions=[
                        WorkspaceRegion(
                            name="tasks",
                            source="Task",
                        )
                    ],
                )
            ],
        )

        enriched = enrich_app_spec_with_layouts(app_spec)

        # Should have ux field populated
        assert enriched.ux is not None
        assert len(enriched.ux.workspaces) == 1
        assert enriched.ux.workspaces[0].id == "dashboard"

        # Original workspaces should still be there
        assert len(enriched.workspaces) == 1


class TestSignalInference:
    """Tests for signal kind and weight inference."""

    def test_limited_becomes_item_list(self):
        """Test that limited regions can become ITEM_LIST."""
        workspace = WorkspaceSpec(
            name="test",
            regions=[
                WorkspaceRegion(
                    name="top_tasks",
                    source="Task",
                    limit=5,
                )
            ],
        )

        layout = convert_workspace_to_layout(workspace)
        signal = layout.attention_signals[0]

        # Without filter, limit alone doesn't make it ITEM_LIST
        # but it should boost weight
        assert signal.attention_weight >= 0.6

    def test_no_limit_becomes_table(self):
        """Test that regions without limits become TABLE."""
        workspace = WorkspaceSpec(
            name="test",
            regions=[
                WorkspaceRegion(
                    name="all",
                    source="Task",
                )
            ],
        )

        layout = convert_workspace_to_layout(workspace)
        signal = layout.attention_signals[0]

        assert signal.kind == AttentionSignalKind.TABLE
        # No boosts, should be base weight
        assert signal.attention_weight == 0.5

    def test_aggregate_boosts_weight(self):
        """Test that aggregates boost attention weight."""
        workspace = WorkspaceSpec(
            name="test",
            regions=[
                WorkspaceRegion(
                    name="metrics",
                    source="Task",
                    aggregates={"total": "count(Task)"},
                )
            ],
        )

        layout = convert_workspace_to_layout(workspace)
        signal = layout.attention_signals[0]

        # Aggregate should boost weight
        assert signal.attention_weight >= 0.7
        assert signal.kind == AttentionSignalKind.KPI

    def test_weight_clamping(self):
        """Test that weights are clamped to [0.0, 1.0]."""
        # Create region with boost factors
        workspace = WorkspaceSpec(
            name="test",
            regions=[
                WorkspaceRegion(
                    name="critical",
                    source="Task",
                    limit=1,
                    aggregates={"count": "count(Task)"},
                )
            ],
        )

        layout = convert_workspace_to_layout(workspace)
        signal = layout.attention_signals[0]

        # Should be clamped to 1.0
        assert signal.attention_weight <= 1.0
        assert signal.attention_weight >= 0.0
