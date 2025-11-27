"""Integration tests for semantic UI archetype pipeline.

Tests the complete end-to-end flow using actual example projects:
DSL → Parser → Linker → Layout Engine → Next.js Generation → Rendered Components
"""

import json
from pathlib import Path

import pytest

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.stacks.nextjs_semantic import NextjsSemanticBackend
from dazzle.ui.layout_engine.converter import convert_workspace_to_layout
from dazzle.ui.layout_engine.plan import build_layout_plan


@pytest.fixture
def examples_dir() -> Path:
    """Path to examples directory."""
    return Path(__file__).parent.parent.parent / "examples"


class TestFocusMetricPipeline:
    """End-to-end tests for FOCUS_METRIC archetype pipeline."""

    def test_uptime_monitor_full_pipeline(self, examples_dir, tmp_path):
        """Test complete pipeline: DSL → Layout Plan → Next.js."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        # Step 1: DSL → AppSpec
        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        # Step 2: AppSpec → Layout Plan
        assert len(appspec.workspaces) == 1
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace_spec)
        plan = build_layout_plan(layout)

        # Verify FOCUS_METRIC archetype
        assert plan.archetype.value == "focus_metric"

        # Step 3: Layout Plan → Next.js
        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Step 4: Verify generated Next.js project
        project_root = output_dir / "uptime-monitor"
        assert project_root.exists()

        # Verify package.json
        package_json = project_root / "package.json"
        assert package_json.exists()
        package_data = json.loads(package_json.read_text())
        assert package_data["name"] == "uptime-monitor"
        assert "next" in package_data["dependencies"]
        assert "react" in package_data["dependencies"]

        # Verify Next.js config
        next_config = project_root / "next.config.js"
        assert next_config.exists()

        # Verify TypeScript config
        tsconfig = project_root / "tsconfig.json"
        assert tsconfig.exists()

        # Verify workspace page
        workspace_page = project_root / "src" / "app" / "uptime" / "page.tsx"
        assert workspace_page.exists()

        page_content = workspace_page.read_text()
        # Should reference FOCUS_METRIC archetype
        assert "FOCUS_METRIC" in page_content

        # Verify FocusMetric component exists
        focus_metric_component = project_root / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        assert focus_metric_component.exists()

        component_content = focus_metric_component.read_text()
        assert "FocusMetric" in component_content
        assert "aria-label" in component_content  # Accessibility


class TestScannerTablePipeline:
    """End-to-end tests for SCANNER_TABLE archetype pipeline."""

    def test_inventory_scanner_full_pipeline(self, examples_dir, tmp_path):
        """Test complete pipeline for SCANNER_TABLE archetype."""
        example_path = examples_dir / "inventory_scanner"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        # DSL → AppSpec
        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        # AppSpec → Layout Plan
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace_spec)
        plan = build_layout_plan(layout)

        # Verify SCANNER_TABLE archetype
        assert plan.archetype.value == "scanner_table"

        # Layout Plan → Next.js
        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Verify generated project
        project_root = output_dir / "inventory-scanner"
        assert project_root.exists()

        # Verify workspace page
        workspace_page = project_root / "src" / "app" / "inventory" / "page.tsx"
        assert workspace_page.exists()

        page_content = workspace_page.read_text()
        assert "SCANNER_TABLE" in page_content

        # Verify ScannerTable component
        scanner_table_component = project_root / "src" / "components" / "archetypes" / "ScannerTable.tsx"
        assert scanner_table_component.exists()

        component_content = scanner_table_component.read_text()
        assert "ScannerTable" in component_content
        assert "aria-label" in component_content


class TestMonitorWallPipeline:
    """End-to-end tests for MONITOR_WALL archetype pipeline."""

    def test_email_client_full_pipeline(self, examples_dir, tmp_path):
        """Test complete pipeline for MONITOR_WALL archetype."""
        example_path = examples_dir / "email_client"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        # DSL → AppSpec
        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        # AppSpec → Layout Plan
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace_spec)
        plan = build_layout_plan(layout)

        # Verify MONITOR_WALL archetype
        assert plan.archetype.value == "monitor_wall"

        # Layout Plan → Next.js
        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Verify generated project
        project_root = output_dir / "email-client"
        assert project_root.exists()

        # Verify workspace page
        workspace_page = project_root / "src" / "app" / "inbox" / "page.tsx"
        assert workspace_page.exists()

        page_content = workspace_page.read_text()
        assert "MONITOR_WALL" in page_content

        # Verify MonitorWall component
        monitor_wall_component = project_root / "src" / "components" / "archetypes" / "MonitorWall.tsx"
        assert monitor_wall_component.exists()

        component_content = monitor_wall_component.read_text()
        assert "MonitorWall" in component_content
        assert "grid" in component_content.lower()  # Grid layout


class TestHighSignalCountPipeline:
    """End-to-end tests for high signal count (ops_dashboard)."""

    def test_ops_dashboard_full_pipeline(self, examples_dir, tmp_path):
        """Test complete pipeline with high signal count."""
        example_path = examples_dir / "ops_dashboard"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        # DSL → AppSpec
        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        # AppSpec → Layout Plan
        workspace_spec = appspec.workspaces[0]
        layout = convert_workspace_to_layout(workspace_spec)
        plan = build_layout_plan(layout)

        # Should select an archetype
        assert plan.archetype is not None

        # Layout Plan → Next.js
        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Verify generated project
        project_root = output_dir / "ops-dashboard"
        assert project_root.exists()

        # Verify workspace page
        workspace_page = project_root / "src" / "app" / "operations" / "page.tsx"
        assert workspace_page.exists()

        page_content = workspace_page.read_text()

        # Should use ArchetypeRouter
        assert "ArchetypeRouter" in page_content


class TestComponentGeneration:
    """Test that all archetype components are generated."""

    def test_all_archetype_components_generated(self, examples_dir, tmp_path):
        """Test that all 5 archetype components are always generated."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        project_root = output_dir / "uptime-monitor"
        archetypes_dir = project_root / "src" / "components" / "archetypes"

        # All 5 archetype components should exist
        assert (archetypes_dir / "FocusMetric.tsx").exists()
        assert (archetypes_dir / "ScannerTable.tsx").exists()
        assert (archetypes_dir / "DualPaneFlow.tsx").exists()
        assert (archetypes_dir / "MonitorWall.tsx").exists()
        assert (archetypes_dir / "CommandCenter.tsx").exists()

        # ArchetypeRouter should exist
        assert (archetypes_dir / "ArchetypeRouter.tsx").exists()

        # SignalRenderer should exist
        signals_dir = project_root / "src" / "components" / "signals"
        assert (signals_dir / "SignalRenderer.tsx").exists()


