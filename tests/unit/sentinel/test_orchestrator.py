"""Tests for the ScanOrchestrator.

Agents are stubbed (their heuristics have their own tests); what is pinned
here is what the orchestrator does with their results: agent selection,
severity and suppression filtering, summary counts, persistence, and carrying
state forward from the previous scan.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dazzle.sentinel.models import (
    AgentId,
    AgentResult,
    Finding,
    FindingStatus,
    ScanConfig,
    ScanResult,
    Severity,
)
from dazzle.sentinel.orchestrator import ScanOrchestrator
from dazzle.sentinel.store import FindingStore

from .conftest import make_appspec


def _finding(
    heuristic_id: str = "DI-01",
    severity: Severity = Severity.HIGH,
    status: FindingStatus = FindingStatus.OPEN,
) -> Finding:
    return Finding(
        agent=AgentId(heuristic_id[:2]),
        heuristic_id=heuristic_id,
        category="test",
        subcategory="test",
        severity=severity,
        title=f"Finding {heuristic_id}",
        description="test",
        entity_name="Task",
        status=status,
    )


def _agent(agent_id: AgentId, findings: list[Finding]) -> MagicMock:
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.run.return_value = AgentResult(agent=agent_id, findings=findings, heuristics_run=1)
    return agent


def _scan(project: Path, agents: list[MagicMock], config: ScanConfig | None = None) -> ScanResult:
    with patch("dazzle.sentinel.agents.get_all_agents", return_value=agents):
        return ScanOrchestrator(project).run_scan(make_appspec(), config)


@pytest.mark.parametrize(
    ("findings", "config", "expected_ids"),
    [
        pytest.param(
            [
                _finding("DI-01", Severity.CRITICAL),
                _finding("DI-02", Severity.LOW),
                _finding("DI-03", Severity.INFO),
            ],
            {"severity_threshold": Severity.LOW},
            ["DI-01", "DI-02"],
            id="severity-threshold-drops-below",
        ),
        pytest.param(
            [_finding(status=FindingStatus.FALSE_POSITIVE)],
            {},
            [],
            id="false-positives-excluded-by-default",
        ),
        pytest.param(
            [_finding(status=FindingStatus.FALSE_POSITIVE)],
            {"include_suppressed": True},
            ["DI-01"],
            id="include-suppressed",
        ),
    ],
)
def test_run_scan_filters_findings(
    tmp_path: Path, findings: list[Finding], config: dict[str, Any], expected_ids: list[str]
) -> None:
    result = _scan(tmp_path, [_agent(AgentId.DI, findings)], ScanConfig(**config))
    assert [f.heuristic_id for f in result.findings] == expected_ids


def test_run_scan_runs_only_selected_agents(tmp_path: Path) -> None:
    di = _agent(AgentId.DI, [_finding("DI-01")])
    aa = _agent(AgentId.AA, [_finding("AA-01")])
    result = _scan(tmp_path, [di, aa], ScanConfig(agents=[AgentId.DI]))
    di.run.assert_called_once()
    aa.run.assert_not_called()
    assert [f.heuristic_id for f in result.findings] == ["DI-01"]


def test_run_scan_summarises_and_persists(tmp_path: Path) -> None:
    result = _scan(
        tmp_path,
        [
            _agent(
                AgentId.DI,
                [_finding("DI-01"), _finding("DI-02"), _finding("DI-03", Severity.LOW)],
            ),
            _agent(AgentId.AA, [_finding("AA-01")]),
        ],
    )
    assert result.summary.total_findings == 4
    assert result.summary.by_severity == {"high": 3, "low": 1}
    assert result.summary.by_agent == {"DI": 3, "AA": 1}
    assert result.duration_ms >= 0
    (saved,) = (tmp_path / ".dazzle" / "sentinel").glob("sentinel_*.json")
    assert FindingStore(tmp_path).load_scan(result.scan_id) is not None
    assert result.scan_id in saved.read_text()


def test_rescan_keeps_first_detected(tmp_path: Path) -> None:
    first = _scan(tmp_path, [_agent(AgentId.DI, [_finding("DI-01")])])
    second = _scan(tmp_path, [_agent(AgentId.DI, [_finding("DI-01")])])
    assert len(second.findings) == 1
    assert second.findings[0].first_detected == first.findings[0].first_detected


def test_rescan_carries_suppression_forward(tmp_path: Path) -> None:
    f = _finding("DI-01")
    _scan(tmp_path, [_agent(AgentId.DI, [f])])
    FindingStore(tmp_path).suppress_finding(f.finding_id, "false positive")
    second = _scan(
        tmp_path,
        [_agent(AgentId.DI, [_finding("DI-01")])],
        ScanConfig(include_suppressed=True),
    )
    assert [f.status for f in second.findings] == [FindingStatus.SUPPRESSED]


def test_rescan_counts_resolved(tmp_path: Path) -> None:
    _scan(tmp_path, [_agent(AgentId.DI, [_finding("DI-01"), _finding("DI-02")])])
    second = _scan(tmp_path, [_agent(AgentId.DI, [_finding("DI-01")])])
    assert second.summary.resolved == 1
