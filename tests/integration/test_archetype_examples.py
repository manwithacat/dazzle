"""Golden master tests for archetype examples.

Tests that all archetype example projects produce consistent layout plans
and select the correct archetypes.
"""

from pathlib import Path

import pytest

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.ui.layout_engine.converter import convert_workspace_to_layout
from dazzle.ui.layout_engine.plan import build_layout_plan


@pytest.fixture
def examples_dir() -> Path:
    """Path to examples directory."""
    return Path(__file__).parent.parent.parent / "examples"


def load_example_appspec(example_name: str, examples_dir: Path):
    """Load and parse an example project."""
    example_path = examples_dir / example_name
    manifest_path = example_path / "dazzle.toml"
    manifest = load_manifest(manifest_path)

    # Discover and parse DSL files
    dsl_files = discover_dsl_files(example_path, manifest)
    modules = parse_modules(dsl_files)

    # Build appspec (use module name from manifest)
    # For examples, the root module is typically {name}.core
    root_module = f"{manifest.name}.core"
    appspec = build_appspec(modules, root_module)

    return appspec


class TestFocusMetricArchetype:
    """Tests for FOCUS_METRIC archetype example (uptime_monitor)."""

    def test_uptime_monitor_selects_focus_metric(self, examples_dir):
        """Test that uptime_monitor example selects FOCUS_METRIC archetype."""
        appspec = load_example_appspec("uptime_monitor", examples_dir)

        # Should have workspaces
        assert len(appspec.workspaces) == 1

        workspace_spec = appspec.workspaces[0]
        assert workspace_spec.name == "uptime"

        # Convert to layout
        layout = convert_workspace_to_layout(workspace_spec)

        # Generate plan
        plan = build_layout_plan(layout)

        # Should select FOCUS_METRIC archetype
        assert plan.archetype.value == "focus_metric"

        # Should have hero and context surfaces
        surface_ids = {s.id for s in plan.surfaces}
        assert "hero" in surface_ids

        # No over-budget signals
        assert len(plan.over_budget_signals) == 0

    def test_uptime_monitor_signal_structure(self, examples_dir):
        """Test that uptime_monitor has expected signal structure."""
        appspec = load_example_appspec("uptime_monitor", examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace)

        # Should have 1 signal (single KPI with aggregates)
        assert len(layout.attention_signals) == 1

        signal = layout.attention_signals[0]
        assert signal.id == "system_uptime"
        assert signal.kind.value == "kpi"

        # Dominant weight for FOCUS_METRIC
        assert signal.attention_weight > 0.7


class TestScannerTableArchetype:
    """Tests for SCANNER_TABLE archetype example (inventory_scanner)."""

    def test_inventory_scanner_selects_scanner_table(self, examples_dir):
        """Test that inventory_scanner example selects SCANNER_TABLE archetype."""
        appspec = load_example_appspec("inventory_scanner", examples_dir)

        workspace_spec = appspec.workspaces[0]
        assert workspace.id == "inventory"

        layout = convert_workspace_to_layout(workspace)
        plan = build_layout_plan(layout)

        # Should select SCANNER_TABLE archetype
        assert plan.archetype.value == "scanner_table"

        # Should have table surface
        surface_ids = {s.id for s in plan.surfaces}
        assert "table" in surface_ids

    def test_inventory_scanner_signal_structure(self, examples_dir):
        """Test that inventory_scanner has expected signal structure."""
        appspec = load_example_appspec("inventory_scanner", examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace)

        # Should have 1 TABLE signal
        assert len(layout.attention_signals) == 1

        signal = layout.attention_signals[0]
        assert signal.id == "all_products"
        assert signal.kind.value == "table"


class TestMonitorWallArchetype:
    """Tests for MONITOR_WALL archetype example (email_client)."""

    def test_email_client_selects_monitor_wall(self, examples_dir):
        """Test that email_client example selects MONITOR_WALL archetype."""
        appspec = load_example_appspec("email_client", examples_dir)

        workspace_spec = appspec.workspaces[0]
        assert workspace.id == "inbox"

        layout = convert_workspace_to_layout(workspace)
        plan = build_layout_plan(layout)

        # Should select MONITOR_WALL archetype
        assert plan.archetype.value == "monitor_wall"

        # Should have primary surfaces
        surface_ids = {s.id for s in plan.surfaces}
        assert any(s_id.startswith("primary") for s_id in surface_ids)

    def test_email_client_signal_structure(self, examples_dir):
        """Test that email_client has expected signal structure."""
        appspec = load_example_appspec("email_client", examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace)

        # Should have 4 signals (1 KPI + 2 ITEM_LIST + 1 TABLE)
        assert len(layout.attention_signals) == 4

        signal_kinds = [s.kind.value for s in layout.attention_signals]
        assert "kpi" in signal_kinds
        assert signal_kinds.count("item_list") == 2
        assert "table" in signal_kinds


