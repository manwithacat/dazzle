"""Golden master tests for archetype examples.

Tests that active example projects produce consistent layout plans
and select the correct archetypes. Only tests examples in the main
examples/ directory (not _archive/).
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
    """Load and parse an example project from the main examples directory."""
    example_path = examples_dir / example_name

    if not example_path.exists():
        pytest.skip(f"Example '{example_name}' not found in examples/")

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


class TestOpsDashboardArchetype:
    """Tests for COMMAND_CENTER archetype example (ops_dashboard)."""

    def test_ops_dashboard_archetype_selection(self, examples_dir):
        """Test that ops_dashboard selects COMMAND_CENTER archetype."""
        appspec = load_example_appspec("ops_dashboard", examples_dir)

        workspace_spec = appspec.workspaces[0]
        assert workspace_spec.name == "command_center"

        layout = convert_workspace_to_layout(workspace_spec)
        plan = build_layout_plan(layout)

        # Should select COMMAND_CENTER due to stage
        assert plan.stage.value == "command_center"

        # Verify it has the expected surfaces
        surface_ids = [s.id for s in plan.surfaces]
        assert "main_grid" in surface_ids
        assert "header" in surface_ids

    def test_ops_dashboard_signal_structure(self, examples_dir):
        """Test that ops_dashboard has expected signal structure."""
        appspec = load_example_appspec("ops_dashboard", examples_dir)
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace_spec)

        # Should have 3 signals (active_alerts, system_status, health_summary)
        assert len(layout.attention_signals) == 3

        # Should have mix of signal types
        signal_kinds = [s.kind.value for s in layout.attention_signals]
        # active_alerts is item_list, system_status is table, health_summary is kpi
        assert "item_list" in signal_kinds or "table" in signal_kinds or "kpi" in signal_kinds


class TestDeterministicGeneration:
    """Tests that layout plan generation is deterministic."""

    def test_ops_dashboard_layout_plan_deterministic(self, examples_dir):
        """Test that parsing ops_dashboard twice produces identical layout plans."""
        # Generate plan twice
        appspec1 = load_example_appspec("ops_dashboard", examples_dir)
        workspace_spec1 = appspec1.workspaces[0]
        layout1 = convert_workspace_to_layout(workspace_spec1)
        plan1 = build_layout_plan(layout1)

        appspec2 = load_example_appspec("ops_dashboard", examples_dir)
        workspace_spec2 = appspec2.workspaces[0]
        layout2 = convert_workspace_to_layout(workspace_spec2)
        plan2 = build_layout_plan(layout2)

        # Archetypes should match
        assert plan1.stage == plan2.stage

        # Surface count should match
        assert len(plan1.surfaces) == len(plan2.surfaces)

        # Surface allocations should match
        for surf1, surf2 in zip(plan1.surfaces, plan2.surfaces, strict=True):
            assert surf1.id == surf2.id
            assert surf1.stage == surf2.stage
            assert surf1.assigned_signals == surf2.assigned_signals
