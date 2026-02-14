"""Tests for the MCP sentinel handler."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.mcp.server.handlers.sentinel import (
    findings_handler,
    history_handler,
    scan_handler,
    status_handler,
    suppress_handler,
)
from dazzle.sentinel.models import (
    AgentId,
    AgentResult,
    Finding,
    ScanResult,
    ScanSummary,
    Severity,
)
from dazzle.sentinel.store import FindingStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _finding(heuristic_id: str = "DI-01", severity: Severity = Severity.HIGH) -> Finding:
    return Finding(
        agent=AgentId.DI,
        heuristic_id=heuristic_id,
        category="test",
        subcategory="test",
        severity=severity,
        title=f"Finding {heuristic_id}",
        description="test finding",
        entity_name="Task",
    )


def _scan_result(findings: list[Finding] | None = None) -> ScanResult:
    f = findings or [_finding()]
    return ScanResult(
        findings=f,
        summary=ScanSummary(total_findings=len(f)),
        agent_results=[AgentResult(agent=AgentId.DI, findings=f, heuristics_run=1)],
    )


def _mock_appspec() -> MagicMock:
    from .conftest import make_appspec

    return make_appspec()


# =============================================================================
# scan_handler
# =============================================================================


class TestScanHandler:
    @patch("dazzle.mcp.server.handlers.sentinel._load_appspec")
    @patch("dazzle.sentinel.orchestrator.ScanOrchestrator.run_scan")
    def test_returns_scan_json(
        self, mock_run: MagicMock, mock_load: MagicMock, tmp_path: Path
    ) -> None:
        mock_load.return_value = _mock_appspec()
        mock_run.return_value = _scan_result()
        result = json.loads(scan_handler(tmp_path, {}))
        assert result["status"] == "ok"
        assert "scan_id" in result
        assert "summary" in result

    @patch("dazzle.mcp.server.handlers.sentinel._load_appspec")
    def test_returns_error_on_load_failure(self, mock_load: MagicMock, tmp_path: Path) -> None:
        mock_load.side_effect = Exception("parse error")
        result = json.loads(scan_handler(tmp_path, {}))
        assert "error" in result

    @patch("dazzle.mcp.server.handlers.sentinel._load_appspec")
    @patch("dazzle.sentinel.orchestrator.ScanOrchestrator.run_scan")
    def test_metrics_detail(
        self, mock_run: MagicMock, mock_load: MagicMock, tmp_path: Path
    ) -> None:
        mock_load.return_value = _mock_appspec()
        mock_run.return_value = _scan_result()
        result = json.loads(scan_handler(tmp_path, {"detail": "metrics"}))
        assert "findings" not in result
        assert "summary" in result

    @patch("dazzle.mcp.server.handlers.sentinel._load_appspec")
    @patch("dazzle.sentinel.orchestrator.ScanOrchestrator.run_scan")
    def test_full_detail_includes_agent_results(
        self, mock_run: MagicMock, mock_load: MagicMock, tmp_path: Path
    ) -> None:
        mock_load.return_value = _mock_appspec()
        mock_run.return_value = _scan_result()
        result = json.loads(scan_handler(tmp_path, {"detail": "full"}))
        assert "agent_results" in result
        assert "findings" in result


# =============================================================================
# findings_handler
# =============================================================================


class TestFindingsHandler:
    def test_empty_when_no_scans(self, tmp_path: Path) -> None:
        result = json.loads(findings_handler(tmp_path, {}))
        assert result["findings"] == []
        assert result["count"] == 0

    def test_returns_latest_findings(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result([_finding("DI-01"), _finding("DI-02")]))
        result = json.loads(findings_handler(tmp_path, {}))
        assert result["count"] == 2

    def test_filter_by_agent(self, tmp_path: Path) -> None:
        f_di = _finding("DI-01")
        f_aa = Finding(
            agent=AgentId.AA,
            heuristic_id="AA-01",
            category="auth",
            subcategory="test",
            severity=Severity.HIGH,
            title="aa",
            description="aa",
        )
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result([f_di, f_aa]))
        result = json.loads(findings_handler(tmp_path, {"agent": "DI"}))
        assert result["count"] == 1
        assert result["findings"][0]["heuristic_id"] == "DI-01"

    def test_filter_by_severity(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(
            _scan_result([_finding("DI-01", Severity.HIGH), _finding("DI-02", Severity.LOW)])
        )
        result = json.loads(findings_handler(tmp_path, {"severity": "high"}))
        assert result["count"] == 1

    def test_load_specific_scan(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        sr = _scan_result([_finding("DI-01")])
        store.save_scan(sr)
        result = json.loads(findings_handler(tmp_path, {"scan_id": sr.scan_id}))
        assert result["count"] == 1

    def test_unknown_scan_id(self, tmp_path: Path) -> None:
        result = json.loads(findings_handler(tmp_path, {"scan_id": "nonexistent"}))
        assert "error" in result


# =============================================================================
# suppress_handler
# =============================================================================


class TestSuppressHandler:
    def test_suppresses_finding(self, tmp_path: Path) -> None:
        f = _finding("DI-01")
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result([f]))
        result = json.loads(
            suppress_handler(tmp_path, {"finding_id": f.finding_id, "reason": "false positive"})
        )
        assert result["status"] == "suppressed"

    def test_error_missing_params(self, tmp_path: Path) -> None:
        result = json.loads(suppress_handler(tmp_path, {}))
        assert "error" in result

    def test_error_unknown_finding(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result())
        result = json.loads(suppress_handler(tmp_path, {"finding_id": "unknown", "reason": "test"}))
        assert "error" in result


# =============================================================================
# status_handler
# =============================================================================


class TestStatusHandler:
    def test_returns_agent_list(self, tmp_path: Path) -> None:
        result = json.loads(status_handler(tmp_path, {}))
        assert "agents" in result
        assert len(result["agents"]) >= 4

    def test_no_last_scan(self, tmp_path: Path) -> None:
        result = json.loads(status_handler(tmp_path, {}))
        assert result["last_scan"] is None

    def test_with_previous_scan(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result())
        result = json.loads(status_handler(tmp_path, {}))
        assert result["last_scan"] is not None


# =============================================================================
# history_handler
# =============================================================================


class TestHistoryHandler:
    def test_empty(self, tmp_path: Path) -> None:
        result = json.loads(history_handler(tmp_path, {}))
        assert result["scans"] == []
        assert result["count"] == 0

    def test_returns_scans(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result())
        store.save_scan(_scan_result())
        result = json.loads(history_handler(tmp_path, {}))
        assert result["count"] == 2

    def test_respects_limit(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        for _ in range(5):
            store.save_scan(_scan_result())
        result = json.loads(history_handler(tmp_path, {"limit": 2}))
        assert result["count"] == 2
