"""Tests for build_investigator_mission + NullObserver/NullExecutor."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dazzle.fitness.backlog import upsert_findings
from dazzle.fitness.investigator.agent_backends import NullExecutor, NullObserver
from dazzle.fitness.investigator.case_file import build_case_file
from dazzle.fitness.investigator.mission import build_investigator_mission
from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.triage import Cluster


def _minimal_finding() -> Finding:
    return Finding(
        id="f_001",
        created=datetime(2026, 4, 14, tzinfo=UTC),
        run_id="run-1",
        cycle=None,
        axis="coverage",
        locus="implementation",
        severity="high",
        persona="admin",
        capability_ref="x",
        expected="y",
        observed="z",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={},
            diff_summary=[],
            transcript_excerpt=[{"text": "src/foo.html:1 problem"}],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )


def _minimal_cluster() -> Cluster:
    return Cluster(
        cluster_id="CL-deadbeef",
        locus="implementation",
        axis="coverage",
        canonical_summary="z",
        persona="admin",
        severity="high",
        cluster_size=1,
        first_seen=datetime(2026, 4, 14, tzinfo=UTC),
        last_seen=datetime(2026, 4, 14, tzinfo=UTC),
        sample_id="f_001",
    )


@pytest.mark.asyncio
async def test_null_observer_returns_empty_state() -> None:
    obs = NullObserver()
    state = await obs.observe()
    assert state.url == ""
    assert obs.current_url == ""
    # navigate is a no-op
    await obs.navigate("http://example.com")


@pytest.mark.asyncio
async def test_null_executor_rejects_page_actions() -> None:
    from dazzle.agent.models import ActionType, AgentAction

    ex = NullExecutor()
    result = await ex.execute(AgentAction(type=ActionType.CLICK, target="button", value=None))
    assert result.error is not None
    assert "tool-only" in (result.error or "")


def test_build_investigator_mission_wires_tools_and_prompt(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(tmp_path / "dev_docs" / "fitness-backlog.md", [_minimal_finding()])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.html").write_text("<div>x</div>")

    case_file = build_case_file(_minimal_cluster(), tmp_path)
    mission, tool_state = build_investigator_mission(
        case_file=case_file,
        dazzle_root=tmp_path,
        llm_run_id="run-xyz",
    )

    # System prompt contains the case file text and root-cause framing
    assert "# Case File" in mission.system_prompt
    assert "CL-deadbeef" in mission.system_prompt
    assert "root cause" in mission.system_prompt.lower()

    # All 6 tools wired
    tool_names = {t.name for t in mission.tools}
    assert tool_names == {
        "read_file",
        "query_dsl",
        "get_cluster_findings",
        "get_related_clusters",
        "search_spec",
        "propose_fix",
    }

    # Max steps from the plan
    assert mission.max_steps == 25

    # Completion criterion: returns True when state.terminal_status is set
    from dazzle.agent.models import ActionType, AgentAction

    tool_state.terminal_status = "proposed"
    fake_action = AgentAction(type=ActionType.TOOL, target="propose_fix", value=None)
    assert mission.completion_criteria(fake_action, []) is True
