"""
End-to-end integration tests for Dazzle Runtime pipeline.

Tests the conversion and runtime generation flow:
1. AppSpec → BackendSpec (conversion)
2. AppSpec → UISpec (conversion)
3. BackendSpec → FastAPI app (runtime)
4. UISpec → Vite project (runtime)

Note: Uses hand-built AppSpecs for testing instead of parsing DSL to keep tests
isolated from the DSL parser changes.
"""

import pytest

from dazzle.core import ir

# Runtime Backend
from dazzle_back.converters import convert_appspec_to_backend
from dazzle_back.runtime import FASTAPI_AVAILABLE, create_app
from dazzle_back.specs import BackendSpec
from dazzle_ui.converters import convert_appspec_to_ui
from dazzle_ui.converters.template_compiler import compile_appspec_to_templates
from dazzle_ui.runtime.template_renderer import render_page
from dazzle_ui.specs import UISpec

# =============================================================================
# Test Fixtures - Hand-built AppSpecs
# =============================================================================


def make_simple_appspec() -> ir.AppSpec:
    """Create a simple AppSpec for testing."""
    task_entity = ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
            ir.FieldSpec(
                name="description",
                type=ir.FieldType(kind=ir.FieldTypeKind.TEXT),
                modifiers=[ir.FieldModifier.OPTIONAL],
            ),
            ir.FieldSpec(
                name="status",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                default="pending",
            ),
            ir.FieldSpec(
                name="created_at",
                type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                modifiers=[ir.FieldModifier.AUTO_ADD],
            ),
        ],
    )

    domain = ir.DomainSpec(entities=[task_entity])

    task_list_surface = ir.SurfaceSpec(
        name="task_list",
        title="Task List",
        entity_ref="Task",
        mode=ir.SurfaceMode.LIST,
        sections=[
            ir.SurfaceSection(
                name="main",
                title="Tasks",
                elements=[
                    ir.SurfaceElement(field_name="title", label="Title"),
                    ir.SurfaceElement(field_name="status", label="Status"),
                ],
            )
        ],
    )

    task_detail_surface = ir.SurfaceSpec(
        name="task_detail",
        title="Task Detail",
        entity_ref="Task",
        mode=ir.SurfaceMode.VIEW,
        sections=[
            ir.SurfaceSection(
                name="main",
                title="Task Details",
                elements=[
                    ir.SurfaceElement(field_name="title", label="Title"),
                    ir.SurfaceElement(field_name="description", label="Description"),
                    ir.SurfaceElement(field_name="status", label="Status"),
                ],
            )
        ],
    )

    task_create_surface = ir.SurfaceSpec(
        name="task_create",
        title="Create Task",
        entity_ref="Task",
        mode=ir.SurfaceMode.CREATE,
        sections=[
            ir.SurfaceSection(
                name="main",
                title="New Task",
                elements=[
                    ir.SurfaceElement(field_name="title", label="Title"),
                    ir.SurfaceElement(field_name="description", label="Description"),
                ],
            )
        ],
    )

    dashboard_workspace = ir.WorkspaceSpec(
        name="dashboard",
        title="Task Dashboard",
        purpose="Overview of all tasks",
        regions=[
            ir.WorkspaceRegion(
                name="main",
                source="Task",
            )
        ],
    )

    return ir.AppSpec(
        name="simple_task",
        title="Simple Task Manager",
        version="1.0.0",
        domain=domain,
        surfaces=[task_list_surface, task_detail_surface, task_create_surface],
        workspaces=[dashboard_workspace],
    )


