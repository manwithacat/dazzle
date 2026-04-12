"""Tests for the ux_quality mission builder."""

from unittest.mock import MagicMock

import pytest

from dazzle.agent.core import Mission
from dazzle.agent.missions._shared import ComponentContract, QualityGate
from dazzle.agent.missions.ux_quality import (
    build_ux_quality_mission,
    make_record_gate_tool,
)


@pytest.fixture
def sample_contract() -> ComponentContract:
    return ComponentContract(
        component_name="data-table",
        quality_gates=[
            QualityGate(
                id="sort_loading", description="Sort a column — does the loading state appear?"
            ),
            QualityGate(
                id="colgroup_resize", description="Resize a column — do cells reflow via colgroup?"
            ),
            QualityGate(id="edit_tab_nav", description="Tab through cells — does focus advance?"),
        ],
        anatomy=["table-root", "table-head", "table-row"],
        primitives=["sort", "column-resize", "inline-edit"],
    )


@pytest.fixture
def sample_persona():
    persona = MagicMock()
    persona.id = "accountant"
    persona.label = "Accountant"
    return persona


class TestRecordGateTool:
    def test_tool_records_result_in_shared_dict(self):
        results: dict = {}
        tool = make_record_gate_tool(results)
        tool.handler({"gate_id": "sort_loading", "pass": True, "observation": "worked fine"})
        assert results == {"sort_loading": {"pass": True, "observation": "worked fine"}}

    def test_tool_schema_has_required_fields(self):
        tool = make_record_gate_tool({})
        assert tool.name == "record_gate_result"
        props = tool.schema["properties"]
        assert "gate_id" in props
        assert "pass" in props
        assert "observation" in props
        required = tool.schema["required"]
        assert "gate_id" in required
        assert "pass" in required
        assert "observation" in required

    def test_tool_records_multiple_gates(self):
        results: dict = {}
        tool = make_record_gate_tool(results)
        tool.handler({"gate_id": "gate_a", "pass": True, "observation": "a"})
        tool.handler({"gate_id": "gate_b", "pass": False, "observation": "b"})
        assert len(results) == 2
        assert results["gate_a"]["pass"] is True
        assert results["gate_b"]["pass"] is False


class TestBuildUxQualityMission:
    def test_returns_mission_instance(self, sample_contract, sample_persona):
        mission = build_ux_quality_mission(
            contract=sample_contract,
            persona=sample_persona,
            example_app="contact_manager",
            base_url="http://localhost:3462",
            results={},
        )
        assert isinstance(mission, Mission)

    def test_mission_name_includes_component_and_persona(self, sample_contract, sample_persona):
        mission = build_ux_quality_mission(
            contract=sample_contract,
            persona=sample_persona,
            example_app="contact_manager",
            base_url="http://localhost:3462",
            results={},
        )
        assert "data-table" in mission.name
        assert "accountant" in mission.name

    def test_mission_system_prompt_lists_all_gates(self, sample_contract, sample_persona):
        mission = build_ux_quality_mission(
            contract=sample_contract,
            persona=sample_persona,
            example_app="contact_manager",
            base_url="http://localhost:3462",
            results={},
        )
        prompt = mission.system_prompt
        assert "data-table" in prompt
        assert "Accountant" in prompt
        assert "sort_loading" in prompt
        assert "colgroup_resize" in prompt
        assert "edit_tab_nav" in prompt

    def test_mission_tools_include_record_gate_result(self, sample_contract, sample_persona):
        results: dict = {}
        mission = build_ux_quality_mission(
            contract=sample_contract,
            persona=sample_persona,
            example_app="contact_manager",
            base_url="http://localhost:3462",
            results=results,
        )
        tool_names = [t.name for t in mission.tools]
        assert "record_gate_result" in tool_names

    def test_mission_start_url_is_base_url(self, sample_contract, sample_persona):
        mission = build_ux_quality_mission(
            contract=sample_contract,
            persona=sample_persona,
            example_app="contact_manager",
            base_url="http://localhost:3462",
            results={},
        )
        assert mission.start_url == "http://localhost:3462"

    def test_mission_context_stores_metadata(self, sample_contract, sample_persona):
        mission = build_ux_quality_mission(
            contract=sample_contract,
            persona=sample_persona,
            example_app="contact_manager",
            base_url="http://localhost:3462",
            results={},
        )
        assert mission.context["component"] == "data-table"
        assert mission.context["persona_id"] == "accountant"
        assert mission.context["example_app"] == "contact_manager"

    def test_stagnation_completion_triggers_after_5_silent_steps(
        self, sample_contract, sample_persona
    ):
        mission = build_ux_quality_mission(
            contract=sample_contract,
            persona=sample_persona,
            example_app="contact_manager",
            base_url="http://localhost:3462",
            results={},
        )
        # Build a history of 5 steps with no record_gate_result tool calls
        from dazzle.agent.models import ActionType, AgentAction, Step

        history = []
        for i in range(5):
            action = AgentAction(
                type=ActionType.DONE if i == 4 else ActionType.CLICK,
                target="foo",
            )
            history.append(
                Step(
                    state=MagicMock(),
                    action=action,
                    result=MagicMock(success=True),
                )
            )
        last_action = history[-1].action
        # Should trigger completion
        assert mission.completion_criteria(last_action, history) is True
