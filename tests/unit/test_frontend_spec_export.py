"""Tests for frontend specification export."""

from __future__ import annotations

import json

import pytest

from dazzle.core.frontend_spec_export import (
    ALL_SECTIONS,
    FIELD_TYPE_MAP,
    _build_api_contract,
    _build_component_inventory,
    _build_route_map,
    _build_state_machines,
    _build_test_criteria,
    _build_typescript_interfaces,
    _build_workspace_layouts,
    export_frontend_spec,
)
from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.state_machine import (
    StateMachineSpec,
    StateTransition,
    TransitionGuard,
)
from dazzle.core.ir.stories import StoryCondition, StorySpec, StoryStatus, StoryTrigger
from dazzle.core.ir.surfaces import (
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
)
from dazzle.core.ir.test_design import (
    TestDesignAction,
    TestDesignSpec,
    TestDesignStep,
)
from dazzle.core.ir.workspaces import (
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
    WorkspaceRegion,
    WorkspaceSpec,
)
from dazzle.core.strings import to_api_plural


@pytest.fixture()
def simple_entity() -> EntitySpec:
    return EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind=FieldTypeKind.BOOL),
            ),
            FieldSpec(
                name="priority",
                type=FieldType(
                    kind=FieldTypeKind.ENUM,
                    enum_values=["low", "medium", "high"],
                ),
            ),
        ],
    )


@pytest.fixture()
def entity_with_state_machine() -> EntitySpec:
    return EntitySpec(
        name="Ticket",
        title="Support Ticket",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="status",
                type=FieldType(
                    kind=FieldTypeKind.ENUM,
                    enum_values=["open", "assigned", "resolved"],
                ),
                modifiers=[FieldModifier.REQUIRED],
            ),
        ],
        state_machine=StateMachineSpec(
            status_field="status",
            states=["open", "assigned", "resolved"],
            transitions=[
                StateTransition(
                    from_state="open",
                    to_state="assigned",
                    guards=[TransitionGuard(requires_field="assignee")],
                ),
                StateTransition(
                    from_state="assigned",
                    to_state="resolved",
                    guards=[TransitionGuard(requires_role="admin")],
                ),
            ],
        ),
    )


@pytest.fixture()
def simple_appspec(simple_entity: EntitySpec) -> AppSpec:
    from dazzle.core.ir.appspec import AppSpec

    return AppSpec(
        name="test_app",
        title="Test App",
        domain=DomainSpec(entities=[simple_entity]),
        surfaces=[
            SurfaceSpec(
                name="task_list",
                title="Tasks",
                entity_ref="Task",
                mode=SurfaceMode.LIST,
                sections=[
                    SurfaceSection(
                        name="main",
                        elements=[
                            SurfaceElement(field_name="title", label="Title"),
                            SurfaceElement(field_name="completed", label="Done"),
                        ],
                    )
                ],
            ),
            SurfaceSpec(
                name="task_create",
                title="New Task",
                entity_ref="Task",
                mode=SurfaceMode.CREATE,
            ),
        ],
        workspaces=[
            WorkspaceSpec(
                name="dashboard",
                title="Dashboard",
                purpose="Main dashboard",
                access=WorkspaceAccessSpec(
                    level=WorkspaceAccessLevel.AUTHENTICATED,
                ),
                regions=[
                    WorkspaceRegion(name="tasks", source="Task"),
                ],
            ),
        ],
    )


class TestFieldTypeMap:
    def test_all_field_types_mapped(self) -> None:
        """All non-ENUM field types should have a TS mapping."""
        for kind in FieldTypeKind:
            if kind != FieldTypeKind.ENUM:
                assert kind in FIELD_TYPE_MAP, f"{kind} missing from FIELD_TYPE_MAP"

    def test_uuid_maps_to_string(self) -> None:
        assert FIELD_TYPE_MAP[FieldTypeKind.UUID] == "string"

    def test_int_maps_to_number(self) -> None:
        assert FIELD_TYPE_MAP[FieldTypeKind.INT] == "number"

    def test_bool_maps_to_boolean(self) -> None:
        assert FIELD_TYPE_MAP[FieldTypeKind.BOOL] == "boolean"


