"""Tests for the discovery mission builder."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.agent.core import Mission
from dazzle.agent.missions.discovery import (
    _auto_prefix,
    _build_dsl_summary,
    _build_persona_context,
    build_discovery_mission,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_field(name: str, type_: str = "str") -> SimpleNamespace:
    return SimpleNamespace(name=name, type=type_, constraints=None)


def _make_entity(
    name: str,
    title: str,
    field_names: list[str] | None = None,
    states: list[str] | None = None,
) -> SimpleNamespace:
    fields = [_make_field(n) for n in (field_names or ["id", "title"])]
    sm = None
    if states:
        sm = SimpleNamespace(
            states=[SimpleNamespace(name=s) for s in states],
            transitions=[],
        )
    return SimpleNamespace(name=name, title=title, fields=fields, state_machine=sm)


def _make_surface(
    name: str,
    title: str,
    mode: str = "list",
    entity: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(name=name, title=title, mode=mode, entity=entity, sections=[])


def _make_appspec(
    entities: list[Any] | None = None,
    surfaces: list[Any] | None = None,
    personas: list[Any] | None = None,
    workspaces: list[Any] | None = None,
    processes: list[Any] | None = None,
    experiences: list[Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name="test_app",
        domain=SimpleNamespace(entities=entities or []),
        surfaces=surfaces or [],
        personas=personas or [],
        workspaces=workspaces or [],
        processes=processes or [],
        experiences=experiences or [],
    )


@pytest.fixture
def sample_appspec() -> SimpleNamespace:
    return _make_appspec(
        entities=[
            _make_entity(
                "Task",
                "Task",
                ["id", "title", "status", "assignee"],
                ["open", "in_progress", "done"],
            ),
            _make_entity("User", "User", ["id", "name", "email"]),
        ],
        surfaces=[
            _make_surface("task_list", "Task List", "list", "Task"),
            _make_surface("task_detail", "Task Detail", "detail", "Task"),
            _make_surface("task_create", "Create Task", "form", "Task"),
            _make_surface("user_list", "User List", "list", "User"),
        ],
        personas=[
            SimpleNamespace(name="admin", description="Administrator with full access"),
            SimpleNamespace(name="viewer", description="Read-only access"),
        ],
        workspaces=[
            SimpleNamespace(
                name="main_dashboard",
                regions=[SimpleNamespace(name="tasks"), SimpleNamespace(name="users")],
            ),
        ],
    )


# =============================================================================
# Tests: DSL Summary Builder
# =============================================================================


class TestDSLSummary:
    def test_includes_entities(self, sample_appspec: SimpleNamespace) -> None:
        summary = _build_dsl_summary(sample_appspec)
        assert "Task" in summary
        assert "User" in summary

    def test_includes_fields(self, sample_appspec: SimpleNamespace) -> None:
        summary = _build_dsl_summary(sample_appspec)
        assert "title" in summary
        assert "status" in summary

    def test_includes_state_machine(self, sample_appspec: SimpleNamespace) -> None:
        summary = _build_dsl_summary(sample_appspec)
        assert "open" in summary
        assert "done" in summary

    def test_includes_surfaces(self, sample_appspec: SimpleNamespace) -> None:
        summary = _build_dsl_summary(sample_appspec)
        assert "task_list" in summary
        assert "task_detail" in summary

    def test_includes_personas(self, sample_appspec: SimpleNamespace) -> None:
        summary = _build_dsl_summary(sample_appspec)
        assert "admin" in summary
        assert "viewer" in summary

    def test_includes_workspaces(self, sample_appspec: SimpleNamespace) -> None:
        summary = _build_dsl_summary(sample_appspec)
        assert "main_dashboard" in summary

    def test_empty_appspec(self) -> None:
        appspec = _make_appspec()
        summary = _build_dsl_summary(appspec)
        assert "### Entities" in summary


# =============================================================================
# Tests: Persona Context
# =============================================================================


class TestPersonaContext:
    def test_basic_context(self) -> None:
        ctx = _build_persona_context("admin", None)
        assert "admin" in ctx
        assert "explore freely" in ctx

    def test_with_capability_map(self) -> None:
        cap_map: dict[str, list[Any]] = {
            "workspaces": [SimpleNamespace(name="dashboard")],
            "surfaces": [SimpleNamespace(name="task_list"), SimpleNamespace(name="user_list")],
            "entities": [SimpleNamespace(name="Task")],
        }
        ctx = _build_persona_context("admin", cap_map)
        assert "dashboard" in ctx
        assert "task_list" in ctx
        assert "Task" in ctx


# =============================================================================
# Tests: Auto-prefix
# =============================================================================


class TestAutoPrefix:
    def test_already_prefixed(self) -> None:
        store = MagicMock()
        result = _auto_prefix(store, "entity:Task", ("entity:", "surface:"))
        assert result == "entity:Task"
        store.get_entity.assert_not_called()

    def test_empty_string(self) -> None:
        store = MagicMock()
        result = _auto_prefix(store, "", ("entity:", "surface:"))
        assert result == ""

    def test_resolves_entity(self) -> None:
        store = MagicMock()
        store.get_entity.side_effect = lambda x: (
            SimpleNamespace(id=x) if x == "entity:Task" else None
        )
        result = _auto_prefix(store, "Task", ("entity:", "surface:"))
        assert result == "entity:Task"

    def test_resolves_surface(self) -> None:
        store = MagicMock()
        store.get_entity.side_effect = lambda x: (
            SimpleNamespace(id=x) if x == "surface:task_list" else None
        )
        result = _auto_prefix(store, "task_list", ("entity:", "surface:"))
        assert result == "surface:task_list"

    def test_no_match_returns_original(self) -> None:
        store = MagicMock()
        store.get_entity.return_value = None
        result = _auto_prefix(store, "unknown_thing", ("entity:", "surface:"))
        assert result == "unknown_thing"


# =============================================================================
# Tests: Mission Builder
# =============================================================================


class TestBuildDiscoveryMission:
    def test_returns_mission(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        assert isinstance(mission, Mission)
        assert mission.name == "discovery:admin"

    def test_default_parameters(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        assert mission.max_steps == 50
        assert mission.token_budget == 200_000
        assert mission.start_url == "http://localhost:3000"

    def test_custom_persona(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec, persona_name="viewer")
        assert mission.name == "discovery:viewer"
        assert mission.context["persona"] == "viewer"

    def test_custom_parameters(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(
            sample_appspec,
            base_url="http://localhost:8080",
            max_steps=100,
            token_budget=500_000,
        )
        assert mission.start_url == "http://localhost:8080"
        assert mission.max_steps == 100
        assert mission.token_budget == 500_000

    def test_has_four_tools(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool_names = {t.name for t in mission.tools}
        assert tool_names == {"observe_gap", "query_dsl", "check_adjacency", "list_surfaces"}

    def test_system_prompt_includes_dsl(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        assert "Task" in mission.system_prompt
        assert "task_list" in mission.system_prompt
        assert "admin" in mission.system_prompt

    def test_context_metadata(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        assert mission.context["mode"] == "discovery"
        assert mission.context["app_name"] == "test_app"

    def test_with_kg_store(self, sample_appspec: SimpleNamespace) -> None:
        store = MagicMock()
        store.persona_capability_map.return_value = {
            "workspaces": [],
            "surfaces": [],
            "entities": [],
        }
        mission = build_discovery_mission(sample_appspec, kg_store=store)
        assert isinstance(mission, Mission)
        store.persona_capability_map.assert_called_once_with("admin")

    def test_kg_store_error_handled(self, sample_appspec: SimpleNamespace) -> None:
        store = MagicMock()
        store.persona_capability_map.side_effect = Exception("DB error")
        # Should not raise
        mission = build_discovery_mission(sample_appspec, kg_store=store)
        assert isinstance(mission, Mission)


# =============================================================================
# Tests: Tool Handlers
# =============================================================================


class TestObserveGapTool:
    def test_basic_observation(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "observe_gap")
        result = tool.handler(
            title="No delete for Task",
            description="Task entity has no delete surface",
            category="missing_crud",
            severity="high",
            location="/tasks",
        )
        assert result["recorded"] is True
        obs = result["observation"]
        assert obs["category"] == "missing_crud"
        assert obs["severity"] == "high"
        assert obs["title"] == "No delete for Task"

    def test_invalid_severity_defaults(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "observe_gap")
        result = tool.handler(title="test", description="test", severity="extreme")
        assert result["observation"]["severity"] == "medium"

    def test_invalid_category_defaults(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "observe_gap")
        result = tool.handler(title="test", description="test", category="invented")
        assert result["observation"]["category"] == "gap"


class TestQueryDSLTool:
    def test_query_entity(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "query_dsl")
        result = tool.handler(entity_name="Task")
        assert result["name"] == "Task"
        assert any(f["name"] == "title" for f in result["fields"])

    def test_query_entity_with_states(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "query_dsl")
        result = tool.handler(entity_name="Task")
        assert "states" in result
        assert "open" in result["states"]

    def test_query_unknown_entity(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "query_dsl")
        result = tool.handler(entity_name="Nonexistent")
        assert "error" in result

    def test_query_surface(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "query_dsl")
        result = tool.handler(surface_name="task_list")
        assert result["name"] == "task_list"
        assert result["mode"] == "list"

    def test_query_no_args(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "query_dsl")
        result = tool.handler()
        assert "error" in result


class TestListSurfacesTool:
    def test_list_all(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "list_surfaces")
        result = tool.handler()
        assert result["total"] == 4

    def test_filter_by_entity(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec)
        tool = next(t for t in mission.tools if t.name == "list_surfaces")
        result = tool.handler(entity_filter="Task")
        assert result["total"] == 3
        assert all(s["entity"] == "Task" for s in result["surfaces"])


class TestCheckAdjacencyTool:
    def test_with_kg_store(self, sample_appspec: SimpleNamespace) -> None:
        store = MagicMock()
        store.persona_capability_map.return_value = {
            "workspaces": [],
            "surfaces": [],
            "entities": [],
        }
        store.compute_adjacency.return_value = 1
        store.get_entity.return_value = None

        mission = build_discovery_mission(sample_appspec, kg_store=store)
        tool = next(t for t in mission.tools if t.name == "check_adjacency")
        result = tool.handler(node_a="entity:Task", node_b="surface:task_list")
        assert result["distance"] == 1
        assert result["within_boundary"] is True

    def test_without_kg_store(self, sample_appspec: SimpleNamespace) -> None:
        mission = build_discovery_mission(sample_appspec, kg_store=None)
        tool = next(t for t in mission.tools if t.name == "check_adjacency")
        result = tool.handler(node_a="Task", node_b="task_list")
        assert result["distance"] == -1


# =============================================================================
# Tests: Completion Criteria
# =============================================================================


class TestDiscoveryCompletion:
    def test_done_action_completes(self, sample_appspec: SimpleNamespace) -> None:
        from dazzle.agent.models import ActionType, AgentAction

        mission = build_discovery_mission(sample_appspec)
        action = AgentAction(type=ActionType.DONE, reasoning="Exploration complete")
        assert mission.completion_criteria(action, []) is True

    def test_non_done_does_not_complete(self, sample_appspec: SimpleNamespace) -> None:
        from dazzle.agent.models import ActionType, AgentAction

        mission = build_discovery_mission(sample_appspec)
        action = AgentAction(type=ActionType.NAVIGATE, target="/tasks")
        assert mission.completion_criteria(action, []) is False
