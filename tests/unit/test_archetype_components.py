"""Unit tests for archetype component generation.

Tests that archetype components are generated correctly with:
- Proper semantic HTML structure
- ARIA labels and accessibility attributes
- Responsive CSS classes
- Correct signal rendering logic
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from dazzle.core.ir import (
    AppSpec,
    AttentionSignal,
    AttentionSignalKind,
    DomainSpec,
    UXLayouts,
    WorkspaceLayout,
)
from dazzle.stacks.nextjs_semantic import NextjsSemanticBackend


class TestFocusMetricComponent:
    """Tests for FocusMetric archetype component."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def focus_metric_spec(self):
        """Create AppSpec that generates FocusMetric archetype."""
        workspace = WorkspaceLayout(
            id="dashboard",
            label="Dashboard",
            attention_budget=1.0,
            attention_signals=[
                AttentionSignal(
                    id="main_kpi",
                    kind=AttentionSignalKind.KPI,
                    label="System Uptime",
                    source="monitoring",
                    attention_weight=0.9,  # Dominant weight -> FOCUS_METRIC
                )
            ],
        )

        return AppSpec(
            name="focus_test",
            title="Focus Test",
            domain=DomainSpec(entities=[]),
            ux=UXLayouts(workspaces=[workspace], personas=[]),
        )

    def test_focus_metric_has_semantic_html(self, focus_metric_spec, temp_output_dir):
        """Test that FocusMetric uses semantic HTML elements."""
        backend = NextjsSemanticBackend()
        backend.generate(focus_metric_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "focus-test" / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        )
        content = component_path.read_text()

        # Check semantic HTML
        assert '<main' in content
        assert 'role="main"' in content
        assert '<section' in content

    def test_focus_metric_has_aria_labels(self, focus_metric_spec, temp_output_dir):
        """Test that FocusMetric has proper ARIA labels."""
        backend = NextjsSemanticBackend()
        backend.generate(focus_metric_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "focus-test" / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        )
        content = component_path.read_text()

        # Check ARIA attributes
        assert 'aria-label="Focus metric dashboard"' in content
        assert 'aria-label="Primary metric"' in content
        assert 'aria-label="Supporting metrics"' in content or 'aria-label="Context metrics"' in content

    def test_focus_metric_has_responsive_classes(self, focus_metric_spec, temp_output_dir):
        """Test that FocusMetric has responsive Tailwind classes."""
        backend = NextjsSemanticBackend()
        backend.generate(focus_metric_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "focus-test" / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        )
        content = component_path.read_text()

        # Check responsive breakpoints (sm, md, lg, xl)
        assert 'sm:' in content  # Small screens
        assert 'lg:' in content  # Large screens

    def test_focus_metric_uses_signal_renderer(self, focus_metric_spec, temp_output_dir):
        """Test that FocusMetric uses SignalRenderer component."""
        backend = NextjsSemanticBackend()
        backend.generate(focus_metric_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "focus-test" / "src" / "components" / "archetypes" / "FocusMetric.tsx"
        )
        content = component_path.read_text()

        # Check SignalRenderer usage
        assert 'SignalRenderer' in content
        assert 'variant="hero"' in content
        assert 'variant="context"' in content