class TestPluralize:
    def test_simple(self) -> None:
        assert to_api_plural("task") == "tasks"

    def test_ending_s(self) -> None:
        assert to_api_plural("status") == "statuses"

    def test_ending_y(self) -> None:
        assert to_api_plural("category") == "categories"

    def test_ending_ay(self) -> None:
        assert to_api_plural("day") == "days"


class TestTypescriptInterfaces:
    def test_basic_entity(self, simple_appspec: AppSpec) -> None:
        result = _build_typescript_interfaces(simple_appspec, None)
        assert len(result) == 1
        assert result[0]["name"] == "Task"
        field_names = [f["name"] for f in result[0]["fields"]]
        assert "id" in field_names
        assert "title" in field_names

    def test_pk_field_not_optional(self, simple_appspec: AppSpec) -> None:
        result = _build_typescript_interfaces(simple_appspec, None)
        id_field = next(f for f in result[0]["fields"] if f["name"] == "id")
        assert id_field["optional"] is False
        assert "pk" in id_field["comments"]

    def test_required_field(self, simple_appspec: AppSpec) -> None:
        result = _build_typescript_interfaces(simple_appspec, None)
        title_field = next(f for f in result[0]["fields"] if f["name"] == "title")
        assert title_field["optional"] is False
        assert "required" in title_field["comments"]

    def test_optional_field(self, simple_appspec: AppSpec) -> None:
        result = _build_typescript_interfaces(simple_appspec, None)
        completed_field = next(f for f in result[0]["fields"] if f["name"] == "completed")
        assert completed_field["optional"] is True

    def test_enum_union_type(self, simple_appspec: AppSpec) -> None:
        result = _build_typescript_interfaces(simple_appspec, None)
        priority_field = next(f for f in result[0]["fields"] if f["name"] == "priority")
        assert '"low"' in priority_field["ts_type"]
        assert '"high"' in priority_field["ts_type"]

    def test_entity_filter(self, simple_appspec: AppSpec) -> None:
        result = _build_typescript_interfaces(simple_appspec, ["NonExistent"])
        assert len(result) == 0

    def test_state_machine_union(self, entity_with_state_machine: EntitySpec) -> None:
        appspec = AppSpec(
            name="test",
            domain=DomainSpec(entities=[entity_with_state_machine]),
        )
        result = _build_typescript_interfaces(appspec, None)
        assert result[0]["status_union"]["states"] == ["open", "assigned", "resolved"]


class TestRouteMap:
    def test_list_surface_route(self, simple_appspec: AppSpec) -> None:
        routes = _build_route_map(simple_appspec, None)
        list_route = next(r for r in routes if r["surface"] == "task_list")
        assert list_route["mode"] == "list"
        assert "tasks" in list_route["path"]

    def test_create_surface_route(self, simple_appspec: AppSpec) -> None:
        routes = _build_route_map(simple_appspec, None)
        create_route = next(r for r in routes if r["surface"] == "task_create")
        assert create_route["path"].endswith("/new")


class TestComponentInventory:
    def test_surface_included(self, simple_appspec: AppSpec) -> None:
        result = _build_component_inventory(simple_appspec, None)
        assert len(result) == 2
        task_list = next(c for c in result if c["name"] == "task_list")
        assert task_list["mode"] == "list"
        assert task_list["entity"] == "Task"

    def test_sections_and_fields(self, simple_appspec: AppSpec) -> None:
        result = _build_component_inventory(simple_appspec, None)
        task_list = next(c for c in result if c["name"] == "task_list")
        assert len(task_list["sections"]) == 1
        assert len(task_list["sections"][0]["fields"]) == 2

    def test_entity_filter(self, simple_appspec: AppSpec) -> None:
        result = _build_component_inventory(simple_appspec, ["NonExistent"])
        assert len(result) == 0


class TestStateMachines:
    def test_mermaid_output(self, entity_with_state_machine: EntitySpec) -> None:
        appspec = AppSpec(
            name="test",
            domain=DomainSpec(entities=[entity_with_state_machine]),
        )
        result = _build_state_machines(appspec, None)
        assert len(result) == 1
        assert result[0]["entity"] == "Ticket"
        assert "stateDiagram-v2" in result[0]["mermaid"]
        assert "requires assignee" in result[0]["mermaid"]
        assert "role(admin)" in result[0]["mermaid"]

    def test_no_state_machine_skipped(self, simple_appspec: AppSpec) -> None:
        result = _build_state_machines(simple_appspec, None)
        assert len(result) == 0


