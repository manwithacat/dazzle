"""
Tests for UISpec types.

Basic validation and construction tests to ensure specs work correctly.
"""

import pytest
from dazzle_dnr_ui.specs import (
    UISpec,
    WorkspaceSpec,
    ComponentSpec,
    ElementNode,
    StateSpec,
    StateScope,
    ActionSpec,
    ThemeSpec,
    ThemeTokens,
    TextStyle,
    SingleColumnLayout,
    AppShellLayout,
    RouteSpec,
    PropsSchema,
    PropFieldSpec,
    LiteralBinding,
    PropBinding,
)


def test_component_spec_creation():
    """Test creating a ComponentSpec."""
    component = ComponentSpec(
        name="ClientCard",
        category="custom",
        props_schema=PropsSchema(
            fields=[
                PropFieldSpec(name="client", type="Client", required=True),
            ]
        ),
    )
    assert component.name == "ClientCard"
    assert component.is_custom is True
    assert len(component.props_schema.fields) == 1


def test_workspace_spec_creation():
    """Test creating a WorkspaceSpec."""
    workspace = WorkspaceSpec(
        name="dashboard",
        layout=SingleColumnLayout(main="DashboardContent"),
        routes=[
            RouteSpec(path="/", component="Overview"),
            RouteSpec(path="/metrics", component="Metrics"),
        ],
    )
    assert workspace.name == "dashboard"
    assert workspace.layout_kind == "singleColumn"
    assert len(workspace.routes) == 2
    assert workspace.get_route("/") is not None


def test_theme_spec_creation():
    """Test creating a ThemeSpec."""
    theme = ThemeSpec(
        name="default",
        tokens=ThemeTokens(
            colors={"primary": "#0066cc", "background": "#ffffff"},
            spacing={"sm": 8, "md": 16, "lg": 24},
            typography={
                "body": TextStyle(font_size="16px", font_weight="400"),
            },
        ),
    )
    assert theme.name == "default"
    assert theme.tokens.colors["primary"] == "#0066cc"
    assert theme.tokens.spacing["md"] == 16


def test_state_spec_creation():
    """Test creating a StateSpec."""
    state = StateSpec(
        name="selectedClient",
        scope=StateScope.WORKSPACE,
        initial=None,
    )
    assert state.name == "selectedClient"
    assert state.scope == StateScope.WORKSPACE
    assert state.initial is None


def test_action_spec_creation():
    """Test creating an ActionSpec."""
    action = ActionSpec(
        name="selectClient",
        inputs={"client_id": "uuid"},
    )
    assert action.name == "selectClient"
    assert action.inputs["client_id"] == "uuid"


def test_element_node_creation():
    """Test creating an ElementNode."""
    node = ElementNode(
        as_="Card",
        props={
            "title": LiteralBinding(value="Client Details"),
            "client": PropBinding(path="client"),
        },
    )
    assert node.as_ == "Card"
    assert len(node.props) == 2
    assert node.props["title"].kind == "literal"


def test_ui_spec_creation():
    """Test creating a complete UISpec."""
    spec = UISpec(
        name="test_ui",
        version="1.0.0",
        components=[
            ComponentSpec(name="TestComponent", category="custom"),
        ],
        workspaces=[
            WorkspaceSpec(
                name="main",
                layout=SingleColumnLayout(main="TestComponent"),
                routes=[],
            )
        ],
        themes=[
            ThemeSpec(
                name="default",
                tokens=ThemeTokens(),
            )
        ],
    )

    assert spec.name == "test_ui"
    assert len(spec.components) == 1
    assert len(spec.workspaces) == 1
    assert len(spec.themes) == 1

    # Test query methods
    assert spec.get_component("TestComponent") is not None
    assert spec.get_workspace("main") is not None
    assert spec.get_theme("default") is not None

    # Test stats
    stats = spec.stats
    assert stats["components"] == 1
    assert stats["workspaces"] == 1
    assert stats["themes"] == 1


def test_ui_spec_validation():
    """Test UISpec reference validation."""
    # Valid spec
    spec = UISpec(
        name="valid_ui",
        components=[
            ComponentSpec(name="MainContent", category="custom"),
        ],
        workspaces=[
            WorkspaceSpec(
                name="main",
                layout=SingleColumnLayout(main="MainContent"),
                routes=[],
            )
        ],
    )
    errors = spec.validate_references()
    assert len(errors) == 0

    # Invalid spec: workspace references non-existent component
    bad_spec = UISpec(
        name="invalid_ui",
        workspaces=[
            WorkspaceSpec(
                name="main",
                layout=SingleColumnLayout(main="NonExistentComponent"),
                routes=[],
            )
        ],
    )
    errors = bad_spec.validate_references()
    assert len(errors) > 0
    assert "NonExistentComponent" in errors[0]


def test_immutability():
    """Test that specs are immutable (frozen)."""
    component = ComponentSpec(name="Test", category="custom")

    with pytest.raises((AttributeError, TypeError)):
        component.name = "NewName"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
