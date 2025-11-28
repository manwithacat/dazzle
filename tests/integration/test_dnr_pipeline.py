"""
End-to-end integration tests for DNR (Dazzle Native Runtime) pipeline.

Tests the conversion and runtime generation flow:
1. AppSpec → BackendSpec (conversion)
2. AppSpec → UISpec (conversion)
3. BackendSpec → FastAPI app (runtime)
4. UISpec → Vite project (runtime)

Note: Uses hand-built AppSpecs for testing instead of parsing DSL to keep tests
isolated from the DSL parser changes.
"""

import json
import tempfile
from pathlib import Path

import pytest

from dazzle.core import ir

# DNR Backend
from dazzle_dnr_back.converters import convert_appspec_to_backend
from dazzle_dnr_back.runtime import FASTAPI_AVAILABLE, create_app
from dazzle_dnr_back.specs import BackendSpec
from dazzle_dnr_ui.converters import convert_appspec_to_ui
from dazzle_dnr_ui.runtime import (
    generate_js_app,
    generate_single_html,
    generate_vite_app,
)
from dazzle_dnr_ui.specs import UISpec

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


class TestJSRuntime:
    """Test UISpec to JavaScript runtime generation."""

    def test_generate_single_html(self, simple_appspec: ir.AppSpec) -> None:
        """Test generating single HTML file."""
        ui = convert_appspec_to_ui(simple_appspec)
        html = generate_single_html(ui)

        assert "<!DOCTYPE html>" in html
        assert "DNR" in html
        assert "createApp" in html

    def test_generate_js_app(self, simple_appspec: ir.AppSpec) -> None:
        """Test generating split JS app."""
        ui = convert_appspec_to_ui(simple_appspec)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = generate_js_app(ui, tmpdir)

            assert len(files) == 4
            file_names = {f.name for f in files}
            assert "index.html" in file_names
            assert "dnr-runtime.js" in file_names
            assert "app.js" in file_names
            assert "ui-spec.json" in file_names

    def test_generated_spec_json(self, simple_appspec: ir.AppSpec) -> None:
        """Test that generated spec JSON is valid."""
        ui = convert_appspec_to_ui(simple_appspec)

        with tempfile.TemporaryDirectory() as tmpdir:
            generate_js_app(ui, tmpdir)
            spec_path = Path(tmpdir) / "ui-spec.json"

            spec_data = json.loads(spec_path.read_text())
            assert "name" in spec_data
            assert "workspaces" in spec_data
            assert "components" in spec_data


class TestViteRuntime:
    """Test UISpec to Vite project generation."""

    def test_generate_vite_project(self, simple_appspec: ir.AppSpec) -> None:
        """Test generating complete Vite project."""
        ui = convert_appspec_to_ui(simple_appspec)

        with tempfile.TemporaryDirectory() as tmpdir:
            generate_vite_app(ui, tmpdir)
            tmpdir = Path(tmpdir)

            assert (tmpdir / "package.json").exists()
            assert (tmpdir / "vite.config.js").exists()
            assert (tmpdir / "src" / "index.html").exists()
            assert (tmpdir / "src" / "main.js").exists()
            assert (tmpdir / "src" / "dnr" / "signals.js").exists()

    def test_vite_package_json(self, simple_appspec: ir.AppSpec) -> None:
        """Test generated package.json is valid."""
        ui = convert_appspec_to_ui(simple_appspec)

        with tempfile.TemporaryDirectory() as tmpdir:
            generate_vite_app(ui, tmpdir)
            package_path = Path(tmpdir) / "package.json"

            package_data = json.loads(package_path.read_text())
            assert package_data["type"] == "module"
            assert "vite" in package_data["devDependencies"]
            assert "dev" in package_data["scripts"]

    def test_vite_es_modules(self, simple_appspec: ir.AppSpec) -> None:
        """Test ES modules are properly structured."""
        ui = convert_appspec_to_ui(simple_appspec)

        with tempfile.TemporaryDirectory() as tmpdir:
            generate_vite_app(ui, tmpdir)
            dnr_dir = Path(tmpdir) / "src" / "dnr"

            signals = (dnr_dir / "signals.js").read_text()
            assert "export function createSignal" in signals

            state = (dnr_dir / "state.js").read_text()
            assert "import { createSignal }" in state


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

        # Convert to UISpec
        ui = convert_appspec_to_ui(appspec)
        assert "simple_task" in ui.name
        assert len(ui.workspaces) >= 1

        # Generate Vite project
        with tempfile.TemporaryDirectory() as tmpdir:
            files = generate_vite_app(ui, tmpdir)
            assert len(files) > 10

            spec_path = Path(tmpdir) / "src" / "ui-spec.json"
            spec_data = json.loads(spec_path.read_text())
            assert len(spec_data["workspaces"]) >= 1

    def test_multi_entity_full_pipeline(self) -> None:
        """Test full pipeline with multi-entity AppSpec."""
        appspec = make_multi_entity_appspec()

        # Convert to BackendSpec
        backend = convert_appspec_to_backend(appspec)
        assert len(backend.entities) == 3

        # Convert to UISpec
        ui = convert_appspec_to_ui(appspec)

        # Generate HTML
        html = generate_single_html(ui)
        assert "DNR" in html

        # Generate Vite project
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_vite_app(ui, tmpdir)
            assert (Path(tmpdir) / "src" / "dnr" / "app.js").exists()
            assert (Path(tmpdir) / "src" / "ui-spec.json").exists()

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