class TestApiContract:
    def test_crud_endpoints(self, simple_appspec: AppSpec) -> None:
        result = _build_api_contract(simple_appspec, None)
        assert len(result) == 1
        endpoints = result[0]["endpoints"]
        methods = [e["method"] for e in endpoints]
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods
        assert "DELETE" in methods

    def test_state_transition_endpoint(self, entity_with_state_machine: EntitySpec) -> None:
        appspec = AppSpec(
            name="test",
            domain=DomainSpec(entities=[entity_with_state_machine]),
        )
        result = _build_api_contract(appspec, None)
        endpoints = result[0]["endpoints"]
        transition_ep = next((e for e in endpoints if "transitions" in e["path"]), None)
        assert transition_ep is not None
        assert transition_ep["method"] == "POST"


class TestWorkspaceLayouts:
    def test_workspace_included(self, simple_appspec: AppSpec) -> None:
        result = _build_workspace_layouts(simple_appspec, None)
        assert len(result) == 1
        assert result[0]["name"] == "dashboard"
        assert result[0]["access"]["level"] == "authenticated"


class TestTestCriteria:
    def test_story_criteria(self) -> None:
        stories = [
            StorySpec(
                story_id="ST-001",
                title="Create task",
                actor="Admin",
                trigger=StoryTrigger.FORM_SUBMITTED,
                scope=["Task"],
                given=[StoryCondition(expression="Task list is empty")],
                when=[StoryCondition(expression="Admin creates a task")],
                then=[StoryCondition(expression="Task appears in list")],
                status=StoryStatus.ACCEPTED,
            )
        ]
        result = _build_test_criteria(stories, [], None)
        assert len(result) == 1
        assert result[0]["source"] == "story"
        assert result[0]["given"] == ["Task list is empty"]

    def test_test_design_criteria(self) -> None:
        designs = [
            TestDesignSpec(
                test_id="TD-001",
                title="Admin creates task",
                persona="Admin",
                entities=["Task"],
                steps=[TestDesignStep(action=TestDesignAction.CLICK, target="task_create")],
                expected_outcomes=["Task is created"],
            )
        ]
        result = _build_test_criteria([], designs, None)
        assert len(result) == 1
        assert result[0]["source"] == "test_design"

    def test_entity_filter(self) -> None:
        stories = [
            StorySpec(
                story_id="ST-001",
                title="Create task",
                actor="Admin",
                trigger=StoryTrigger.FORM_SUBMITTED,
                scope=["Task"],
                status=StoryStatus.ACCEPTED,
            )
        ]
        result = _build_test_criteria(stories, [], ["NonExistent"])
        assert len(result) == 0


class TestExportFormats:
    def test_markdown_output(self, simple_appspec: AppSpec) -> None:
        result = export_frontend_spec(simple_appspec, None, [], [], "markdown")
        assert "# Frontend Specification" in result
        assert "## TypeScript Interfaces" in result
        assert "## Route Map" in result
        assert "interface Task" in result

    def test_json_output(self, simple_appspec: AppSpec) -> None:
        result = export_frontend_spec(simple_appspec, None, [], [], "json")
        data = json.loads(result)
        assert "typescript_interfaces" in data
        assert "route_map" in data
        assert len(data) == len(ALL_SECTIONS)

    def test_section_filter(self, simple_appspec: AppSpec) -> None:
        result = export_frontend_spec(
            simple_appspec, None, [], [], "json", sections=["typescript_interfaces"]
        )
        data = json.loads(result)
        assert "typescript_interfaces" in data
        assert "route_map" not in data

    def test_entity_filter(self, simple_appspec: AppSpec) -> None:
        result = export_frontend_spec(
            simple_appspec, None, [], [], "json", entities_filter=["Task"]
        )
        data = json.loads(result)
        assert len(data["typescript_interfaces"]) == 1