class TestHighSignalCount:
    """Tests for high signal count example (ops_dashboard)."""

    def test_ops_dashboard_archetype_selection(self, examples_dir):
        """Test that ops_dashboard selects appropriate archetype."""
        appspec = load_example_appspec("ops_dashboard", examples_dir)

        workspace_spec = appspec.workspaces[0]
        assert workspace.id == "operations"

        layout = convert_workspace_to_layout(workspace)
        plan = build_layout_plan(layout)

        # Should select an archetype (exact one depends on signal weights)
        assert plan.archetype.value in [
            "focus_metric",
            "scanner_table",
            "dual_pane_flow",
            "monitor_wall",
            "command_center",
        ]

        # May have over-budget signals due to high count
        # This is expected behavior

    def test_ops_dashboard_signal_structure(self, examples_dir):
        """Test that ops_dashboard has expected signal structure."""
        appspec = load_example_appspec("ops_dashboard", examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace)

        # Should have 8 signals
        assert len(layout.attention_signals) == 8

        # Should have mix of signal types
        signal_kinds = [s.kind.value for s in layout.attention_signals]
        assert "kpi" in signal_kinds
        assert "item_list" in signal_kinds
        assert "table" in signal_kinds


class TestDeterministicGeneration:
    """Tests that layout plan generation is deterministic."""

    @pytest.mark.parametrize("example_name", [
        "uptime_monitor",
        "inventory_scanner",
        "email_client",
        "ops_dashboard",
    ])
    def test_layout_plan_deterministic(self, example_name, examples_dir):
        """Test that parsing same example twice produces identical layout plans."""
        # Generate plan twice
        appspec1 = load_example_appspec(example_name, examples_dir)
        workspace1 = appspec1.ux.workspaces[0]
        layout1 = convert_workspace_to_layout(workspace1)
        planner1 = LayoutPlanner()
        plan1 = planner1.plan(layout1)

        appspec2 = load_example_appspec(example_name, examples_dir)
        workspace2 = appspec2.ux.workspaces[0]
        layout2 = convert_workspace_to_layout(workspace2)
        planner2 = LayoutPlanner()
        plan2 = planner2.plan(layout2)

        # Archetypes should match
        assert plan1.archetype == plan2.archetype

        # Surface count should match
        assert len(plan1.surfaces) == len(plan2.surfaces)

        # Surface allocations should match
        for surf1, surf2 in zip(plan1.surfaces, plan2.surfaces):
            assert surf1.id == surf2.id
            assert surf1.archetype == surf2.archetype
            assert surf1.assigned_signals == surf2.assigned_signals


class TestLayoutPlanSnapshots:
    """Snapshot tests for layout plans."""

    @pytest.mark.parametrize("example_name", [
        "uptime_monitor",
        "inventory_scanner",
        "email_client",
        "ops_dashboard",
    ])
    def test_layout_plan_snapshot(self, example_name, examples_dir, snapshot):
        """Test that layout plan matches snapshot."""
        appspec = load_example_appspec(example_name, examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace)
        plan = build_layout_plan(layout)

        # Convert to dict for snapshot comparison
        plan_dict = {
            "workspace_id": plan.workspace_id,
            "persona_id": plan.persona_id,
            "archetype": plan.archetype.value,
            "surfaces": [
                {
                    "id": s.id,
                    "archetype": s.archetype.value,
                    "capacity": s.capacity,
                    "priority": s.priority,
                    "assigned_signals": s.assigned_signals,
                }
                for s in plan.surfaces
            ],
            "over_budget_signals": plan.over_budget_signals,
            "warnings": plan.warnings,
        }

        # Compare against snapshot
        assert plan_dict == snapshot


class TestArchetypeConsistency:
    """Tests for archetype selection consistency."""

    def test_focus_metric_requires_dominant_kpi(self, examples_dir):
        """Test that FOCUS_METRIC requires dominant KPI."""
        appspec = load_example_appspec("uptime_monitor", examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace)

        # Find KPI signal
        kpi_signals = [s for s in layout.attention_signals if s.kind.value == "kpi"]
        assert len(kpi_signals) > 0

        # Should have high weight
        max_kpi_weight = max(s.attention_weight for s in kpi_signals)
        assert max_kpi_weight > 0.7

    def test_scanner_table_requires_table_signal(self, examples_dir):
        """Test that SCANNER_TABLE requires TABLE signal."""
        appspec = load_example_appspec("inventory_scanner", examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace)

        # Should have TABLE signal
        table_signals = [s for s in layout.attention_signals if s.kind.value == "table"]
        assert len(table_signals) > 0

        # Table weight should be significant
        total_table_weight = sum(s.attention_weight for s in table_signals)
        assert total_table_weight > 0.5

    def test_monitor_wall_requires_multiple_signals(self, examples_dir):
        """Test that MONITOR_WALL requires 3-8 signals."""
        appspec = load_example_appspec("email_client", examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace)

        # Should have 3-8 signals
        signal_count = len(layout.attention_signals)
        assert 3 <= signal_count <= 8