class TestAccessibilityFeatures:
    """Test that accessibility features are generated."""

    def test_aria_labels_in_workspace_page(self, examples_dir, tmp_path):
        """Test that workspace pages include ARIA labels."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Check FocusMetric component has ARIA labels
        focus_metric = (
            output_dir / "uptime-monitor" / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        )
        content = focus_metric.read_text()

        assert 'aria-label' in content
        assert 'role=' in content

    def test_semantic_html_in_components(self, examples_dir, tmp_path):
        """Test that components use semantic HTML."""
        example_path = examples_dir / "inventory_scanner"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Check ScannerTable uses semantic HTML
        scanner_table = (
            output_dir / "inventory-scanner" / "src" / "components" / "archetypes" / "ScannerTable.tsx"
        )
        content = scanner_table.read_text()

        assert '<main' in content or '<section' in content
        assert 'role=' in content


class TestResponsiveDesign:
    """Test that responsive design is implemented."""

    def test_responsive_classes_in_components(self, examples_dir, tmp_path):
        """Test that components include responsive Tailwind classes."""
        example_path = examples_dir / "email_client"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Check MonitorWall has responsive classes
        monitor_wall = (
            output_dir / "email-client" / "src" / "components" / "archetypes" / "MonitorWall.tsx"
        )
        content = monitor_wall.read_text()

        # Should have responsive breakpoints
        assert 'sm:' in content or 'md:' in content or 'lg:' in content


class TestTypeSafety:
    """Test that generated TypeScript code is type-safe."""

    def test_layout_types_generated(self, examples_dir, tmp_path):
        """Test that layout types are generated."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Check layout types file
        layout_types = output_dir / "uptime-monitor" / "src" / "types" / "layout.ts"
        assert layout_types.exists()

        content = layout_types.read_text()
        assert "LayoutArchetype" in content
        assert "AttentionSignalKind" in content
        assert "LayoutPlan" in content
        assert "WorkspaceLayout" in content
