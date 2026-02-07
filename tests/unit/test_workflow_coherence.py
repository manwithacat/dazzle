"""Tests for the workflow coherence mission."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dazzle.agent.core import Mission
from dazzle.agent.missions.workflow_coherence import (
    _static_workflow_analysis,
    build_workflow_coherence_mission,
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
    state_machine: Any = None,
) -> SimpleNamespace:
    fields = [_make_field(n) for n in (field_names or ["id", "title"])]
    return SimpleNamespace(name=name, title=title, fields=fields, state_machine=state_machine)


def _make_state_machine(states: list[str], transitions: list[Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(states=states, transitions=transitions or [])


def _make_surface(
    name: str,
    title: str,
    mode: str = "list",
    entity_ref: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=title,
        mode=mode,
        entity_ref=entity_ref,
        entity=entity_ref,
        sections=[],
        actions=[],
    )


def _make_human_task_step(name: str, surface: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        kind="human_task",
        human_task=SimpleNamespace(surface=surface),
        subprocess=None,
    )


def _make_subprocess_step(name: str, subprocess: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        kind="subprocess",
        subprocess=subprocess,
        human_task=None,
    )


def _make_service_step(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        kind="service",
        human_task=None,
        subprocess=None,
    )


def _make_trigger(kind: str, entity_name: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(kind=kind, entity_name=entity_name)


def _make_process(
    name: str,
    steps: list[Any] | None = None,
    trigger: Any = None,
    implements: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=name,
        steps=steps or [],
        trigger=trigger,
        implements=implements or [],
    )


def _make_story(story_id: str, title: str) -> SimpleNamespace:
    return SimpleNamespace(story_id=story_id, title=title)


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
# Tests: Static Workflow Analysis
# =============================================================================


class TestStaticWorkflowAnalysis:
    def test_missing_human_task_surface(self) -> None:
        appspec = _make_appspec(
            surfaces=[_make_surface("task_list", "Task List")],
            processes=[
                _make_process(
                    "approve",
                    steps=[_make_human_task_step("review", "nonexistent_surface")],
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "missing_human_task_surface" in gap_types

    def test_human_task_surface_exists(self) -> None:
        appspec = _make_appspec(
            surfaces=[_make_surface("review_form", "Review Form")],
            processes=[
                _make_process(
                    "approve",
                    steps=[_make_human_task_step("review", "review_form")],
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "missing_human_task_surface" not in gap_types

    def test_missing_subprocess(self) -> None:
        appspec = _make_appspec(
            processes=[
                _make_process(
                    "main_process",
                    steps=[_make_subprocess_step("sub", "nonexistent_process")],
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "missing_subprocess" in gap_types

    def test_subprocess_exists(self) -> None:
        appspec = _make_appspec(
            processes=[
                _make_process(
                    "main_process",
                    steps=[_make_subprocess_step("sub", "child_process")],
                ),
                _make_process("child_process"),
            ],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "missing_subprocess" not in gap_types

    def test_trigger_entity_no_state_machine(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Order", "Order")],
            processes=[
                _make_process(
                    "on_order_confirmed",
                    trigger=_make_trigger("entity_status_transition", "Order"),
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "trigger_no_state_machine" in gap_types

    def test_trigger_entity_has_state_machine(self) -> None:
        sm = _make_state_machine(["pending", "confirmed"])
        appspec = _make_appspec(
            entities=[_make_entity("Order", "Order", state_machine=sm)],
            processes=[
                _make_process(
                    "on_order_confirmed",
                    trigger=_make_trigger("entity_status_transition", "Order"),
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "trigger_no_state_machine" not in gap_types

    def test_trigger_entity_not_found(self) -> None:
        appspec = _make_appspec(
            entities=[],
            processes=[
                _make_process(
                    "on_order_confirmed",
                    trigger=_make_trigger("entity_status_transition", "NonExistent"),
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "trigger_no_state_machine" in gap_types

    def test_story_no_process(self) -> None:
        appspec = _make_appspec(
            stories=[_make_story("ST-001", "Create invoice")],
            processes=[],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "story_no_process" in gap_types

    def test_story_with_process(self) -> None:
        appspec = _make_appspec(
            stories=[_make_story("ST-001", "Create invoice")],
            processes=[_make_process("create_invoice", implements=["ST-001"])],
        )
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        assert "story_no_process" not in gap_types

    def test_empty_appspec(self) -> None:
        appspec = _make_appspec()
        report = _static_workflow_analysis(appspec)
        assert report.gap_count == 0

    def test_report_summary(self) -> None:
        appspec = _make_appspec(
            processes=[
                _make_process(
                    "approve",
                    steps=[_make_human_task_step("review", "missing_surface")],
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        summary = report.to_summary()
        assert "missing_surface" in summary
        assert "gap" in summary.lower()

    def test_report_summary_no_gaps(self) -> None:
        appspec = _make_appspec()
        report = _static_workflow_analysis(appspec)
        summary = report.to_summary()
        assert "No workflow coherence gaps found" in summary

    def test_missing_human_task_surface_is_critical(self) -> None:
        appspec = _make_appspec(
            processes=[
                _make_process(
                    "approve",
                    steps=[_make_human_task_step("review", "missing_surface")],
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        ht_gaps = [g for g in report.gaps if g.gap_type == "missing_human_task_surface"]
        assert all(g.severity == "critical" for g in ht_gaps)

    def test_missing_subprocess_is_high(self) -> None:
        appspec = _make_appspec(
            processes=[
                _make_process(
                    "main",
                    steps=[_make_subprocess_step("sub", "missing_process")],
                ),
            ],
        )
        report = _static_workflow_analysis(appspec)
        sp_gaps = [g for g in report.gaps if g.gap_type == "missing_subprocess"]
        assert all(g.severity == "high" for g in sp_gaps)


# =============================================================================
# Tests: check_process_coverage Tool
# =============================================================================


class TestCheckProcessCoverageTool:
    def test_step_coverage(self) -> None:
        from dazzle.agent.missions.workflow_coherence import _make_check_process_coverage_tool

        appspec = _make_appspec(
            surfaces=[_make_surface("review_form", "Review Form")],
            processes=[
                _make_process(
                    "approve",
                    steps=[
                        _make_service_step("validate"),
                        _make_human_task_step("review", "review_form"),
                    ],
                ),
            ],
        )
        tool = _make_check_process_coverage_tool(appspec)
        result = tool.handler(process_name="approve")
        assert result["process"] == "approve"
        assert result["step_count"] == 2
        # Check human_task step has surface_exists
        ht_step = [s for s in result["steps"] if "surface" in s][0]
        assert ht_step["surface_exists"] is True

    def test_unknown_process(self) -> None:
        from dazzle.agent.missions.workflow_coherence import _make_check_process_coverage_tool

        appspec = _make_appspec()
        tool = _make_check_process_coverage_tool(appspec)
        result = tool.handler(process_name="nonexistent")
        assert "error" in result

    def test_empty_process_name(self) -> None:
        from dazzle.agent.missions.workflow_coherence import _make_check_process_coverage_tool

        appspec = _make_appspec()
        tool = _make_check_process_coverage_tool(appspec)
        result = tool.handler(process_name="")
        assert "error" in result

    def test_subprocess_exists_check(self) -> None:
        from dazzle.agent.missions.workflow_coherence import _make_check_process_coverage_tool

        appspec = _make_appspec(
            processes=[
                _make_process(
                    "main",
                    steps=[_make_subprocess_step("sub", "child")],
                ),
                _make_process("child"),
            ],
        )
        tool = _make_check_process_coverage_tool(appspec)
        result = tool.handler(process_name="main")
        sp_step = [s for s in result["steps"] if "subprocess" in s][0]
        assert sp_step["subprocess_exists"] is True


# =============================================================================
# Tests: list_workflow_gaps Tool
# =============================================================================


class TestListWorkflowGapsTool:
    def test_all_gaps(self) -> None:
        from dazzle.agent.missions.workflow_coherence import (
            WorkflowCoherenceReport,
            WorkflowGap,
            _make_list_workflow_gaps_tool,
        )

        report = WorkflowCoherenceReport(
            gaps=[
                WorkflowGap(
                    gap_type="missing_human_task_surface",
                    severity="critical",
                    description="Missing surface",
                    process_name="proc1",
                ),
                WorkflowGap(
                    gap_type="story_no_process",
                    severity="medium",
                    description="Story not implemented",
                    story_id="ST-001",
                ),
            ]
        )
        tool = _make_list_workflow_gaps_tool(report)
        result = tool.handler()
        assert result["total"] == 2

    def test_filtered_gaps(self) -> None:
        from dazzle.agent.missions.workflow_coherence import (
            WorkflowCoherenceReport,
            WorkflowGap,
            _make_list_workflow_gaps_tool,
        )

        report = WorkflowCoherenceReport(
            gaps=[
                WorkflowGap(
                    gap_type="missing_human_task_surface",
                    severity="critical",
                    description="Missing surface",
                ),
                WorkflowGap(
                    gap_type="story_no_process",
                    severity="medium",
                    description="Story not implemented",
                ),
            ]
        )
        tool = _make_list_workflow_gaps_tool(report)
        result = tool.handler(gap_type="story_no_process")
        assert result["total"] == 1
        assert result["gaps"][0]["gap_type"] == "story_no_process"

    def test_empty_filter(self) -> None:
        from dazzle.agent.missions.workflow_coherence import (
            WorkflowCoherenceReport,
            _make_list_workflow_gaps_tool,
        )

        report = WorkflowCoherenceReport(gaps=[])
        tool = _make_list_workflow_gaps_tool(report)
        result = tool.handler()
        assert result["total"] == 0


# =============================================================================
# Tests: Mission Builder
# =============================================================================


class TestBuildWorkflowCoherenceMission:
    def test_returns_valid_mission(self) -> None:
        appspec = _make_appspec(
            processes=[
                _make_process(
                    "approve",
                    steps=[_make_human_task_step("review", "missing_form")],
                ),
            ],
        )
        mission = build_workflow_coherence_mission(appspec)
        assert isinstance(mission, Mission)
        assert mission.name == "workflow_coherence"

    def test_has_correct_tools(self) -> None:
        appspec = _make_appspec()
        mission = build_workflow_coherence_mission(appspec)
        tool_names = {t.name for t in mission.tools}
        assert "observe_gap" in tool_names
        assert "query_dsl" in tool_names
        assert "check_process_coverage" in tool_names
        assert "list_workflow_gaps" in tool_names

    def test_gaps_in_context(self) -> None:
        appspec = _make_appspec(
            processes=[
                _make_process(
                    "approve",
                    steps=[_make_human_task_step("review", "missing_form")],
                ),
            ],
        )
        mission = build_workflow_coherence_mission(appspec)
        assert mission.context["mode"] == "workflow_coherence"
        assert mission.context["static_analysis"]["gaps_found"] >= 1

    def test_completion_on_done(self) -> None:
        from dazzle.agent.missions.workflow_coherence import _workflow_coherence_completion

        action = AgentAction(type=ActionType.DONE, success=True)
        assert _workflow_coherence_completion(action, []) is True

    def test_stagnation_at_6_steps(self) -> None:
        from dazzle.agent.missions.workflow_coherence import _workflow_coherence_completion
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
        assert _workflow_coherence_completion(action, history) is True


# =============================================================================
# Tests: Mode Routing
# =============================================================================


class TestModeRouting:
    def test_tool_schema_has_mode_enum(self) -> None:
        """Verify the consolidated tool schema includes mode enum by reading source."""
        # Read the tools_consolidated.py source and check for mode enum
        # This avoids MCP import issues while still verifying the schema.
        from pathlib import Path

        tools_file = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dazzle"
            / "mcp"
            / "server"
            / "tools_consolidated.py"
        )
        source = tools_file.read_text()
        # Verify the mode property exists in discovery tool section
        assert '"mode"' in source
        assert '"persona"' in source
        assert '"entity_completeness"' in source
        assert '"workflow_coherence"' in source

    def test_unknown_mode_error(self) -> None:
        """Verify that an unknown mode returns an error via the handler."""
        import json
        import sys
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        # Pre-mock mcp modules
        for _mod in ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.stdio", "mcp.types"):
            sys.modules.setdefault(_mod, MagicMock(pytest_plugins=[]))

        from dazzle.mcp.server.handlers.discovery import run_discovery_handler

        # Mock _load_appspec since we don't have a real project
        with patch("dazzle.mcp.server.handlers.discovery._load_appspec") as mock_load:
            result_str = run_discovery_handler(
                Path("/fake/path"),
                {"mode": "invalid_mode"},
            )
            result = json.loads(result_str)
            assert "error" in result
            assert "invalid_mode" in result["error"]
            # _load_appspec should not have been called
            mock_load.assert_not_called()
