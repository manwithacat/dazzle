"""Tests for the workflow coherence mission."""

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.agent.missions.workflow_coherence import (
    _static_workflow_analysis,
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
    @pytest.mark.parametrize(
        "appspec_kwargs,expected_gap_type,present",
        [
            (
                {
                    "surfaces": [_make_surface("task_list", "Task List")],
                    "processes": [
                        _make_process(
                            "approve",
                            steps=[_make_human_task_step("review", "nonexistent_surface")],
                        )
                    ],
                },
                "missing_human_task_surface",
                True,
            ),
            (
                {
                    "surfaces": [_make_surface("review_form", "Review Form")],
                    "processes": [
                        _make_process(
                            "approve",
                            steps=[_make_human_task_step("review", "review_form")],
                        )
                    ],
                },
                "missing_human_task_surface",
                False,
            ),
            (
                {
                    "processes": [
                        _make_process(
                            "main_process",
                            steps=[_make_subprocess_step("sub", "nonexistent_process")],
                        )
                    ]
                },
                "missing_subprocess",
                True,
            ),
            (
                {
                    "processes": [
                        _make_process(
                            "main_process",
                            steps=[_make_subprocess_step("sub", "child_process")],
                        ),
                        _make_process("child_process"),
                    ]
                },
                "missing_subprocess",
                False,
            ),
            (
                {
                    "entities": [_make_entity("Order", "Order")],
                    "processes": [
                        _make_process(
                            "on_order_confirmed",
                            trigger=_make_trigger("entity_status_transition", "Order"),
                        )
                    ],
                },
                "trigger_no_state_machine",
                True,
            ),
            (
                {
                    "entities": [],
                    "processes": [
                        _make_process(
                            "on_order_confirmed",
                            trigger=_make_trigger("entity_status_transition", "NonExistent"),
                        )
                    ],
                },
                "trigger_no_state_machine",
                True,
            ),
            (
                {
                    "stories": [_make_story("ST-001", "Create invoice")],
                    "processes": [],
                },
                "story_no_process",
                True,
            ),
            (
                {
                    "stories": [_make_story("ST-001", "Create invoice")],
                    "processes": [_make_process("create_invoice", implements=["ST-001"])],
                },
                "story_no_process",
                False,
            ),
        ],
        ids=[
            "test_missing_human_task_surface",
            "test_human_task_surface_exists",
            "test_missing_subprocess",
            "test_subprocess_exists",
            "test_trigger_entity_no_state_machine",
            "test_trigger_entity_not_found",
            "test_story_no_process",
            "test_story_with_process",
        ],
    )
    def test_gap_type_presence(
        self,
        appspec_kwargs: dict,
        expected_gap_type: str,
        present: bool,
    ) -> None:
        appspec = _make_appspec(**appspec_kwargs)
        report = _static_workflow_analysis(appspec)
        gap_types = [g.gap_type for g in report.gaps]
        if present:
            assert expected_gap_type in gap_types
        else:
            assert expected_gap_type not in gap_types

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
# Tests: Mode Routing
# =============================================================================


class TestModeRouting:
    def test_tool_schema_has_coherence_operation(self) -> None:
        """Verify the consolidated tool schema includes coherence operation."""
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        discovery_tool = next(t for t in tools if t.name == "discovery")
        ops = discovery_tool.input_schema["properties"]["operation"]["enum"]
        assert "coherence" in ops
