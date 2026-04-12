"""Tests for the ux_explore mission builder."""

from unittest.mock import MagicMock

import pytest

from dazzle.agent.core import Mission
from dazzle.agent.missions.ux_explore import (
    Strategy,
    build_ux_explore_mission,
    make_propose_component_tool,
    make_record_edge_case_tool,
)


@pytest.fixture
def sample_persona():
    persona = MagicMock()
    persona.id = "admin"
    persona.label = "Administrator"
    return persona


class TestExploreTools:
    def test_propose_component_tool_records_proposal(self):
        proposals: list = []
        tool = make_propose_component_tool(proposals)
        tool.handler(
            {
                "component_name": "tree-view",
                "description": "Hierarchical tree navigation used in the kanban board",
                "example_app": "support_tickets",
            }
        )
        assert len(proposals) == 1
        assert proposals[0]["component_name"] == "tree-view"
        assert proposals[0]["example_app"] == "support_tickets"

    def test_record_edge_case_tool_records_finding(self):
        findings: list = []
        tool = make_record_edge_case_tool(findings)
        tool.handler(
            {
                "component_name": "data-table",
                "description": "Cmd+A with 0 rows selected throws a console error",
                "example_app": "contact_manager",
                "severity": "minor",
            }
        )
        assert len(findings) == 1
        assert findings[0]["severity"] == "minor"


class TestBuildUxExploreMission:
    def test_returns_mission_instance(self, sample_persona):
        mission = build_ux_explore_mission(
            strategy=Strategy.MISSING_CONTRACTS,
            persona=sample_persona,
            example_app="ops_dashboard",
            base_url="http://localhost:3462",
            proposals=[],
            findings=[],
        )
        assert isinstance(mission, Mission)

    def test_missing_contracts_strategy_prompt_mentions_contracts(self, sample_persona):
        mission = build_ux_explore_mission(
            strategy=Strategy.MISSING_CONTRACTS,
            persona=sample_persona,
            example_app="ops_dashboard",
            base_url="http://localhost:3462",
            proposals=[],
            findings=[],
        )
        assert "contract" in mission.system_prompt.lower()
        assert "propose_component" in mission.system_prompt

    def test_edge_cases_strategy_prompt_mentions_edge_cases(self, sample_persona):
        mission = build_ux_explore_mission(
            strategy=Strategy.EDGE_CASES,
            persona=sample_persona,
            example_app="ops_dashboard",
            base_url="http://localhost:3462",
            proposals=[],
            findings=[],
        )
        assert (
            "edge case" in mission.system_prompt.lower()
            or "adversarial" in mission.system_prompt.lower()
        )
        assert "record_edge_case" in mission.system_prompt

    def test_missing_contracts_mission_has_propose_tool(self, sample_persona):
        proposals: list = []
        mission = build_ux_explore_mission(
            strategy=Strategy.MISSING_CONTRACTS,
            persona=sample_persona,
            example_app="ops_dashboard",
            base_url="http://localhost:3462",
            proposals=proposals,
            findings=[],
        )
        tool_names = [t.name for t in mission.tools]
        assert "propose_component" in tool_names

    def test_edge_cases_mission_has_record_tool(self, sample_persona):
        findings: list = []
        mission = build_ux_explore_mission(
            strategy=Strategy.EDGE_CASES,
            persona=sample_persona,
            example_app="ops_dashboard",
            base_url="http://localhost:3462",
            proposals=[],
            findings=findings,
        )
        tool_names = [t.name for t in mission.tools]
        assert "record_edge_case" in tool_names
