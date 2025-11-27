"""Tests for Next.js Semantic UI stack."""

import pytest
from pathlib import Path
import tempfile
import shutil

from dazzle.core.ir import (
    AppSpec,
    AttentionSignal,
    AttentionSignalKind,
    DomainSpec,
    LayoutArchetype,
    UXLayouts,
    WorkspaceLayout,
)
from dazzle.stacks.nextjs_semantic import NextjsSemanticBackend


class TestNextjsSemanticBackend:
    """Tests for Next.js Semantic UI backend."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def minimal_spec_with_workspace(self):
        """Create minimal AppSpec with a workspace."""
        workspace = WorkspaceLayout(
            id="dashboard",
            label="Dashboard",
            attention_budget=1.0,
            attention_signals=[
                AttentionSignal(
                    id="kpi1",
                    kind=AttentionSignalKind.KPI,
                    label="Active Users",
                    source="analytics",
                    attention_weight=0.9,
                )
            ],
        )

        return AppSpec(
            name="test_app",
            title="Test App",
            domain=DomainSpec(entities=[]),
            ux=UXLayouts(
                workspaces=[workspace],
                personas=[],
            ),
        )

    def test_backend_capabilities(self):
        """Test that backend reports correct capabilities."""
        backend = NextjsSemanticBackend()
        caps = backend.get_capabilities()

        assert caps.name == "nextjs_semantic"
        assert "Next.js" in caps.description
        assert "typescript" in caps.output_formats
        assert "tsx" in caps.output_formats

    def test_generates_package_json(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that package.json is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        package_json = temp_output_dir / "test-app" / "package.json"
        assert package_json.exists()

        import json
        with open(package_json) as f:
            data = json.load(f)

        assert data["name"] == "test-app"
        assert "next" in data["dependencies"]
        assert "react" in data["dependencies"]
        assert "tailwindcss" in data["devDependencies"]

    def test_generates_next_config(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that next.config.js is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        config = temp_output_dir / "test-app" / "next.config.js"
        assert config.exists()
        assert "nextConfig" in config.read_text()

    def test_generates_tsconfig(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that tsconfig.json is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        tsconfig = temp_output_dir / "test-app" / "tsconfig.json"
        assert tsconfig.exists()

        import json
        with open(tsconfig) as f:
            data = json.load(f)

        assert "compilerOptions" in data
        assert data["compilerOptions"]["strict"] is True

    def test_generates_tailwind_config(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that tailwind.config.ts is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        tailwind = temp_output_dir / "test-app" / "tailwind.config.ts"
        assert tailwind.exists()
        content = tailwind.read_text()
        assert "Config" in content
        assert "content" in content

    def test_generates_globals_css(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that globals.css with Tailwind is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        globals = temp_output_dir / "test-app" / "src" / "app" / "globals.css"
        assert globals.exists()
        content = globals.read_text()
        assert "@tailwind base" in content
        assert "@tailwind components" in content
        assert "@tailwind utilities" in content

    def test_generates_layout_types(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that TypeScript layout types are generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        layout_types = temp_output_dir / "test-app" / "src" / "types" / "layout.ts"
        assert layout_types.exists()
        content = layout_types.read_text()

        assert "LayoutArchetype" in content
        assert "AttentionSignalKind" in content
        assert "LayoutPlan" in content
        assert "WorkspaceLayout" in content

    def test_generates_archetype_components(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that all 5 archetype components are generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        archetypes_dir = temp_output_dir / "test-app" / "src" / "components" / "archetypes"

        # Check all 5 archetype components exist
        assert (archetypes_dir / "FocusMetric.tsx").exists()
        assert (archetypes_dir / "ScannerTable.tsx").exists()
        assert (archetypes_dir / "DualPaneFlow.tsx").exists()
        assert (archetypes_dir / "MonitorWall.tsx").exists()
        assert (archetypes_dir / "CommandCenter.tsx").exists()

        # Check router exists
        assert (archetypes_dir / "ArchetypeRouter.tsx").exists()
        router_content = (archetypes_dir / "ArchetypeRouter.tsx").read_text()
        assert "switch" in router_content.lower()
        assert "FOCUS_METRIC" in router_content

    def test_generates_signal_renderer(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that SignalRenderer component is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        signal_renderer = (
            temp_output_dir / "test-app" / "src" / "components" / "signals" / "SignalRenderer.tsx"
        )
        assert signal_renderer.exists()
        content = signal_renderer.read_text()

        # Check it handles all signal kinds
        assert "AttentionSignalKind.KPI" in content
        assert "AttentionSignalKind.TABLE" in content
        assert "AttentionSignalKind.CHART" in content

    def test_generates_root_layout(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that root layout is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        layout = temp_output_dir / "test-app" / "src" / "app" / "layout.tsx"
        assert layout.exists()
        content = layout.read_text()

        assert "Test App" in content  # Title from spec
        assert "RootLayout" in content
        assert "globals.css" in content

    def test_generates_home_page(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that home page is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        home = temp_output_dir / "test-app" / "src" / "app" / "page.tsx"
        assert home.exists()
        content = home.read_text()

        assert "Test App" in content
        assert "dashboard" in content.lower()  # Workspace link

    def test_generates_workspace_pages(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that workspace pages are generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        workspace_page = (
            temp_output_dir / "test-app" / "src" / "app" / "dashboard" / "page.tsx"
        )
        assert workspace_page.exists()
        content = workspace_page.read_text()

        assert "Dashboard" in content  # Workspace label
        assert "ArchetypeRouter" in content
        assert "layoutPlan" in content
        assert "FOCUS_METRIC" in content  # Expected archetype

    def test_workspace_page_includes_signals(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that workspace page includes signal definitions."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        workspace_page = (
            temp_output_dir / "test-app" / "src" / "app" / "dashboard" / "page.tsx"
        )
        content = workspace_page.read_text()

        # Check signal is included
        assert "kpi1" in content
        assert "Active Users" in content
        assert "AttentionSignalKind.KPI" in content

    def test_creates_correct_directory_structure(
        self, minimal_spec_with_workspace, temp_output_dir
    ):
        """Test that correct Next.js App Router directory structure is created."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        project_root = temp_output_dir / "test-app"

        # Check Next.js App Router structure
        assert (project_root / "src").is_dir()
        assert (project_root / "src" / "app").is_dir()
        assert (project_root / "src" / "components").is_dir()
        assert (project_root / "src" / "components" / "archetypes").is_dir()
        assert (project_root / "src" / "components" / "signals").is_dir()
        assert (project_root / "src" / "lib").is_dir()
        assert (project_root / "src" / "types").is_dir()
        assert (project_root / "public").is_dir()

    def test_handles_multiple_workspaces(self, temp_output_dir):
        """Test that multiple workspaces generate multiple pages."""
        spec = AppSpec(
            name="multi_workspace",
            title="Multi Workspace App",
            domain=DomainSpec(entities=[]),
            ux=UXLayouts(
                workspaces=[
                    WorkspaceLayout(
                        id="dashboard",
                        label="Dashboard",
                        attention_budget=1.0,
                        attention_signals=[
                            AttentionSignal(
                                id="kpi1",
                                kind=AttentionSignalKind.KPI,
                                label="KPI",
                                source="data",
                                attention_weight=0.8,
                            )
                        ],
                    ),
                    WorkspaceLayout(
                        id="reports",
                        label="Reports",
                        attention_budget=1.0,
                        attention_signals=[
                            AttentionSignal(
                                id="table1",
                                kind=AttentionSignalKind.TABLE,
                                label="Table",
                                source="data",
                                attention_weight=0.9,
                            )
                        ],
                    ),
                ],
                personas=[],
            ),
        )

        backend = NextjsSemanticBackend()
        backend.generate(spec, temp_output_dir)

        # Check both workspace pages exist
        dashboard_page = (
            temp_output_dir / "multi-workspace" / "src" / "app" / "dashboard" / "page.tsx"
        )
        reports_page = (
            temp_output_dir / "multi-workspace" / "src" / "app" / "reports" / "page.tsx"
        )

        assert dashboard_page.exists()
        assert reports_page.exists()

        # Check home page links to both
        home_page = temp_output_dir / "multi-workspace" / "src" / "app" / "page.tsx"
        home_content = home_page.read_text()
        assert "dashboard" in home_content.lower()
        assert "reports" in home_content.lower()

    def test_generates_gitignore(self, minimal_spec_with_workspace, temp_output_dir):
        """Test that .gitignore is generated."""
        backend = NextjsSemanticBackend()
        backend.generate(minimal_spec_with_workspace, temp_output_dir)

        gitignore = temp_output_dir / "test-app" / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()

        assert "node_modules" in content
        assert ".next" in content
        assert ".env" in content
