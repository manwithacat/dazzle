"""
Tests for DNR-UI runtime module.
"""

import json
import tempfile
from pathlib import Path

import pytest

from dazzle_dnr_ui.runtime.js_generator import (
    JSGenerator,
    generate_js_app,
    generate_single_html,
)
from dazzle_dnr_ui.specs import (
    ComponentSpec,
    PropFieldSpec,
    PropsSchema,
    RouteSpec,
    SingleColumnLayout,
    StateScope,
    StateSpec,
    ThemeSpec,
    ThemeTokens,
    UISpec,
    WorkspaceSpec,
)
from dazzle_dnr_ui.specs.state import LiteralBinding
from dazzle_dnr_ui.specs.view import ElementNode, TextNode

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_ui_spec() -> UISpec:
    """Create a simple UI spec for testing."""
    return UISpec(
        name="test_app",
        version="1.0.0",
        description="Test application",
        workspaces=[
            WorkspaceSpec(
                name="main",
                label="Main Workspace",
                layout=SingleColumnLayout(main="MainPage"),
                routes=[
                    RouteSpec(path="/", component="MainPage", title="Home"),
                    RouteSpec(path="/about", component="AboutPage", title="About"),
                ],
            ),
        ],
        components=[
            ComponentSpec(
                name="MainPage",
                description="Main page component",
                category="custom",
                props_schema=PropsSchema(
                    fields=[
                        PropFieldSpec(name="title", type="str", required=False),
                    ]
                ),
                view=ElementNode(
                    as_="Page",
                    props={"title": LiteralBinding(value="Welcome")},
                    children=[
                        ElementNode(
                            as_="Card",
                            props={"title": LiteralBinding(value="Hello World")},
                            children=[
                                TextNode(content=LiteralBinding(value="This is a test app."))
                            ],
                        ),
                    ],
                ),
                state=[
                    StateSpec(
                        name="counter",
                        scope=StateScope.LOCAL,
                        initial=0,
                    ),
                ],
            ),
            ComponentSpec(
                name="AboutPage",
                description="About page",
                view=ElementNode(
                    as_="Page",
                    props={"title": LiteralBinding(value="About")},
                ),
            ),
        ],
        themes=[
            ThemeSpec(
                name="default",
                description="Default theme",
                tokens=ThemeTokens(
                    colors={
                        "primary": "#0066cc",
                        "background": "#ffffff",
                    },
                    spacing={"md": 16},
                    radii={"md": 4},
                ),
            ),
        ],
        default_workspace="main",
        default_theme="default",
    )


# =============================================================================
# JSGenerator Tests
# =============================================================================


