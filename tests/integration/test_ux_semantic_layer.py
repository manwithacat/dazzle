"""
Integration tests for UX Semantic Layer feature.

Tests the full pipeline from DSL parsing through Django code generation
with UX specifications including:
- Information Needs (purpose, show, sort, filter, search, empty)
- Attention Signals (critical, warning, notice, info)
- Persona Variants
- Workspaces with regions
"""

import tempfile
from pathlib import Path

import pytest

from dazzle.core.dsl_parser import parse_dsl
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.stacks.django_micro_modular import DjangoMicroModularBackend

# Sample DSL with UX Semantic Layer features
UX_DSL = """
module urban_canopy.core

app urban_canopy "Urban Canopy Maintenance Tracker"

entity MaintenanceTask "Maintenance Task":
    id: uuid pk
    tree_id: str(50) required
    location: str(200) required
    task_type: enum[pruning,watering,pest_control,removal,planting]=pruning
    priority: enum[low,medium,high,urgent]=medium
    status: enum[pending,assigned,in_progress,completed,cancelled]=pending
    assigned_to: str(100) optional
    notes: text optional
    scheduled_date: datetime optional
    created_at: datetime auto_add
    updated_at: datetime auto_update

surface task_list "Task Queue":
    uses entity MaintenanceTask
    mode: list

    section main "Tasks":
        field tree_id "Tree ID"
        field location "Location"
        field task_type "Type"
        field priority "Priority"
        field status "Status"
        field scheduled_date "Scheduled"

    ux:
        purpose: "View and prioritize pending maintenance tasks"
        show: tree_id, location, task_type, priority, status, scheduled_date
        sort: priority desc, scheduled_date asc
        filter: status, priority, task_type
        search: tree_id, location
        empty: "No maintenance tasks scheduled. Great job keeping the urban canopy healthy!"

        attention critical:
            when: priority = "urgent" and status = "pending"
            message: "Urgent task requires immediate attention!"
            action: task_edit

        attention warning:
            when: priority = "high" and status = "pending"
            message: "High priority task pending"

        attention notice:
            when: status = "assigned"
            message: "Task has been assigned"

        for volunteer:
            scope: assigned_to = current_user
            purpose: "View your assigned tasks"
            show: tree_id, location, task_type, scheduled_date
            hide: notes
            action_primary: task_edit
            read_only: false

        for coordinator:
            scope: all
            purpose: "Manage all tasks and assignments"
            show_aggregate: critical_count, pending_count
            action_primary: task_assign

surface task_detail "Task Details":
    uses entity MaintenanceTask
    mode: view

    section main "Details":
        field tree_id "Tree ID"
        field location "Location"
        field task_type "Task Type"
        field priority "Priority"
        field status "Status"
        field assigned_to "Assigned To"
        field notes "Notes"
        field scheduled_date "Scheduled Date"
        field created_at "Created"
        field updated_at "Last Updated"

surface task_create "Create Task":
    uses entity MaintenanceTask
    mode: create

    section main "New Task":
        field tree_id "Tree ID"
        field location "Location"
        field task_type "Task Type"
        field priority "Priority"
        field notes "Notes"
        field scheduled_date "Scheduled Date"

surface task_edit "Edit Task":
    uses entity MaintenanceTask
    mode: edit

    section main "Edit Task":
        field status "Status"
        field assigned_to "Assigned To"
        field notes "Notes"
        field scheduled_date "Scheduled Date"

workspace coordinator_dashboard "Coordinator Dashboard":
    purpose: "Overview of all maintenance activities"

    urgent_tasks:
        source: MaintenanceTask
        filter: priority = "urgent" and status = "pending"
        sort: created_at asc
        limit: 10
        display: list

    high_priority:
        source: MaintenanceTask
        filter: priority = "high" and status = "pending"
        sort: scheduled_date asc
        limit: 10
        display: list

    in_progress:
        source: MaintenanceTask
        filter: status = "in_progress"
        sort: updated_at desc
        limit: 5
        display: timeline

workspace volunteer_dashboard "My Tasks":
    purpose: "Your assigned maintenance tasks"

    my_tasks:
        source: MaintenanceTask
        filter: status = "assigned"
        sort: scheduled_date asc
        limit: 20
        display: list
"""


