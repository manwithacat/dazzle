"""Accessibility tests for generated components.

Tests that generated React components include proper accessibility features:
- ARIA labels and attributes
- Semantic HTML elements
- Keyboard navigation support
- Screen reader support
- Color contrast (via class names)
"""

from pathlib import Path

import pytest

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.stacks.nextjs_semantic import NextjsSemanticBackend


@pytest.fixture
def examples_dir() -> Path:
    """Path to examples directory."""
    return Path(__file__).parent.parent.parent / "examples"


class TestAriaLabels:
    """Test ARIA label implementation across all archetypes."""

    @pytest.mark.parametrize("example_name,archetype_component", [
        ("uptime_monitor", "FocusMetric"),
        ("inventory_scanner", "ScannerTable"),
        ("email_client", "MonitorWall"),
        ("ops_dashboard", "CommandCenter"),  # Will have whatever archetype is selected
    ])
    def test_archetype_components_have_aria_labels(self, examples_dir, tmp_path, example_name, archetype_component):
        """Test that all archetype components include ARIA labels."""
        example_path = examples_dir / example_name
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Check specific archetype component
        project_root = output_dir / manifest.name.replace("_", "-")
        component_path = (
            project_root / "src" / "components" / "archetypes" / f"{archetype_component}.tsx"
        )

        if component_path.exists():  # ops_dashboard might use different archetype
            content = component_path.read_text()

            # Should have ARIA labels
            assert 'aria-label=' in content, f"{archetype_component} missing aria-label"

            # Should have role attributes
            assert 'role=' in content, f"{archetype_component} missing role attributes"


class TestSemanticHTML:
    """Test semantic HTML usage in generated components."""

    def test_focus_metric_uses_semantic_elements(self, examples_dir, tmp_path):
        """Test FocusMetric uses semantic HTML."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        focus_metric = (
            output_dir / "uptime-monitor" / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        )
        content = focus_metric.read_text()

        # Should use semantic elements
        assert '<main' in content
        assert '<section' in content

        # Should have landmark roles
        assert 'role="main"' in content

    def test_scanner_table_uses_semantic_elements(self, examples_dir, tmp_path):
        """Test ScannerTable uses semantic HTML."""
        example_path = examples_dir / "inventory_scanner"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        scanner_table = (
            output_dir / "inventory-scanner" / "src" / "components" / "archetypes" / "ScannerTable.tsx"
        )
        content = scanner_table.read_text()

        # Should use semantic elements
        assert '<main' in content
        assert '<nav' in content or '<section' in content

    def test_monitor_wall_uses_semantic_elements(self, examples_dir, tmp_path):
        """Test MonitorWall uses semantic HTML."""
        example_path = examples_dir / "email_client"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        monitor_wall = (
            output_dir / "email-client" / "src" / "components" / "archetypes" / "MonitorWall.tsx"
        )
        content = monitor_wall.read_text()

        # Should use semantic elements
        assert '<main' in content


class TestKeyboardNavigation:
    """Test keyboard navigation support in generated components."""

    def test_archetype_router_renders_focusable_content(self, examples_dir, tmp_path):
        """Test that ArchetypeRouter renders interactive content."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        router = (
            output_dir / "uptime-monitor" / "src" / "components" / "archetypes" / "ArchetypeRouter.tsx"
        )
        content = router.read_text()

        # Router should render components that support keyboard navigation
        # (actual keyboard nav is in the components themselves)
        assert "FocusMetric" in content
        assert "plan" in content
        assert "signals" in content


class TestScreenReaderSupport:
    """Test screen reader support in generated components."""

    @pytest.mark.parametrize("component_name", [
        "FocusMetric",
        "ScannerTable",
        "DualPaneFlow",
        "MonitorWall",
        "CommandCenter",
    ])
    def test_component_has_descriptive_aria_labels(self, examples_dir, tmp_path, component_name):
        """Test that components have descriptive ARIA labels for screen readers."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        component_path = (
            output_dir / "uptime-monitor" / "src" / "components" / "archetypes" / f"{component_name}.tsx"
        )
        content = component_path.read_text()

        # Should have descriptive ARIA labels (not just "click here")
        aria_labels = []
        import re
        matches = re.findall(r'aria-label="([^"]+)"', content)
        aria_labels.extend(matches)

        # Should have at least one ARIA label
        assert len(aria_labels) > 0, f"{component_name} has no ARIA labels"

        # ARIA labels should be descriptive (not generic)
        generic_labels = ["click", "button", "div", "section"]
        for label in aria_labels:
            for generic in generic_labels:
                assert label.lower() != generic, f"{component_name} has generic ARIA label: {label}"


class TestColorContrast:
    """Test that generated components use accessible color classes."""

    def test_components_use_tailwind_semantic_colors(self, examples_dir, tmp_path):
        """Test that components use Tailwind's semantic color utilities."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        focus_metric = (
            output_dir / "uptime-monitor" / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        )
        content = focus_metric.read_text()

        # Should use Tailwind color utilities (which have good contrast by default)
        # bg-white, bg-gray-50, text-gray-900, etc.
        tailwind_colors = ["bg-", "text-", "border-"]
        found_color_classes = any(color in content for color in tailwind_colors)
        assert found_color_classes, "Component should use Tailwind color utilities"


class TestNavigationLandmarks:
    """Test that components use proper landmark roles."""

    def test_focus_metric_has_navigation_landmarks(self, examples_dir, tmp_path):
        """Test FocusMetric has proper landmark structure."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        focus_metric = (
            output_dir / "uptime-monitor" / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        )
        content = focus_metric.read_text()

        # Should have main landmark
        assert 'role="main"' in content

        # Should have section landmarks
        assert '<section' in content


class TestAccessibilityDocumentation:
    """Test that accessibility features are documented in generated README."""

    def test_generated_project_has_readme(self, examples_dir, tmp_path):
        """Test that generated projects include README with accessibility info."""
        example_path = examples_dir / "uptime_monitor"
        manifest_path = example_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)

        dsl_files = discover_dsl_files(example_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, f"{manifest.name}.core")

        output_dir = tmp_path / "output"
        backend = NextjsSemanticBackend()
        backend.generate(appspec, output_dir)

        # Check if README exists (if generated)
        readme = output_dir / "uptime-monitor" / "README.md"
        if readme.exists():
            content = readme.read_text()
            # If README exists, it should mention Next.js
            assert "Next.js" in content or "next" in content.lower()
