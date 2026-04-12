"""Smoke test: parse the real dashboard-grid contract and build a QA mission.

This doesn't run the agent (that requires a live app), but verifies
the parse → build pipeline works end-to-end against shipped artefacts.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dazzle.agent.core import Mission
from dazzle.agent.missions._shared import parse_component_contract
from dazzle.agent.missions.ux_quality import build_ux_quality_mission

SKILL_COMPONENT_DIR = Path.home() / ".claude/skills/ux-architect/components"


class TestUxCycleSmokeIntegration:
    def test_dashboard_grid_contract_parses(self):
        path = SKILL_COMPONENT_DIR / "dashboard-grid.md"
        if not path.exists():
            pytest.skip(f"ux-architect skill not installed at {SKILL_COMPONENT_DIR}")
        contract = parse_component_contract(path)
        assert contract.component_name == "dashboard-grid"
        assert len(contract.quality_gates) >= 3
        assert contract.anatomy  # should have anatomy parts
        assert contract.primitives  # should have drag-and-drop, resize

    def test_data_table_contract_parses(self):
        path = SKILL_COMPONENT_DIR / "data-table.md"
        if not path.exists():
            pytest.skip(f"ux-architect skill not installed at {SKILL_COMPONENT_DIR}")
        contract = parse_component_contract(path)
        assert contract.component_name == "data-table"
        assert len(contract.quality_gates) >= 3

    def test_build_mission_from_real_contract(self):
        path = SKILL_COMPONENT_DIR / "dashboard-grid.md"
        if not path.exists():
            pytest.skip("ux-architect skill not installed")
        contract = parse_component_contract(path)

        persona = MagicMock()
        persona.id = "admin"
        persona.label = "Administrator"

        results: dict = {}
        mission = build_ux_quality_mission(
            contract=contract,
            persona=persona,
            example_app="ops_dashboard",
            base_url="http://localhost:3462",
            results=results,
        )

        assert isinstance(mission, Mission)
        assert "dashboard-grid" in mission.name
        assert "admin" in mission.name
        # Every gate should be mentioned in the prompt
        for gate in contract.quality_gates:
            assert gate.id in mission.system_prompt
        # record_gate_result tool should be present
        assert any(t.name == "record_gate_result" for t in mission.tools)