class TestUXParsing:
    """Test UX DSL parsing."""

    def test_parse_ux_block(self):
        """Test parsing UX block within surface."""
        module_name, app_name, app_title, uses, fragment = parse_dsl(UX_DSL, Path("test.dsl"))

        assert module_name == "urban_canopy.core"
        assert app_name == "urban_canopy"
        assert len(fragment.surfaces) == 4

        # Find task_list surface
        task_list = next(s for s in fragment.surfaces if s.name == "task_list")
        assert task_list.ux is not None

        ux = task_list.ux
        assert ux.purpose == "View and prioritize pending maintenance tasks"
        assert ux.show == [
            "tree_id",
            "location",
            "task_type",
            "priority",
            "status",
            "scheduled_date",
        ]
        assert len(ux.sort) == 2
        assert ux.sort[0].field == "priority"
        assert ux.sort[0].direction == "desc"
        assert ux.filter == ["status", "priority", "task_type"]
        assert ux.search == ["tree_id", "location"]
        assert "Great job" in ux.empty_message

    def test_parse_attention_signals(self):
        """Test parsing attention signals."""
        _, _, _, _, fragment = parse_dsl(UX_DSL, Path("test.dsl"))

        task_list = next(s for s in fragment.surfaces if s.name == "task_list")
        signals = task_list.ux.attention_signals

        assert len(signals) == 3
        assert signals[0].level.value == "critical"
        assert signals[0].message == "Urgent task requires immediate attention!"
        assert signals[0].action == "task_edit"
        assert signals[1].level.value == "warning"
        assert signals[2].level.value == "notice"

    def test_parse_persona_variants(self):
        """Test parsing persona variants."""
        _, _, _, _, fragment = parse_dsl(UX_DSL, Path("test.dsl"))

        task_list = next(s for s in fragment.surfaces if s.name == "task_list")
        personas = task_list.ux.persona_variants

        assert len(personas) == 2

        volunteer = next(p for p in personas if p.persona == "volunteer")
        assert volunteer.purpose == "View your assigned tasks"
        assert "tree_id" in volunteer.show
        assert "notes" in volunteer.hide
        assert volunteer.action_primary == "task_edit"
        assert volunteer.read_only is False

        coordinator = next(p for p in personas if p.persona == "coordinator")
        assert coordinator.scope_all is True
        assert "critical_count" in coordinator.show_aggregate

    def test_parse_workspace(self):
        """Test parsing workspace declarations."""
        _, _, _, _, fragment = parse_dsl(UX_DSL, Path("test.dsl"))

        assert len(fragment.workspaces) == 2

        coord_ws = next(w for w in fragment.workspaces if w.name == "coordinator_dashboard")
        assert coord_ws.title == "Coordinator Dashboard"
        assert coord_ws.purpose == "Overview of all maintenance activities"
        assert len(coord_ws.regions) == 3

        urgent_region = next(r for r in coord_ws.regions if r.name == "urgent_tasks")
        assert urgent_region.source == "MaintenanceTask"
        assert urgent_region.limit == 10
        assert urgent_region.filter is not None


