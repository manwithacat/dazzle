"""
Tests for DNR-UI runtime module.
"""

import json
import tempfile
from pathlib import Path

import pytest

from dazzle_dnr_ui.specs import (
    UISpec,
    WorkspaceSpec,
    ComponentSpec,
    ThemeSpec,
    ThemeTokens,
    RouteSpec,
    SingleColumnLayout,
    PropsSchema,
    PropFieldSpec,
    StateSpec,
    StateScope,
)
from dazzle_dnr_ui.specs.view import ElementNode, TextNode
from dazzle_dnr_ui.specs.state import LiteralBinding, PropBinding
from dazzle_dnr_ui.runtime.js_generator import (
    JSGenerator,
    generate_js_app,
    generate_single_html,
)


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