class TestJSGenerator:
    """Tests for JavaScript generation."""

    def test_generate_runtime(self, simple_ui_spec: UISpec) -> None:
        """Test runtime generation."""
        generator = JSGenerator(simple_ui_spec)
        runtime = generator.generate_runtime()

        # Check for key runtime components
        assert "DNR" in runtime
        assert "createSignal" in runtime
        assert "createEffect" in runtime
        assert "createElement" in runtime
        assert "registerComponent" in runtime
        assert "renderViewNode" in runtime
        assert "applyTheme" in runtime

    def test_generate_spec_json(self, simple_ui_spec: UISpec) -> None:
        """Test spec JSON generation."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()

        # Parse and validate
        parsed = json.loads(spec_json)
        assert parsed["name"] == "test_app"
        assert parsed["version"] == "1.0.0"
        assert len(parsed["workspaces"]) == 1
        assert len(parsed["components"]) == 2
        assert len(parsed["themes"]) == 1

    def test_generate_app_js(self, simple_ui_spec: UISpec) -> None:
        """Test app JS generation."""
        generator = JSGenerator(simple_ui_spec)
        app_js = generator.generate_app_js()

        # Check for app initialization
        assert "DNR.createApp" in app_js
        assert "uiSpec" in app_js
        assert "test_app" in app_js

    def test_generate_html(self, simple_ui_spec: UISpec) -> None:
        """Test HTML generation."""
        generator = JSGenerator(simple_ui_spec)
        html = generator.generate_html()

        # Check HTML structure
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert '<div id="app">' in html

        # Check for CSS variables
        assert "--color-primary" in html
        assert "--spacing-md" in html

        # Check for runtime code
        assert "DNR" in html

    def test_generate_html_with_title(self, simple_ui_spec: UISpec) -> None:
        """Test HTML generation with custom title."""
        generator = JSGenerator(simple_ui_spec)
        html = generator.generate_html(title="Custom Title")

        assert "<title>Custom Title</title>" in html

    def test_write_to_directory_split(self, simple_ui_spec: UISpec) -> None:
        """Test writing split files to directory."""
        generator = JSGenerator(simple_ui_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = generator.write_to_directory(tmpdir, split_files=True)

            assert len(files) == 4
            assert any(f.name == "dnr-runtime.js" for f in files)
            assert any(f.name == "ui-spec.json" for f in files)
            assert any(f.name == "app.js" for f in files)
            assert any(f.name == "index.html" for f in files)

            # Verify files exist and have content
            for f in files:
                assert f.exists()
                assert f.stat().st_size > 0

    def test_write_to_directory_single(self, simple_ui_spec: UISpec) -> None:
        """Test writing single HTML file."""
        generator = JSGenerator(simple_ui_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = generator.write_to_directory(tmpdir, split_files=False)

            assert len(files) == 1
            assert files[0].name == "index.html"
            assert files[0].exists()

            # Check content includes runtime
            content = files[0].read_text()
            assert "DNR" in content


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_generate_js_app(self, simple_ui_spec: UISpec) -> None:
        """Test generate_js_app function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = generate_js_app(simple_ui_spec, tmpdir)

            assert len(files) == 4
            assert all(f.exists() for f in files)

    def test_generate_single_html(self, simple_ui_spec: UISpec) -> None:
        """Test generate_single_html function."""
        html = generate_single_html(simple_ui_spec)

        assert "<!DOCTYPE html>" in html
        assert "DNR" in html
        assert "test_app" in html


# =============================================================================
# View Node Rendering Tests
# =============================================================================


class TestViewNodeRendering:
    """Tests for view node rendering in generated code."""

    def test_element_node_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that ElementNode is properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        # Find MainPage component
        main_page = next(c for c in parsed["components"] if c["name"] == "MainPage")
        view = main_page["view"]

        assert view["kind"] == "element"
        assert view["as"] == "Page"
        assert "props" in view
        assert "children" in view

    def test_text_node_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that TextNode is properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        # Find MainPage component and traverse to TextNode
        main_page = next(c for c in parsed["components"] if c["name"] == "MainPage")
        card = main_page["view"]["children"][0]
        text_node = card["children"][0]

        assert text_node["kind"] == "text"
        assert text_node["content"]["kind"] == "literal"
        assert text_node["content"]["value"] == "This is a test app."

    def test_literal_binding_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that LiteralBinding is properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        main_page = next(c for c in parsed["components"] if c["name"] == "MainPage")
        title_binding = main_page["view"]["props"]["title"]

        assert title_binding["kind"] == "literal"
        assert title_binding["value"] == "Welcome"


# =============================================================================
# State and Theme Tests
# =============================================================================


class TestStateAndTheme:
    """Tests for state and theme in generated code."""

    def test_state_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that state is properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        main_page = next(c for c in parsed["components"] if c["name"] == "MainPage")
        state = main_page["state"]

        assert len(state) == 1
        assert state[0]["name"] == "counter"
        assert state[0]["scope"] == "local"
        assert state[0]["initial"] == 0

    def test_theme_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that theme is properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        theme = parsed["themes"][0]
        assert theme["name"] == "default"
        assert theme["tokens"]["colors"]["primary"] == "#0066cc"
        assert theme["tokens"]["spacing"]["md"] == 16

    def test_default_theme_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that default_theme is properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        assert parsed["default_theme"] == "default"