class TestUXLinking:
    """Test UX linking and validation."""

    def test_link_with_ux(self):
        """Test linking modules with UX specs."""
        module_name, app_name, app_title, uses, fragment = parse_dsl(UX_DSL, Path("test.dsl"))

        # Create ModuleIR from parsed data
        from dazzle.core import ir

        module = ir.ModuleIR(
            name=module_name,
            file=Path("test.dsl"),
            uses=uses,
            app_name=app_name,
            app_title=app_title,
            fragment=fragment,
        )

        appspec = build_appspec([module], module_name)

        assert appspec.name == "urban_canopy"
        assert len(appspec.surfaces) == 4
        assert len(appspec.workspaces) == 2

        # Verify UX preserved after linking
        task_list = next(s for s in appspec.surfaces if s.name == "task_list")
        assert task_list.ux is not None
        assert len(task_list.ux.attention_signals) == 3


class TestUXValidation:
    """Test UX validation rules."""

    def test_lint_valid_ux(self):
        """Test linting valid UX specs."""
        module_name, app_name, app_title, uses, fragment = parse_dsl(UX_DSL, Path("test.dsl"))

        from dazzle.core import ir

        module = ir.ModuleIR(
            name=module_name,
            file=Path("test.dsl"),
            uses=uses,
            app_name=app_name,
            app_title=app_title,
            fragment=fragment,
        )

        appspec = build_appspec([module], module_name)
        errors, warnings = lint_appspec(appspec)

        # Should have no errors for valid UX
        assert len(errors) == 0

    def test_lint_invalid_ux_field(self):
        """Test linting catches invalid UX field references."""
        invalid_dsl = """
module test.core

app test_app "Test"

entity Task "Task":
    id: uuid pk
    title: str(200) required

surface task_list "Tasks":
    uses entity Task
    mode: list

    section main "Tasks":
        field title "Title"

    ux:
        show: title, nonexistent_field
"""
        module_name, app_name, app_title, uses, fragment = parse_dsl(invalid_dsl, Path("test.dsl"))

        from dazzle.core import ir

        module = ir.ModuleIR(
            name=module_name,
            file=Path("test.dsl"),
            uses=uses,
            app_name=app_name,
            app_title=app_title,
            fragment=fragment,
        )

        appspec = build_appspec([module], module_name)
        errors, warnings = lint_appspec(appspec)

        # Should catch the invalid field reference
        assert any("nonexistent_field" in e for e in errors)


class TestDjangoUXGeneration:
    """Test Django code generation with UX features."""

    def test_generate_with_ux(self):
        """Test Django generation includes UX features."""
        module_name, app_name, app_title, uses, fragment = parse_dsl(UX_DSL, Path("test.dsl"))

        from dazzle.core import ir

        module = ir.ModuleIR(
            name=module_name,
            file=Path("test.dsl"),
            uses=uses,
            app_name=app_name,
            app_title=app_title,
            fragment=fragment,
        )

        appspec = build_appspec([module], module_name)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            backend = DjangoMicroModularBackend()
            backend.generate(appspec, output_dir, skip_hooks=True)

            # Check generated files exist
            project_dir = output_dir / "urban_canopy"
            assert (
                project_dir / "app" / "templates" / "app" / "maintenancetask_list.html"
            ).exists()

            # Read list template and verify UX features
            list_template = (
                project_dir / "app" / "templates" / "app" / "maintenancetask_list.html"
            ).read_text()

            # Should have purpose text
            assert "purpose-text" in list_template

            # Should have custom empty message
            assert "Great job" in list_template or "empty" in list_template.lower()

            # Check CSS has attention signal styles
            css_file = project_dir / "app" / "static" / "css" / "style.css"
            css_content = css_file.read_text()
            assert "attention-critical" in css_content
            assert "attention-warning" in css_content

            # Check middleware generated (if personas present)
            middleware_file = project_dir / "app" / "middleware.py"
            if middleware_file.exists():
                middleware_content = middleware_file.read_text()
                assert "PersonaMiddleware" in middleware_content
                assert "volunteer" in middleware_content or "coordinator" in middleware_content

            # Check workspace template exists
            workspace_template = (
                project_dir / "app" / "templates" / "app" / "coordinator_dashboard_dashboard.html"
            )
            assert workspace_template.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
