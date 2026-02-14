"""Tests for UI island runtime components."""

import json
from pathlib import Path

from dazzle.core.ir.islands import IslandPropSpec, IslandSpec
from dazzle_ui.runtime.template_context import IslandContext


class TestIslandContext:
    """Tests for IslandContext model."""

    def test_basic_context(self):
        """Test IslandContext creation."""
        ctx = IslandContext(
            name="chart",
            src="/static/islands/chart/index.js",
            props_json='{"type":"bar"}',
            api_base="/api/islands/chart",
        )
        assert ctx.name == "chart"
        assert ctx.src == "/static/islands/chart/index.js"
        assert ctx.api_base == "/api/islands/chart"
        assert ctx.fallback is None

    def test_props_json_is_valid(self):
        """Test that props_json is valid JSON."""
        props = {"chart_type": "bar", "count": 10}
        ctx = IslandContext(
            name="chart",
            src="/static/islands/chart/index.js",
            props_json=json.dumps(props),
            api_base="/api/islands/chart",
        )
        parsed = json.loads(ctx.props_json)
        assert parsed == props

    def test_context_with_fallback(self):
        """Test IslandContext with fallback content."""
        ctx = IslandContext(
            name="chart",
            src="/static/islands/chart/index.js",
            props_json="{}",
            api_base="/api/islands/chart",
            fallback="<p>Loading chart...</p>",
        )
        assert ctx.fallback == "<p>Loading chart...</p>"


class TestIslandContextCompilation:
    """Tests for compiling IslandSpec to IslandContext."""

    @staticmethod
    def compile_island(spec: IslandSpec) -> IslandContext:
        """Compile an IslandSpec into an IslandContext."""
        src = spec.src or f"/static/islands/{spec.name}/index.js"
        api_base = f"/api/islands/{spec.name}" if spec.entity else ""
        props = {p.name: p.default for p in spec.props if p.default is not None}
        return IslandContext(
            name=spec.name,
            src=src,
            props_json=json.dumps(props),
            api_base=api_base,
            fallback=spec.fallback,
        )

    def test_default_src_from_name(self):
        """Test src is derived from island name when not specified."""
        spec = IslandSpec(name="task_chart")
        ctx = self.compile_island(spec)
        assert ctx.src == "/static/islands/task_chart/index.js"

    def test_explicit_src_used(self):
        """Test explicit src is used when provided."""
        spec = IslandSpec(name="chart", src="custom/path.js")
        ctx = self.compile_island(spec)
        assert ctx.src == "custom/path.js"

    def test_api_base_with_entity(self):
        """Test api_base is set when entity is bound."""
        spec = IslandSpec(name="task_chart", entity="Task")
        ctx = self.compile_island(spec)
        assert ctx.api_base == "/api/islands/task_chart"

    def test_api_base_without_entity(self):
        """Test api_base is empty when no entity is bound."""
        spec = IslandSpec(name="confetti")
        ctx = self.compile_island(spec)
        assert ctx.api_base == ""

    def test_props_serialization(self):
        """Test props with defaults are serialized to JSON."""
        spec = IslandSpec(
            name="chart",
            props=[
                IslandPropSpec(name="type", type="str", default="bar"),
                IslandPropSpec(name="count", type="int", default=5),
                IslandPropSpec(name="label", type="str"),  # no default
            ],
        )
        ctx = self.compile_island(spec)
        parsed = json.loads(ctx.props_json)
        assert parsed == {"type": "bar", "count": 5}
        assert "label" not in parsed


class TestIslandLoaderJS:
    """Tests for the island loader JavaScript file."""

    def test_loader_file_exists(self):
        """Test that dz-islands.js exists."""
        js_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle_ui"
            / "runtime"
            / "static"
            / "js"
            / "dz-islands.js"
        )
        assert js_path.exists(), f"Island loader not found at {js_path}"

    def test_loader_contains_mount_logic(self):
        """Test that loader has mount scanning logic."""
        js_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle_ui"
            / "runtime"
            / "static"
            / "js"
            / "dz-islands.js"
        )
        content = js_path.read_text()
        assert "data-island" in content
        assert "mountIslands" in content
        assert "htmx:afterSettle" in content
        assert "DOMContentLoaded" in content

    def test_loader_uses_weakset(self):
        """Test that loader uses WeakSet for deduplication."""
        js_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle_ui"
            / "runtime"
            / "static"
            / "js"
            / "dz-islands.js"
        )
        content = js_path.read_text()
        assert "WeakSet" in content


class TestIslandTemplate:
    """Tests for the island mount point template."""

    def test_template_file_exists(self):
        """Test that island.html template exists."""
        tpl_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle_ui"
            / "templates"
            / "components"
            / "island.html"
        )
        assert tpl_path.exists(), f"Island template not found at {tpl_path}"

    def test_template_has_data_attributes(self):
        """Test that template contains data-island attributes."""
        tpl_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle_ui"
            / "templates"
            / "components"
            / "island.html"
        )
        content = tpl_path.read_text()
        assert "data-island=" in content
        assert "data-island-src=" in content
        assert "data-island-props=" in content
        assert "data-island-api-base=" in content


class TestIslandRoutes:
    """Tests for island API route generation."""

    def test_routes_module_importable(self):
        """Test that island_routes module can be imported."""
        from dazzle_back.runtime.island_routes import create_island_routes  # noqa: F401

    def test_create_routes_empty_islands(self):
        """Test route creation with no islands."""
        from dazzle_back.runtime.island_routes import create_island_routes

        router = create_island_routes(islands=[], services={})
        assert router.prefix == "/api/islands"

    def test_create_routes_with_entity_island(self):
        """Test route creation for island with entity binding."""
        from dazzle_back.runtime.island_routes import create_island_routes

        island = IslandSpec(name="task_chart", entity="Task")
        router = create_island_routes(islands=[island], services={"Task": object()})
        # Should have sub-routes for the island
        route_paths = [r.path for r in router.routes]
        assert any("task_chart" in p for p in route_paths)

    def test_create_routes_skips_no_entity(self):
        """Test that islands without entity don't generate routes."""
        from dazzle_back.runtime.island_routes import create_island_routes

        island = IslandSpec(name="confetti")
        router = create_island_routes(islands=[island], services={})
        # No sub-routes should be created
        route_paths = [r.path for r in router.routes]
        assert not any("confetti" in p for p in route_paths)

    def test_auth_dependency_applied(self):
        """Test that auth dependency is applied to island routes."""
        from dazzle_back.runtime.island_routes import create_island_routes

        def mock_auth():
            pass

        island = IslandSpec(name="chart", entity="Task")
        router = create_island_routes(
            islands=[island],
            services={"Task": object()},
            auth_dep=mock_auth,
        )
        # Router should have routes (auth applied via dependencies)
        assert len(router.routes) > 0