class TestScannerTableComponent:
    """Tests for ScannerTable archetype component."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def scanner_table_spec(self):
        """Create AppSpec that generates ScannerTable archetype."""
        workspace = WorkspaceLayout(
            id="inventory",
            label="Inventory",
            attention_budget=1.0,
            attention_signals=[
                AttentionSignal(
                    id="products_table",
                    kind=AttentionSignalKind.TABLE,
                    label="All Products",
                    source="products",
                    attention_weight=0.9,  # Dominant TABLE -> SCANNER_TABLE
                )
            ],
        )

        return AppSpec(
            name="scanner_test",
            title="Scanner Test",
            domain=DomainSpec(entities=[]),
            ux=UXLayouts(workspaces=[workspace], personas=[]),
        )

    def test_scanner_table_has_semantic_html(self, scanner_table_spec, temp_output_dir):
        """Test that ScannerTable uses semantic HTML."""
        backend = NextjsSemanticBackend()
        backend.generate(scanner_table_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "scanner-test" / "src" / "components" / "archetypes" / "ScannerTable.tsx"
        )
        content = component_path.read_text()

        # Check semantic HTML
        assert '<main' in content
        assert 'role="main"' in content

    def test_scanner_table_has_aria_labels(self, scanner_table_spec, temp_output_dir):
        """Test that ScannerTable has proper ARIA labels."""
        backend = NextjsSemanticBackend()
        backend.generate(scanner_table_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "scanner-test" / "src" / "components" / "archetypes" / "ScannerTable.tsx"
        )
        content = component_path.read_text()

        # Check ARIA attributes
        assert 'aria-label="Data table browser"' in content
        assert 'aria-label="Data table"' in content


class TestDualPaneFlowComponent:
    """Tests for DualPaneFlow archetype component."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def dual_pane_spec(self):
        """Create AppSpec that generates DualPaneFlow archetype."""
        workspace = WorkspaceLayout(
            id="contacts",
            label="Contacts",
            attention_budget=1.0,
            attention_signals=[
                AttentionSignal(
                    id="contact_list",
                    kind=AttentionSignalKind.ITEM_LIST,
                    label="Contact List",
                    source="contacts",
                    attention_weight=0.6,
                ),
                AttentionSignal(
                    id="contact_detail",
                    kind=AttentionSignalKind.DETAIL_VIEW,
                    label="Contact Details",
                    source="contacts",
                    attention_weight=0.7,
                ),
            ],
        )

        return AppSpec(
            name="dual_pane_test",
            title="Dual Pane Test",
            domain=DomainSpec(entities=[]),
            ux=UXLayouts(workspaces=[workspace], personas=[]),
        )

    def test_dual_pane_has_semantic_html(self, dual_pane_spec, temp_output_dir):
        """Test that DualPaneFlow uses semantic HTML."""
        backend = NextjsSemanticBackend()
        backend.generate(dual_pane_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "dual-pane-test" / "src" / "components" / "archetypes" / "DualPaneFlow.tsx"
        )
        content = component_path.read_text()

        # Check semantic HTML
        assert '<main' in content
        assert '<nav' in content  # List navigation pane

    def test_dual_pane_has_aria_labels(self, dual_pane_spec, temp_output_dir):
        """Test that DualPaneFlow has proper ARIA labels."""
        backend = NextjsSemanticBackend()
        backend.generate(dual_pane_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "dual-pane-test" / "src" / "components" / "archetypes" / "DualPaneFlow.tsx"
        )
        content = component_path.read_text()

        # Check ARIA attributes
        assert 'aria-label="Item list navigation"' in content
        assert 'aria-label="Item detail view"' in content

    def test_dual_pane_has_responsive_layout(self, dual_pane_spec, temp_output_dir):
        """Test that DualPaneFlow has responsive layout."""
        backend = NextjsSemanticBackend()
        backend.generate(dual_pane_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "dual-pane-test" / "src" / "components" / "archetypes" / "DualPaneFlow.tsx"
        )
        content = component_path.read_text()

        # Check responsive grid/flex classes
        assert 'lg:' in content  # Large screen layout


