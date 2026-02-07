"""Tests for the entity completeness mission."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dazzle.agent.core import Mission
from dazzle.agent.missions.entity_completeness import (
    _static_entity_analysis,
    build_entity_completeness_mission,
)
from dazzle.agent.models import ActionType, AgentAction

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
    transitions: list[Any] | None = None,
) -> SimpleNamespace:
    fields = [_make_field(n) for n in (field_names or ["id", "title"])]
    sm = None
    if states:
        sm = SimpleNamespace(
            states=states,
            transitions=transitions or [],
        )
    return SimpleNamespace(name=name, title=title, fields=fields, state_machine=sm)


def _make_surface(
    name: str,
    title: str,
    mode: str = "list",
    entity_ref: str | None = None,
    actions: list[Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=title,
        mode=mode,
        entity_ref=entity_ref,
        entity=entity_ref,
        sections=[],
        actions=actions or [],
    )


def _make_transition(from_state: str, to_state: str) -> SimpleNamespace:
    return SimpleNamespace(from_state=from_state, to_state=to_state, event=None)


def _make_action(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _make_process(
    name: str,
    steps: list[Any] | None = None,
    implements: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(name=name, title=name, steps=steps or [], implements=implements or [])


def _make_human_task_step(name: str, surface: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        kind="human_task",
        human_task=SimpleNamespace(surface=surface),
    )


def _make_appspec(
    entities: list[Any] | None = None,
    surfaces: list[Any] | None = None,
    personas: list[Any] | None = None,
    workspaces: list[Any] | None = None,
    processes: list[Any] | None = None,
    experiences: list[Any] | None = None,
    stories: list[Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name="test_app",
        domain=SimpleNamespace(entities=entities or []),
        surfaces=surfaces or [],
        personas=personas or [],
        workspaces=workspaces or [],
        processes=processes or [],
        experiences=experiences or [],
        stories=stories or [],
    )


# =============================================================================
# Tests: Static Entity Analysis
# =============================================================================


class TestStaticEntityAnalysis:
    def test_entity_with_no_surfaces(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[],
        )
        report = _static_entity_analysis(appspec)
        assert report.gap_count >= 1
        gap_types = [g.gap_type for g in report.gaps]
        assert "no_surface" in gap_types

    def test_entity_with_no_surfaces_is_critical(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[],
        )
        report = _static_entity_analysis(appspec)
        no_surface_gaps = [g for g in report.gaps if g.gap_type == "no_surface"]
        assert all(g.severity == "critical" for g in no_surface_gaps)

    def test_missing_list_surface(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[
                _make_surface("task_create", "Create Task", "create", "Task"),
            ],
        )
        report = _static_entity_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "missing_list" in gap_types

    def test_missing_create_surface(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[
                _make_surface("task_list", "Task List", "list", "Task"),
            ],
        )
        report = _static_entity_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "missing_create" in gap_types

    def test_missing_edit_surface(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[
                _make_surface("task_list", "Task List", "list", "Task"),
                _make_surface("task_create", "Create Task", "create", "Task"),
            ],
        )
        report = _static_entity_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "missing_edit" in gap_types

    def test_missing_view_surface(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[
                _make_surface("task_list", "Task List", "list", "Task"),
                _make_surface("task_create", "Create Task", "create", "Task"),
                _make_surface("task_edit", "Edit Task", "edit", "Task"),
            ],
        )
        report = _static_entity_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "missing_view" in gap_types

    def test_complete_entity_has_no_crud_gaps(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[
                _make_surface("task_list", "Task List", "list", "Task"),
                _make_surface("task_create", "Create Task", "create", "Task"),
                _make_surface("task_edit", "Edit Task", "edit", "Task"),
                _make_surface("task_view", "View Task", "view", "Task"),
            ],
        )
        report = _static_entity_analysis(appspec)
        crud_gaps = [
            g
            for g in report.gaps
            if g.gap_type
            in ("no_surface", "missing_list", "missing_create", "missing_edit", "missing_view")
        ]
        assert len(crud_gaps) == 0

    def test_no_transition_ui(self) -> None:
        transitions = [_make_transition("open", "closed")]
        appspec = _make_appspec(
            entities=[
                _make_entity("Task", "Task", states=["open", "closed"], transitions=transitions),
            ],
            surfaces=[
                _make_surface("task_list", "Task List", "list", "Task"),
                _make_surface("task_create", "Create Task", "create", "Task"),
                _make_surface("task_edit", "Edit Task", "edit", "Task"),
                _make_surface("task_view", "View Task", "view", "Task"),
            ],
        )
        report = _static_entity_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "no_transition_ui" in gap_types

    def test_has_transition_ui_no_gap(self) -> None:
        transitions = [_make_transition("open", "closed")]
        appspec = _make_appspec(
            entities=[
                _make_entity("Task", "Task", states=["open", "closed"], transitions=transitions),
            ],
            surfaces=[
                _make_surface(
                    "task_list",
                    "Task List",
                    "list",
                    "Task",
                    actions=[_make_action("close_task")],
                ),
                _make_surface("task_create", "Create Task", "create", "Task"),
                _make_surface("task_edit", "Edit Task", "edit", "Task"),
                _make_surface("task_view", "View Task", "view", "Task"),
            ],
        )
        report = _static_entity_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "no_transition_ui" not in gap_types

    def test_process_referenced_entity_no_surface(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Invoice", "Invoice")],
            surfaces=[_make_surface("inv_form", "Invoice Form", "edit", "Invoice")],
            processes=[
                _make_process(
                    "approve_invoice",
                    steps=[_make_human_task_step("review", "inv_form")],
                ),
            ],
        )
        # Invoice has some surfaces, so no process_referenced gap
        report = _static_entity_analysis(appspec)
        proc_gaps = [g for g in report.gaps if g.gap_type == "process_referenced"]
        assert len(proc_gaps) == 0

    def test_empty_appspec(self) -> None:
        appspec = _make_appspec()
        report = _static_entity_analysis(appspec)
        assert report.gap_count == 0

    def test_report_summary(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[],
        )
        report = _static_entity_analysis(appspec)
        summary = report.to_summary()
        assert "Task" in summary
        assert "gap" in summary.lower()

    def test_report_summary_no_gaps(self) -> None:
        appspec = _make_appspec()
        report = _static_entity_analysis(appspec)
        summary = report.to_summary()
        assert "No entity coverage gaps found" in summary

    def test_entity_coverage_dict(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[
                _make_surface("task_list", "Task List", "list", "Task"),
            ],
        )
        report = _static_entity_analysis(appspec)
        assert "Task" in report.entity_coverage
        coverage = report.entity_coverage["Task"]
        assert coverage["list"] is True
        assert coverage["create"] is False


# =============================================================================
# Tests: check_crud_coverage Tool
# =============================================================================


class TestCheckCrudCoverageTool:
    def test_returns_coverage(self) -> None:
        from dazzle.agent.missions.entity_completeness import _make_check_crud_coverage_tool

        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[
                _make_surface("task_list", "Task List", "list", "Task"),
                _make_surface("task_create", "Create Task", "create", "Task"),
            ],
        )
        tool = _make_check_crud_coverage_tool(appspec)
        result = tool.handler(entity_name="Task")
        assert result["list"] is True
        assert result["create"] is True
        assert result["edit"] is False
        assert result["view"] is False
        assert "task_list" in result["surfaces"]

    def test_unknown_entity(self) -> None:
        from dazzle.agent.missions.entity_completeness import _make_check_crud_coverage_tool

        appspec = _make_appspec()
        tool = _make_check_crud_coverage_tool(appspec)
        result = tool.handler(entity_name="NonExistent")
        assert result["list"] is False
        assert result["surfaces"] == []

    def test_empty_entity_name(self) -> None:
        from dazzle.agent.missions.entity_completeness import _make_check_crud_coverage_tool

        appspec = _make_appspec()
        tool = _make_check_crud_coverage_tool(appspec)
        result = tool.handler(entity_name="")
        assert "error" in result


# =============================================================================
# Tests: check_state_transitions Tool
# =============================================================================


class TestCheckStateTransitionsTool:
    def test_returns_transitions(self) -> None:
        from dazzle.agent.missions.entity_completeness import _make_check_state_transitions_tool

        transitions = [_make_transition("open", "closed")]
        appspec = _make_appspec(
            entities=[
                _make_entity("Task", "Task", states=["open", "closed"], transitions=transitions),
            ],
            surfaces=[],
        )
        tool = _make_check_state_transitions_tool(appspec)
        result = tool.handler(entity_name="Task")
        assert result["has_state_machine"] is True
        assert len(result["transitions"]) == 1
        assert result["transitions"][0]["from"] == "open"
        assert result["transitions"][0]["to"] == "closed"

    def test_no_state_machine(self) -> None:
        from dazzle.agent.missions.entity_completeness import _make_check_state_transitions_tool

        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
        )
        tool = _make_check_state_transitions_tool(appspec)
        result = tool.handler(entity_name="Task")
        assert result["has_state_machine"] is False
        assert result["transitions"] == []

    def test_unknown_entity(self) -> None:
        from dazzle.agent.missions.entity_completeness import _make_check_state_transitions_tool

        appspec = _make_appspec()
        tool = _make_check_state_transitions_tool(appspec)
        result = tool.handler(entity_name="NonExistent")
        assert "error" in result

    def test_empty_entity_name(self) -> None:
        from dazzle.agent.missions.entity_completeness import _make_check_state_transitions_tool

        appspec = _make_appspec()
        tool = _make_check_state_transitions_tool(appspec)
        result = tool.handler(entity_name="")
        assert "error" in result


# =============================================================================
# Tests: Mission Builder
# =============================================================================


class TestBuildEntityCompletenessMission:
    def test_returns_valid_mission(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[_make_surface("task_list", "Task List", "list", "Task")],
        )
        mission = build_entity_completeness_mission(appspec)
        assert isinstance(mission, Mission)
        assert mission.name == "entity_completeness"

    def test_has_correct_tools(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[],
        )
        mission = build_entity_completeness_mission(appspec)
        tool_names = {t.name for t in mission.tools}
        assert "observe_gap" in tool_names
        assert "query_dsl" in tool_names
        assert "check_crud_coverage" in tool_names
        assert "check_state_transitions" in tool_names

    def test_gaps_in_context(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[],
        )
        mission = build_entity_completeness_mission(appspec)
        assert mission.context["mode"] == "entity_completeness"
        assert mission.context["static_analysis"]["gaps_found"] >= 1

    def test_gap_summary_in_prompt(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task", "Task")],
            surfaces=[],
        )
        mission = build_entity_completeness_mission(appspec)
        assert "Task" in mission.system_prompt
        assert (
            "no surfaces" in mission.system_prompt.lower() or "gap" in mission.system_prompt.lower()
        )

    def test_completion_on_done(self) -> None:
        action = AgentAction(type=ActionType.DONE, success=True)
        assert mission_completion_triggers_done(action)

    def test_stagnation_at_6_steps(self) -> None:
        from dazzle.agent.missions.entity_completeness import _entity_completeness_completion
        from dazzle.agent.models import ActionResult, PageState, Step

        action = AgentAction(type=ActionType.NAVIGATE, target="/test")
        history = []
        for i in range(6):
            history.append(
                Step(
                    state=PageState(url="http://test", title="test"),
                    action=AgentAction(type=ActionType.NAVIGATE, target="/test"),
                    result=ActionResult(message="ok"),
                    step_number=i + 1,
                )
            )
        assert _entity_completeness_completion(action, history) is True

    def test_no_stagnation_with_tool_calls(self) -> None:
        from dazzle.agent.missions.entity_completeness import _entity_completeness_completion
        from dazzle.agent.models import ActionResult, PageState, Step

        action = AgentAction(type=ActionType.NAVIGATE, target="/test")
        history = []
        for i in range(6):
            action_type = ActionType.TOOL if i % 2 == 0 else ActionType.NAVIGATE
            history.append(
                Step(
                    state=PageState(url="http://test", title="test"),
                    action=AgentAction(type=action_type, target="check_crud_coverage"),
                    result=ActionResult(message="ok"),
                    step_number=i + 1,
                )
            )
        assert _entity_completeness_completion(action, history) is False


def mission_completion_triggers_done(action: AgentAction) -> bool:
    from dazzle.agent.missions.entity_completeness import _entity_completeness_completion

    return _entity_completeness_completion(action, [])