# =============================================================================
# Workspace Tests
# =============================================================================


class TestWorkspace:
    """Tests for workspace in generated code."""

    def test_workspace_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that workspace is properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        workspace = parsed["workspaces"][0]
        assert workspace["name"] == "main"
        assert workspace["label"] == "Main Workspace"
        assert len(workspace["routes"]) == 2

    def test_routes_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that routes are properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        routes = parsed["workspaces"][0]["routes"]
        assert routes[0]["path"] == "/"
        assert routes[0]["component"] == "MainPage"
        assert routes[1]["path"] == "/about"
        assert routes[1]["component"] == "AboutPage"

    def test_default_workspace_in_spec(self, simple_ui_spec: UISpec) -> None:
        """Test that default_workspace is properly serialized."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()
        parsed = json.loads(spec_json)

        assert parsed["default_workspace"] == "main"


# =============================================================================
# Vite Generator Tests
# =============================================================================


from dazzle_dnr_ui.runtime.vite_generator import (  # noqa: E402
    ViteGenerator,
    generate_es_modules,
    generate_vite_app,
)


class TestViteGenerator:
    """Tests for Vite project generation."""

    def test_generate_package_json(self, simple_ui_spec: UISpec) -> None:
        """Test package.json generation."""
        generator = ViteGenerator(simple_ui_spec)
        package_json = generator.generate_package_json()

        parsed = json.loads(package_json)
        assert parsed["name"] == "test-app"
        assert parsed["type"] == "module"
        assert "dev" in parsed["scripts"]
        assert parsed["scripts"]["dev"] == "vite"
        assert "vite" in parsed["devDependencies"]

    def test_generate_vite_config(self, simple_ui_spec: UISpec) -> None:
        """Test vite.config.js generation."""
        generator = ViteGenerator(simple_ui_spec)
        config = generator.generate_vite_config()

        assert "defineConfig" in config
        assert "root: 'src'" in config
        assert "port: 3000" in config
        assert "@dnr" in config

    def test_generate_index_html(self, simple_ui_spec: UISpec) -> None:
        """Test index.html generation."""
        generator = ViteGenerator(simple_ui_spec)
        html = generator.generate_index_html()

        assert "<!DOCTYPE html>" in html
        assert "test_app" in html
        assert '<div id="app">' in html
        assert 'type="module"' in html
        assert "main.js" in html

    def test_generate_main_js(self, simple_ui_spec: UISpec) -> None:
        """Test main.js generation."""
        generator = ViteGenerator(simple_ui_spec)
        main_js = generator.generate_main_js()

        assert "import { createApp }" in main_js
        assert "import uiSpec" in main_js
        assert "createApp(uiSpec)" in main_js

    def test_write_to_directory(self, simple_ui_spec: UISpec) -> None:
        """Test writing complete Vite project to directory."""
        generator = ViteGenerator(simple_ui_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = generator.write_to_directory(tmpdir)

            # Check root files
            assert any(f.name == "package.json" for f in files)
            assert any(f.name == "vite.config.js" for f in files)

            # Check src files
            assert any(f.name == "index.html" for f in files)
            assert any(f.name == "main.js" for f in files)
            assert any(f.name == "ui-spec.json" for f in files)

            # Check styles
            assert any(f.name == "dnr.css" for f in files)

            # Check DNR runtime modules
            assert any(f.name == "signals.js" for f in files)
            assert any(f.name == "state.js" for f in files)
            assert any(f.name == "dom.js" for f in files)
            assert any(f.name == "components.js" for f in files)
            assert any(f.name == "renderer.js" for f in files)
            assert any(f.name == "theme.js" for f in files)
            assert any(f.name == "app.js" for f in files)
            assert any(f.name == "index.js" for f in files)

            # Verify all files exist and have content
            for f in files:
                assert f.exists()
                assert f.stat().st_size > 0

    def test_write_runtime_only(self, simple_ui_spec: UISpec) -> None:
        """Test writing only the ES module runtime."""
        generator = ViteGenerator(simple_ui_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = generator.write_runtime_only(tmpdir)

            # Should only have runtime modules
            expected_files = {
                "signals.js",
                "state.js",
                "dom.js",
                "bindings.js",
                "components.js",
                "renderer.js",
                "theme.js",
                "actions.js",
                "app.js",
                "index.js",
            }
            actual_files = {f.name for f in files}
            assert actual_files == expected_files

            # Verify all files exist
            for f in files:
                assert f.exists()

    def test_es_module_structure(self, simple_ui_spec: UISpec) -> None:
        """Test that ES modules have proper import/export structure."""
        generator = ViteGenerator(simple_ui_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = generator.write_runtime_only(tmpdir)

            # Check signals.js exports
            signals_js = next(f for f in files if f.name == "signals.js")
            content = signals_js.read_text()
            assert "export function createSignal" in content
            assert "export function createEffect" in content
            assert "export function createMemo" in content

            # Check state.js imports signals
            state_js = next(f for f in files if f.name == "state.js")
            content = state_js.read_text()
            assert "import { createSignal } from './signals.js'" in content
            assert "export function getState" in content
            assert "export function setState" in content

            # Check dom.js imports signals
            dom_js = next(f for f in files if f.name == "dom.js")
            content = dom_js.read_text()
            assert "import { createEffect } from './signals.js'" in content
            assert "export function createElement" in content
            assert "export function render" in content

            # Check index.js re-exports everything
            index_js = next(f for f in files if f.name == "index.js")
            content = index_js.read_text()
            assert "export { createSignal" in content
            assert "export { createApp }" in content


class TestViteConvenienceFunctions:
    """Tests for Vite convenience functions."""

    def test_generate_vite_app(self, simple_ui_spec: UISpec) -> None:
        """Test generate_vite_app function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = generate_vite_app(simple_ui_spec, tmpdir)

            # Should create complete project
            assert any(f.name == "package.json" for f in files)
            assert any(f.name == "vite.config.js" for f in files)
            assert any(f.name == "signals.js" for f in files)
            assert all(f.exists() for f in files)

    def test_generate_es_modules(self, simple_ui_spec: UISpec) -> None:
        """Test generate_es_modules function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = generate_es_modules(simple_ui_spec, tmpdir)

            # Should only create runtime modules
            assert all(f.suffix == ".js" for f in files)
            assert any(f.name == "signals.js" for f in files)
            assert all(f.exists() for f in files)


class TestViteProjectStructure:
    """Tests for Vite project structure validation."""

    def test_directory_structure(self, simple_ui_spec: UISpec) -> None:
        """Test that proper directory structure is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_vite_app(simple_ui_spec, tmpdir)
            tmpdir = Path(tmpdir)

            # Root level
            assert (tmpdir / "package.json").exists()
            assert (tmpdir / "vite.config.js").exists()

            # src directory
            assert (tmpdir / "src").is_dir()
            assert (tmpdir / "src" / "index.html").exists()
            assert (tmpdir / "src" / "main.js").exists()
            assert (tmpdir / "src" / "ui-spec.json").exists()

            # styles directory
            assert (tmpdir / "src" / "styles").is_dir()
            assert (tmpdir / "src" / "styles" / "dnr.css").exists()

            # dnr runtime directory
            assert (tmpdir / "src" / "dnr").is_dir()
            assert (tmpdir / "src" / "dnr" / "index.js").exists()

    def test_spec_json_in_vite_project(self, simple_ui_spec: UISpec) -> None:
        """Test that UI spec JSON is properly included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_vite_app(simple_ui_spec, tmpdir)
            tmpdir = Path(tmpdir)

            spec_path = tmpdir / "src" / "ui-spec.json"
            parsed = json.loads(spec_path.read_text())

            assert parsed["name"] == "test_app"
            assert len(parsed["components"]) == 2
            assert len(parsed["workspaces"]) == 1
