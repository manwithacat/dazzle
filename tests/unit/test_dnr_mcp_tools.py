"""
Tests for DNR MCP tools.

Tests the MCP tool interface for DNR BackendSpec and UISpec manipulation.
"""

import json

import pytest

from dazzle.mcp.dnr_tools_impl import (
    DNR_TOOL_NAMES,
    LAYOUT_TYPES,
    PATTERN_COMPONENTS,
    PRIMITIVE_COMPONENTS,
    get_ui_spec,
    handle_dnr_tool,
    set_backend_spec,
    set_ui_spec,
)


class TestDNRToolNames:
    """Test that all expected tools are defined."""

    def test_backend_tools_defined(self):
        """Verify backend tools are in DNR_TOOL_NAMES."""
        backend_tools = [
            "list_dnr_entities",
            "get_dnr_entity",
            "list_backend_services",
            "get_backend_service_spec",
        ]
        for tool in backend_tools:
            assert tool in DNR_TOOL_NAMES

    def test_ui_tools_defined(self):
        """Verify UI tools are in DNR_TOOL_NAMES."""
        ui_tools = [
            "list_dnr_components",
            "get_dnr_component_spec",
            "list_workspace_layouts",
            "create_uispec_component",
            "patch_uispec_component",
            "compose_workspace",
        ]
        for tool in ui_tools:
            assert tool in DNR_TOOL_NAMES


