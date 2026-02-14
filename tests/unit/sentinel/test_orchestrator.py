"""Tests for the ScanOrchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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

from .conftest import make_appspec

_AGENTS_PATCH = "dazzle.sentinel.agents.get_all_agents"

# =============================================================================
# Helpers
# =============================================================================


def _finding(
    heuristic_id: str = "DI-01",
    severity: Severity = Severity.HIGH,
    entity_name: str | None = "Task",
    status: FindingStatus = FindingStatus.OPEN,
) -> Finding:
    return Finding(
        agent=AgentId.DI,
        heuristic_id=heuristic_id,
        category="test",
        subcategory="test",
        severity=severity,
        title=f"Finding {heuristic_id}",
        description="test",
        entity_name=entity_name,
        status=status,
    )


def _mock_agent(agent_id: AgentId, findings: list[Finding]) -> MagicMock:
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.run.return_value = AgentResult(
        agent=agent_id,
        findings=findings,
        heuristics_run=1,
    )
    return agent


# =============================================================================
# Tests
# =============================================================================


class TestRunScan:
    def test_returns_scan_result(self, tmp_path: Path) -> None:
        orch = ScanOrchestrator(tmp_path)
        f = _finding()
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [f])],
        ):
            appspec = make_appspec()
            result = orch.run_scan(appspec)
        assert isinstance(result, ScanResult)
        assert len(result.findings) >= 1
        assert result.summary.total_findings >= 1

    def test_filters_by_agent(self, tmp_path: Path) -> None:
        di = _mock_agent(AgentId.DI, [_finding("DI-01")])
        aa = _mock_agent(AgentId.AA, [_finding("AA-01")])
        orch = ScanOrchestrator(tmp_path)
        with patch(
            _AGENTS_PATCH,
            return_value=[di, aa],
        ):
            config = ScanConfig(agents=[AgentId.DI])
            orch.run_scan(make_appspec(), config)
        di.run.assert_called_once()
        aa.run.assert_not_called()

    def test_severity_threshold_filters(self, tmp_path: Path) -> None:
        findings = [
            _finding("DI-01", Severity.CRITICAL),
            _finding("DI-02", Severity.LOW),
            _finding("DI-03", Severity.INFO),
        ]
        orch = ScanOrchestrator(tmp_path)
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, findings)],
        ):
            config = ScanConfig(severity_threshold=Severity.LOW)
            result = orch.run_scan(make_appspec(), config)
        severities = {f.severity for f in result.findings}
        assert Severity.INFO not in severities

    def test_excludes_false_positives_by_default(self, tmp_path: Path) -> None:
        f = _finding(status=FindingStatus.FALSE_POSITIVE)
        orch = ScanOrchestrator(tmp_path)
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [f])],
        ):
            result = orch.run_scan(make_appspec())
        assert len(result.findings) == 0

    def test_include_suppressed(self, tmp_path: Path) -> None:
        f = _finding(status=FindingStatus.FALSE_POSITIVE)
        orch = ScanOrchestrator(tmp_path)
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [f])],
        ):
            config = ScanConfig(include_suppressed=True)
            result = orch.run_scan(make_appspec(), config)
        assert len(result.findings) == 1

    def test_persists_scan_result(self, tmp_path: Path) -> None:
        orch = ScanOrchestrator(tmp_path)
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [_finding()])],
        ):
            orch.run_scan(make_appspec())
        files = list((tmp_path / ".dazzle" / "sentinel").glob("sentinel_*.json"))
        assert len(files) == 1

    def test_measures_duration(self, tmp_path: Path) -> None:
        orch = ScanOrchestrator(tmp_path)
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [])],
        ):
            result = orch.run_scan(make_appspec())
        assert result.duration_ms >= 0


class TestDeduplication:
    def test_preserves_first_detected_from_previous(self, tmp_path: Path) -> None:
        orch = ScanOrchestrator(tmp_path)
        # First scan
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [_finding("DI-01")])],
        ):
            result1 = orch.run_scan(make_appspec())
        first_detected_1 = result1.findings[0].first_detected
        # Second scan — same finding should carry forward first_detected
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [_finding("DI-01")])],
        ):
            result2 = orch.run_scan(make_appspec())
        assert len(result2.findings) == 1
        assert result2.findings[0].first_detected == first_detected_1

    def test_carries_suppression_forward(self, tmp_path: Path) -> None:
        f = _finding("DI-01")
        orch = ScanOrchestrator(tmp_path)
        # First scan, then suppress
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [f])],
        ):
            orch.run_scan(make_appspec())
        from dazzle.sentinel.store import FindingStore

        store = FindingStore(tmp_path)
        store.suppress_finding(f.finding_id, "false positive")
        # Second scan — should carry forward suppression
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [_finding("DI-01")])],
        ):
            config = ScanConfig(include_suppressed=True)
            result2 = orch.run_scan(make_appspec(), config)
        suppressed = [f for f in result2.findings if f.status == FindingStatus.FALSE_POSITIVE]
        assert len(suppressed) == 1


class TestSummary:
    def test_counts_by_severity(self, tmp_path: Path) -> None:
        findings = [
            _finding("DI-01", Severity.HIGH),
            _finding("DI-02", Severity.HIGH),
            _finding("DI-03", Severity.LOW),
        ]
        orch = ScanOrchestrator(tmp_path)
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, findings)],
        ):
            result = orch.run_scan(make_appspec())
        assert result.summary.by_severity.get("high") == 2
        assert result.summary.by_severity.get("low") == 1

    def test_counts_by_agent(self, tmp_path: Path) -> None:
        di_findings = [_finding("DI-01")]
        aa_finding = Finding(
            agent=AgentId.AA,
            heuristic_id="AA-01",
            category="auth",
            subcategory="access",
            severity=Severity.HIGH,
            title="t",
            description="d",
        )
        di_agent = _mock_agent(AgentId.DI, di_findings)
        aa_agent = _mock_agent(AgentId.AA, [aa_finding])
        orch = ScanOrchestrator(tmp_path)
        with patch(
            _AGENTS_PATCH,
            return_value=[di_agent, aa_agent],
        ):
            result = orch.run_scan(make_appspec())
        assert result.summary.by_agent.get("DI") == 1
        assert result.summary.by_agent.get("AA") == 1

    def test_counts_resolved(self, tmp_path: Path) -> None:
        orch = ScanOrchestrator(tmp_path)
        # First scan: 2 findings
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [_finding("DI-01"), _finding("DI-02")])],
        ):
            orch.run_scan(make_appspec())
        # Second scan: only 1 finding (DI-02 resolved)
        with patch(
            _AGENTS_PATCH,
            return_value=[_mock_agent(AgentId.DI, [_finding("DI-01")])],
        ):
            result = orch.run_scan(make_appspec())
        assert result.summary.resolved == 1