def make_multi_entity_appspec() -> ir.AppSpec:
    """Create a multi-entity AppSpec for testing."""
    user_entity = ir.EntitySpec(
        name="User",
        title="User",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="email",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=255),
                modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.UNIQUE],
            ),
            ir.FieldSpec(
                name="name",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
        ],
    )

    ticket_entity = ir.EntitySpec(
        name="Ticket",
        title="Support Ticket",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
            ir.FieldSpec(
                name="status",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                default="open",
            ),
            # Assignee relation represented as ref field
            ir.FieldSpec(
                name="assignee",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User"),
                modifiers=[ir.FieldModifier.OPTIONAL],
            ),
        ],
    )

    comment_entity = ir.EntitySpec(
        name="Comment",
        title="Comment",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="content",
                type=ir.FieldType(kind=ir.FieldTypeKind.TEXT),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
            # Relations as ref fields
            ir.FieldSpec(
                name="ticket",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Ticket"),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
            ir.FieldSpec(
                name="author",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User"),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
        ],
    )

    domain = ir.DomainSpec(entities=[user_entity, ticket_entity, comment_entity])

    ticket_list_surface = ir.SurfaceSpec(
        name="ticket_list",
        title="Ticket List",
        entity_ref="Ticket",
        mode=ir.SurfaceMode.LIST,
        sections=[
            ir.SurfaceSection(
                name="main",
                title="Tickets",
                elements=[
                    ir.SurfaceElement(field_name="title", label="Title"),
                    ir.SurfaceElement(field_name="status", label="Status"),
                ],
            )
        ],
    )

    return ir.AppSpec(
        name="support_tickets",
        title="Support Ticket System",
        version="1.0.0",
        domain=domain,
        surfaces=[ticket_list_surface],
        workspaces=[],
    )


@pytest.fixture
def simple_appspec() -> ir.AppSpec:
    """Simple AppSpec fixture."""
    return make_simple_appspec()


@pytest.fixture
def multi_entity_appspec() -> ir.AppSpec:
    """Multi-entity AppSpec fixture."""
    return make_multi_entity_appspec()


# =============================================================================
# AppSpec → BackendSpec Conversion Tests
# =============================================================================


class TestBackendConversion:
    """Test AppSpec to BackendSpec conversion."""

    def test_convert_simple_task(self, simple_appspec: ir.AppSpec) -> None:
        """Test converting simple task to BackendSpec."""
        backend = convert_appspec_to_backend(simple_appspec)

        assert isinstance(backend, BackendSpec)
        assert backend.name == "simple_task"
        assert len(backend.entities) == 1
        assert "Task" in {e.name for e in backend.entities}

    def test_convert_multi_entity(self, multi_entity_appspec: ir.AppSpec) -> None:
        """Test converting multi-entity to BackendSpec."""
        backend = convert_appspec_to_backend(multi_entity_appspec)

        assert len(backend.entities) == 3
        entity_names = {e.name for e in backend.entities}
        assert "User" in entity_names
        assert "Ticket" in entity_names
        assert "Comment" in entity_names

    def test_entity_spec_fields(self, simple_appspec: ir.AppSpec) -> None:
        """Test EntitySpec field conversion."""
        backend = convert_appspec_to_backend(simple_appspec)
        task = next(e for e in backend.entities if e.name == "Task")

        field_names = {f.name for f in task.fields}
        assert "id" in field_names
        assert "title" in field_names
        assert "status" in field_names

    def test_services_generated(self, simple_appspec: ir.AppSpec) -> None:
        """Test service generation from surfaces."""
        backend = convert_appspec_to_backend(simple_appspec)
        assert len(backend.services) > 0

    def test_endpoints_generated(self, simple_appspec: ir.AppSpec) -> None:
        """Test endpoint generation from surfaces."""
        backend = convert_appspec_to_backend(simple_appspec)
        assert len(backend.endpoints) > 0


# =============================================================================
# AppSpec → UISpec Conversion Tests
# =============================================================================


class TestUIConversion:
    """Test AppSpec to UISpec conversion."""

    def test_convert_simple_task(self, simple_appspec: ir.AppSpec) -> None:
        """Test converting simple task to UISpec."""
        ui = convert_appspec_to_ui(simple_appspec)

        assert isinstance(ui, UISpec)
        assert "simple_task" in ui.name
        assert len(ui.workspaces) >= 1

    def test_convert_multi_entity(self, multi_entity_appspec: ir.AppSpec) -> None:
        """Test converting multi-entity to UISpec."""
        ui = convert_appspec_to_ui(multi_entity_appspec)
        assert len(ui.components) > 0

    def test_workspace_conversion(self, simple_appspec: ir.AppSpec) -> None:
        """Test workspace conversion."""
        ui = convert_appspec_to_ui(simple_appspec)
        workspace_names = {w.name for w in ui.workspaces}
        assert "dashboard" in workspace_names

    def test_component_generation(self, simple_appspec: ir.AppSpec) -> None:
        """Test component generation from surfaces."""
        ui = convert_appspec_to_ui(simple_appspec)
        assert len(ui.components) > 0

    def test_theme_generation(self, simple_appspec: ir.AppSpec) -> None:
        """Test default theme generation."""
        ui = convert_appspec_to_ui(simple_appspec)

        assert len(ui.themes) >= 1
        assert ui.default_theme == "default"

        default_theme = next(t for t in ui.themes if t.name == "default")
        assert "primary" in default_theme.tokens.colors


# =============================================================================
# BackendSpec → FastAPI Runtime Tests
# =============================================================================


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestFastAPIRuntime:
    """Test BackendSpec to FastAPI runtime generation."""

    def test_create_app(self, simple_appspec: ir.AppSpec) -> None:
        """Test creating FastAPI app from BackendSpec."""
        backend = convert_appspec_to_backend(simple_appspec)
        app = create_app(backend)

        from fastapi import FastAPI

        assert isinstance(app, FastAPI)
        assert app.title == "simple_task"

    def test_app_routes(self, simple_appspec: ir.AppSpec) -> None:
        """Test that routes are registered."""
        backend = convert_appspec_to_backend(simple_appspec)
        app = create_app(backend)

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert len(routes) > 0


# =============================================================================
# UISpec → JavaScript/Vite Runtime Tests
# =============================================================================


class TestTemplateRuntime:
    """Test AppSpec to server-rendered template generation."""

    def test_compile_templates(self, simple_appspec: ir.AppSpec) -> None:
        """Test compiling AppSpec to template contexts."""
        contexts = compile_appspec_to_templates(simple_appspec)

        assert len(contexts) > 0
        # Should have routes for list, detail, create surfaces
        route_paths = list(contexts.keys())
        assert any("/task" in r for r in route_paths)

    def test_render_all_pages(self, simple_appspec: ir.AppSpec) -> None:
        """Test rendering all compiled templates to HTML."""
        contexts = compile_appspec_to_templates(simple_appspec)

        for route, ctx in contexts.items():
            html = render_page(ctx)
            assert len(html) > 0, f"Route {route} produced empty HTML"
            assert "<!DOCTYPE html>" in html or "<html" in html or "<div" in html


# =============================================================================
# Full Pipeline Integration Tests
# =============================================================================


class TestFullPipeline:
    """Test complete AppSpec → Generated Code pipeline."""

    def test_simple_task_full_pipeline(self) -> None:
        """Test full pipeline with simple task AppSpec."""
        appspec = make_simple_appspec()

        # Convert to BackendSpec
        backend = convert_appspec_to_backend(appspec)
        assert backend.name == "simple_task"
        assert len(backend.entities) == 1

        # Convert to UISpec (still used by eject system)
        ui = convert_appspec_to_ui(appspec)
        assert "simple_task" in ui.name
        assert len(ui.workspaces) >= 1

        # Compile to templates (the new primary path)
        contexts = compile_appspec_to_templates(appspec)
        assert len(contexts) > 0
        for route, ctx in contexts.items():
            html = render_page(ctx)
            assert len(html) > 100, f"Route {route} HTML too short"

    def test_multi_entity_full_pipeline(self) -> None:
        """Test full pipeline with multi-entity AppSpec."""
        appspec = make_multi_entity_appspec()

        # Convert to BackendSpec
        backend = convert_appspec_to_backend(appspec)
        assert len(backend.entities) == 3

        # Compile to templates
        contexts = compile_appspec_to_templates(appspec)
        assert len(contexts) > 0
        for _route, ctx in contexts.items():
            html = render_page(ctx)
            assert len(html) > 0

    def test_roundtrip_spec_serialization(self, simple_appspec: ir.AppSpec) -> None:
        """Test that specs can be serialized and deserialized."""
        # Backend roundtrip
        backend = convert_appspec_to_backend(simple_appspec)
        backend_json = backend.model_dump_json()
        backend_restored = BackendSpec.model_validate_json(backend_json)
        assert backend_restored.name == backend.name
        assert len(backend_restored.entities) == len(backend.entities)

        # UI roundtrip
        ui = convert_appspec_to_ui(simple_appspec)
        ui_json = ui.model_dump_json()
        ui_restored = UISpec.model_validate_json(ui_json)
        assert ui_restored.name == ui.name
        assert len(ui_restored.workspaces) == len(ui.workspaces)