class TestBackendTools:
    """Test backend-related DNR tools."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear any existing spec
        set_backend_spec(None)

    def test_list_entities_no_spec(self):
        """Test list_dnr_entities with no spec loaded."""
        result = json.loads(handle_dnr_tool("list_dnr_entities", {}))
        assert result["status"] == "no_spec"
        assert result["entities"] == []

    def test_list_entities_with_spec(self):
        """Test list_dnr_entities with a spec loaded."""
        set_backend_spec(
            {
                "name": "test_backend",
                "entities": [
                    {
                        "name": "Client",
                        "label": "Client",
                        "fields": [{"name": "id"}, {"name": "name"}],
                    },
                    {
                        "name": "Invoice",
                        "label": "Invoice",
                        "fields": [{"name": "id"}],
                        "relations": [{"name": "client"}],
                    },
                ],
            }
        )

        result = json.loads(handle_dnr_tool("list_dnr_entities", {}))
        assert result["count"] == 2
        assert len(result["entities"]) == 2
        assert result["entities"][0]["name"] == "Client"
        assert result["entities"][0]["field_count"] == 2

    def test_get_entity(self):
        """Test get_dnr_entity."""
        set_backend_spec(
            {
                "entities": [
                    {
                        "name": "Client",
                        "label": "Client",
                        "fields": [{"name": "id"}, {"name": "name"}],
                    },
                ],
            }
        )

        result = json.loads(handle_dnr_tool("get_dnr_entity", {"name": "Client"}))
        assert result["name"] == "Client"
        assert len(result["fields"]) == 2

    def test_get_entity_not_found(self):
        """Test get_dnr_entity with unknown entity."""
        set_backend_spec({"entities": []})

        result = json.loads(handle_dnr_tool("get_dnr_entity", {"name": "Unknown"}))
        assert "error" in result
        assert "Unknown" in result["error"]

    def test_list_services(self):
        """Test list_backend_services."""
        set_backend_spec(
            {
                "services": [
                    {
                        "name": "create_client",
                        "domain_operation": {"kind": "create", "entity": "Client"},
                        "inputs": {"fields": [{"name": "name"}]},
                        "outputs": {"fields": [{"name": "client"}]},
                    },
                ],
            }
        )

        result = json.loads(handle_dnr_tool("list_backend_services", {}))
        assert result["count"] == 1
        assert result["services"][0]["name"] == "create_client"
        assert result["services"][0]["entity"] == "Client"

    def test_list_services_filtered(self):
        """Test list_backend_services with entity filter."""
        set_backend_spec(
            {
                "services": [
                    {
                        "name": "create_client",
                        "domain_operation": {"entity": "Client"},
                        "inputs": {},
                        "outputs": {},
                    },
                    {
                        "name": "create_invoice",
                        "domain_operation": {"entity": "Invoice"},
                        "inputs": {},
                        "outputs": {},
                    },
                ],
            }
        )

        result = json.loads(handle_dnr_tool("list_backend_services", {"entity_name": "Client"}))
        assert result["count"] == 1
        assert result["services"][0]["name"] == "create_client"


class TestUITools:
    """Test UI-related DNR tools."""

    def setup_method(self):
        """Set up test fixtures."""
        set_ui_spec(None)

    def test_list_components_all(self):
        """Test list_dnr_components with default (all)."""
        result = json.loads(handle_dnr_tool("list_dnr_components", {}))
        # Should have primitives + patterns
        expected_count = len(PRIMITIVE_COMPONENTS) + len(PATTERN_COMPONENTS)
        assert result["count"] == expected_count

    def test_list_components_primitives(self):
        """Test list_dnr_components for primitives only."""
        result = json.loads(handle_dnr_tool("list_dnr_components", {"kind": "primitives"}))
        assert result["count"] == len(PRIMITIVE_COMPONENTS)
        for comp in result["components"]:
            assert comp["category"] == "primitive"

    def test_list_components_patterns(self):
        """Test list_dnr_components for patterns only."""
        result = json.loads(handle_dnr_tool("list_dnr_components", {"kind": "patterns"}))
        assert result["count"] == len(PATTERN_COMPONENTS)
        for comp in result["components"]:
            assert comp["category"] == "pattern"

    def test_get_component_primitive(self):
        """Test get_dnr_component_spec for a primitive."""
        result = json.loads(handle_dnr_tool("get_dnr_component_spec", {"name": "DataTable"}))
        assert "componentSpec" in result
        assert result["componentSpec"]["name"] == "DataTable"
        assert result["componentSpec"]["category"] == "primitive"

    def test_get_component_pattern(self):
        """Test get_dnr_component_spec for a pattern."""
        result = json.loads(handle_dnr_tool("get_dnr_component_spec", {"name": "FilterableTable"}))
        assert "componentSpec" in result
        assert result["componentSpec"]["name"] == "FilterableTable"
        assert result["componentSpec"]["category"] == "pattern"

    def test_get_component_not_found(self):
        """Test get_dnr_component_spec with unknown component."""
        result = json.loads(handle_dnr_tool("get_dnr_component_spec", {"name": "UnknownComponent"}))
        assert "error" in result

    def test_list_workspace_layouts(self):
        """Test list_workspace_layouts."""
        result = json.loads(handle_dnr_tool("list_workspace_layouts", {}))
        assert "layouts" in result
        assert len(result["layouts"]) == len(LAYOUT_TYPES)
        layout_kinds = {lt["kind"] for lt in result["layouts"]}
        assert "singleColumn" in layout_kinds
        assert "appShell" in layout_kinds

    def test_create_component(self):
        """Test create_uispec_component."""
        result = json.loads(
            handle_dnr_tool(
                "create_uispec_component",
                {
                    "name": "ClientDetails",
                    "description": "Shows client details in a card",
                    "atoms": ["Card", "Form"],
                },
            )
        )

        assert result["status"] == "created"
        assert result["componentSpec"]["name"] == "ClientDetails"
        assert result["componentSpec"]["category"] == "custom"

        # Verify it was added to UISpec
        ui_spec = get_ui_spec()
        assert ui_spec is not None
        assert len(ui_spec["components"]) == 1
        assert ui_spec["components"][0]["name"] == "ClientDetails"

    def test_create_component_invalid_name(self):
        """Test create_uispec_component with invalid name."""
        result = json.loads(
            handle_dnr_tool(
                "create_uispec_component",
                {
                    "name": "invalidName",  # Not PascalCase
                    "description": "Test",
                    "atoms": ["Card"],
                },
            )
        )
        assert "error" in result

    def test_create_component_invalid_atom(self):
        """Test create_uispec_component with unknown atom."""
        result = json.loads(
            handle_dnr_tool(
                "create_uispec_component",
                {
                    "name": "TestComponent",
                    "description": "Test",
                    "atoms": ["UnknownAtom"],
                },
            )
        )
        assert "error" in result
        assert "UnknownAtom" in str(result)

    def test_compose_workspace(self):
        """Test compose_workspace."""
        result = json.loads(
            handle_dnr_tool(
                "compose_workspace",
                {
                    "workspace_name": "dashboard",
                    "layout_kind": "appShell",
                    "region_components": {
                        "sidebar": "SideNav",
                        "main": "DataTable",
                        "header": "TopNav",
                    },
                    "routes": [
                        {"path": "/", "component": "Overview"},
                    ],
                },
            )
        )

        assert result["status"] == "created"
        assert result["workspaceSpec"]["name"] == "dashboard"
        assert result["workspaceSpec"]["layout"]["kind"] == "appShell"

        # Verify it was added to UISpec
        ui_spec = get_ui_spec()
        assert ui_spec is not None
        assert len(ui_spec["workspaces"]) == 1

    def test_compose_workspace_update(self):
        """Test compose_workspace updates existing workspace."""
        # Create first
        handle_dnr_tool(
            "compose_workspace",
            {
                "workspace_name": "dashboard",
                "layout_kind": "singleColumn",
                "region_components": {"main": "Card"},
                "routes": [],
            },
        )

        # Update
        result = json.loads(
            handle_dnr_tool(
                "compose_workspace",
                {
                    "workspace_name": "dashboard",
                    "layout_kind": "appShell",
                    "region_components": {"sidebar": "SideNav", "main": "DataTable"},
                    "routes": [],
                },
            )
        )

        assert result["status"] == "updated"
        assert result["workspaceSpec"]["layout"]["kind"] == "appShell"

        # Verify only one workspace
        ui_spec = get_ui_spec()
        assert len(ui_spec["workspaces"]) == 1


class TestPatchComponent:
    """Test patch_uispec_component tool."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a component to patch
        set_ui_spec(
            {
                "name": "test",
                "components": [
                    {
                        "name": "TestComponent",
                        "description": "Original description",
                        "category": "custom",
                    },
                ],
                "workspaces": [],
                "themes": [],
            }
        )

    def test_patch_component_replace(self):
        """Test patching a component with replace operation."""
        result = json.loads(
            handle_dnr_tool(
                "patch_uispec_component",
                {
                    "name": "TestComponent",
                    "patch": [
                        {"op": "replace", "path": "/description", "value": "Updated description"},
                    ],
                },
            )
        )

        assert result["status"] == "patched"
        assert result["componentSpec"]["description"] == "Updated description"

    def test_patch_component_not_found(self):
        """Test patching non-existent component."""
        result = json.loads(
            handle_dnr_tool(
                "patch_uispec_component",
                {
                    "name": "NonExistent",
                    "patch": [],
                },
            )
        )
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
