"""
E2E tests for the Semantic DOM Contract.

These tests verify that DNR-generated UIs include the proper
data-dazzle-* attributes for stack-agnostic E2E testing.

See docs/SEMANTIC_DOM_CONTRACT.md for the full specification.
"""

import pytest

# Skip if DNR is not available
pytest.importorskip("dazzle_dnr_ui")


class TestWithDazzleAttrsHelper:
    """Test the withDazzleAttrs JavaScript helper function."""

    def test_helper_exported_from_dom_js(self) -> None:
        """Verify withDazzleAttrs is exported from dom.js."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Check that withDazzleAttrs function exists in the bundle
        assert "withDazzleAttrs" in bundle, "withDazzleAttrs should be defined in bundle"
        assert "data-dazzle-" in bundle, "Bundle should contain data-dazzle- attribute logic"

    def test_helper_sets_view_attribute(self) -> None:
        """Verify the helper handles view attributes."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # The helper should map 'view' to 'data-dazzle-view'
        assert "view: 'view'" in bundle or "'view'" in bundle


class TestComponentSemanticAttributes:
    """Test that built-in components include semantic attributes."""

    def test_components_import_withDazzleAttrs(self) -> None:
        """Verify components.js imports the semantic attribute helper."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Components should use withDazzleAttrs
        assert "withDazzleAttrs" in bundle, "Components should use withDazzleAttrs"

    def test_button_component_has_action_attributes(self) -> None:
        """Verify Button component adds action semantic attributes."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Button should set action and actionRole attributes
        # The component code should reference these patterns
        assert "action:" in bundle or "dazzle?.action" in bundle.replace(" ", "")
        assert "actionRole" in bundle

    def test_input_component_has_field_attributes(self) -> None:
        """Verify Input component adds field semantic attributes."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Input should set field and fieldType attributes
        assert "field:" in bundle or "dazzle?.field" in bundle.replace(" ", "")
        assert "fieldType" in bundle

    def test_form_component_has_form_attributes(self) -> None:
        """Verify Form component adds form semantic attributes."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Form should set form and formMode attributes
        assert "formMode" in bundle

    def test_datatable_component_has_table_attributes(self) -> None:
        """Verify DataTable component adds table/row/cell semantic attributes."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # DataTable should set table, row, cell, column attributes
        assert "table:" in bundle or "'table'" in bundle
        assert "row:" in bundle or "'row'" in bundle
        assert "cell:" in bundle or "'cell'" in bundle
        assert "column:" in bundle or "'column'" in bundle

    def test_loading_component_has_loading_attribute(self) -> None:
        """Verify Loading component adds loading semantic attribute."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Loading should set loading attribute
        assert "loading:" in bundle or "'loading'" in bundle

    def test_error_component_has_message_attributes(self) -> None:
        """Verify Error component adds message semantic attributes."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Error should set message and messageKind attributes
        assert "message:" in bundle or "'message'" in bundle
        assert "messageKind" in bundle

    def test_modal_component_has_dialog_attributes(self) -> None:
        """Verify Modal component adds dialog semantic attributes."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # Modal should set dialog and dialogOpen attributes
        assert "dialog:" in bundle or "'dialog'" in bundle
        assert "dialogOpen" in bundle or "dialog-open" in bundle


class TestSurfaceConverterSemanticAttrs:
    """Test that surface converter includes semantic attributes."""

    def test_list_surface_generates_dazzle_attrs(self) -> None:
        """Verify list surface includes dazzle attrs in view."""
        from dazzle.core.ir import (
            EntitySpec,
            FieldSpec,
            FieldType,
            FieldTypeKind,
            SurfaceMode,
            SurfaceSpec,
        )
        from dazzle_dnr_ui.converters.surface_converter import convert_surface_to_component

        entity = EntitySpec(
            name="Task",
            title="Task",
            fields=[
                FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
                FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR)),
            ],
        )

        surface = SurfaceSpec(
            name="task_list",
            title="Task List",
            mode=SurfaceMode.LIST,
            entity="Task",
            sections=[],
        )

        component = convert_surface_to_component(surface, entity)

        # Check that view has dazzle attrs
        assert component.view is not None
        assert "dazzle" in component.view.props

        dazzle_binding = component.view.props["dazzle"]
        assert dazzle_binding.value["view"] == "task_list"
        assert dazzle_binding.value["entity"] == "Task"

    def test_create_surface_generates_form_mode(self) -> None:
        """Verify create surface includes formMode in dazzle attrs."""
        from dazzle.core.ir import (
            EntitySpec,
            FieldSpec,
            FieldType,
            FieldTypeKind,
            SurfaceMode,
            SurfaceSpec,
        )
        from dazzle_dnr_ui.converters.surface_converter import convert_surface_to_component

        entity = EntitySpec(
            name="Task",
            title="Task",
            fields=[
                FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
                FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR)),
            ],
        )

        surface = SurfaceSpec(
            name="task_create",
            title="Create Task",
            mode=SurfaceMode.CREATE,
            entity="Task",
            sections=[],
        )

        component = convert_surface_to_component(surface, entity)

        # Check that view has formMode
        assert component.view is not None
        dazzle_binding = component.view.props["dazzle"]
        assert dazzle_binding.value["formMode"] == "create"
        assert dazzle_binding.value["view"] == "task_create"


class TestAttributeNamingConventions:
    """Test that attribute naming follows the specification."""

    def test_attribute_prefix_is_data_dazzle(self) -> None:
        """Verify all semantic attributes use data-dazzle- prefix."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # All semantic attributes should go through the helper which adds the prefix
        assert "data-dazzle-" in bundle

        # Should not have data-appspec (old naming convention)
        assert "data-appspec" not in bundle

    def test_camelcase_to_kebabcase_mapping(self) -> None:
        """Verify camelCase props are converted to kebab-case attributes."""
        from dazzle_dnr_ui.runtime.js_loader import generate_iife_bundle

        bundle = generate_iife_bundle()

        # The attrMap should map camelCase to kebab-case
        assert "entityId: 'entity-id'" in bundle or "entity-id" in bundle
        assert "actionRole: 'action-role'" in bundle or "action-role" in bundle
        assert "fieldType: 'field-type'" in bundle or "field-type" in bundle
        assert "formMode: 'form-mode'" in bundle or "form-mode" in bundle


# Mark all tests in this module as e2e
pytestmark = pytest.mark.e2e