class TestMonitorWallComponent:
    """Tests for MonitorWall archetype component."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def monitor_wall_spec(self):
        """Create AppSpec that generates MonitorWall archetype."""
        workspace = WorkspaceLayout(
            id="operations",
            label="Operations",
            attention_budget=1.0,
            attention_signals=[
                AttentionSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="Active Users",
                    source="analytics",
                    attention_weight=0.3,
                ),
                AttentionSignal(
                    id="kpi2",
                    kind=AttentionSignalKind.KPI,
                    label="Error Rate",
                    source="monitoring",
                    attention_weight=0.3,
                ),
                AttentionSignal(
                    id="list1",
                    kind=AttentionSignalKind.ITEM_LIST,
                    label="Recent Alerts",
                    source="alerts",
                    attention_weight=0.2,
                ),
                AttentionSignal(
                    id="table1",
                    kind=AttentionSignalKind.TABLE,
                    label="Server Status",
                    source="servers",
                    attention_weight=0.2,
                ),
            ],
        )

        return AppSpec(
            name="monitor_wall_test",
            title="Monitor Wall Test",
            domain=DomainSpec(entities=[]),
            ux=UXLayouts(workspaces=[workspace], personas=[]),
        )

    def test_monitor_wall_has_semantic_html(self, monitor_wall_spec, temp_output_dir):
        """Test that MonitorWall uses semantic HTML."""
        backend = NextjsSemanticBackend()
        backend.generate(monitor_wall_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "monitor-wall-test" / "src" / "components" / "archetypes" / "MonitorWall.tsx"
        )
        content = component_path.read_text()

        # Check semantic HTML
        assert '<main' in content
        assert 'role="main"' in content

    def test_monitor_wall_has_aria_labels(self, monitor_wall_spec, temp_output_dir):
        """Test that MonitorWall has proper ARIA labels."""
        backend = NextjsSemanticBackend()
        backend.generate(monitor_wall_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "monitor-wall-test" / "src" / "components" / "archetypes" / "MonitorWall.tsx"
        )
        content = component_path.read_text()

        # Check ARIA attributes
        assert 'aria-label="Monitor wall dashboard"' in content

    def test_monitor_wall_has_grid_layout(self, monitor_wall_spec, temp_output_dir):
        """Test that MonitorWall uses grid layout."""
        backend = NextjsSemanticBackend()
        backend.generate(monitor_wall_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "monitor-wall-test" / "src" / "components" / "archetypes" / "MonitorWall.tsx"
        )
        content = component_path.read_text()

        # Check grid classes
        assert 'grid' in content


class TestCommandCenterComponent:
    """Tests for CommandCenter archetype component."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def command_center_spec(self):
        """Create AppSpec that generates CommandCenter archetype."""
        signals = [
            AttentionSignal(
                id=f"signal{i}",
                kind=AttentionSignalKind.KPI if i % 2 == 0 else AttentionSignalKind.CHART,
                label=f"Metric {i}",
                source="data",
                attention_weight=0.1,
            )
            for i in range(10)  # 10 signals -> COMMAND_CENTER
        ]

        workspace = WorkspaceLayout(
            id="command",
            label="Command Center",
            attention_budget=1.0,
            attention_signals=signals,
        )

        return AppSpec(
            name="command_center_test",
            title="Command Center Test",
            domain=DomainSpec(entities=[]),
            ux=UXLayouts(workspaces=[workspace], personas=[]),
        )

    def test_command_center_has_semantic_html(self, command_center_spec, temp_output_dir):
        """Test that CommandCenter uses semantic HTML."""
        backend = NextjsSemanticBackend()
        backend.generate(command_center_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "command-center-test" / "src" / "components" / "archetypes" / "CommandCenter.tsx"
        )
        content = component_path.read_text()

        # Check semantic HTML (CommandCenter uses sections within a div container)
        assert '<section' in content

    def test_command_center_has_aria_labels(self, command_center_spec, temp_output_dir):
        """Test that CommandCenter has proper ARIA labels."""
        backend = NextjsSemanticBackend()
        backend.generate(command_center_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "command-center-test" / "src" / "components" / "archetypes" / "CommandCenter.tsx"
        )
        content = component_path.read_text()

        # Check ARIA attributes
        assert 'aria-label="Command center dashboard"' in content

    def test_command_center_has_dense_grid(self, command_center_spec, temp_output_dir):
        """Test that CommandCenter uses dense grid layout."""
        backend = NextjsSemanticBackend()
        backend.generate(command_center_spec, temp_output_dir)

        component_path = (
            temp_output_dir / "command-center-test" / "src" / "components" / "archetypes" / "CommandCenter.tsx"
        )
        content = component_path.read_text()

        # Check dense grid classes
        assert 'grid' in content


class TestArchetypeRouter:
    """Tests for ArchetypeRouter component."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def minimal_spec(self):
        """Create minimal AppSpec."""
        workspace = WorkspaceLayout(
            id="test",
            label="Test",
            attention_budget=1.0,
            attention_signals=[
                AttentionSignal(
                    id="kpi",
                    kind=AttentionSignalKind.KPI,
                    label="KPI",
                    source="data",
                    attention_weight=0.9,
                )
            ],
        )

        return AppSpec(
            name="router_test",
            title="Router Test",
            domain=DomainSpec(entities=[]),
            ux=UXLayouts(workspaces=[workspace], personas=[]),
        )

    def test_archetype_router_handles_all_archetypes(self, minimal_spec, temp_output_dir):
        """Test that ArchetypeRouter handles all 5 archetypes."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec, temp_output_dir)

        router_path = (
            temp_output_dir / "router-test" / "src" / "components" / "archetypes" / "ArchetypeRouter.tsx"
        )
        content = router_path.read_text()

        # Check all archetype cases
        assert 'FOCUS_METRIC' in content
        assert 'SCANNER_TABLE' in content
        assert 'DUAL_PANE_FLOW' in content
        assert 'MONITOR_WALL' in content
        assert 'COMMAND_CENTER' in content

        # Check component imports
        assert 'import { FocusMetric }' in content
        assert 'import { ScannerTable }' in content
        assert 'import { DualPaneFlow }' in content
        assert 'import { MonitorWall }' in content
        assert 'import { CommandCenter }' in content

    def test_archetype_router_has_fallback(self, minimal_spec, temp_output_dir):
        """Test that ArchetypeRouter has default case."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec, temp_output_dir)

        router_path = (
            temp_output_dir / "router-test" / "src" / "components" / "archetypes" / "ArchetypeRouter.tsx"
        )
        content = router_path.read_text()

        # Check default case
        assert 'default:' in content or 'Unknown archetype' in content
