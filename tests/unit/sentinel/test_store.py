"""Tests for the FindingStore JSON persistence layer."""

from __future__ import annotations

from pathlib import Path

from dazzle.sentinel.models import (
    AgentId,
    AgentResult,
    Finding,
    FindingStatus,
    ScanResult,
    ScanSummary,
    Severity,
)
from dazzle.sentinel.store import FindingStore


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


# =============================================================================
# Tests
# =============================================================================


class TestSaveScan:
    def test_creates_sentinel_directory(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result())
        assert (tmp_path / ".dazzle" / "sentinel").is_dir()

    def test_creates_json_file(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        path = store.save_scan(_scan_result())
        assert path.exists()
        assert path.suffix == ".json"
        assert path.name.startswith("sentinel_")

    def test_multiple_scans_create_multiple_files(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result())
        store.save_scan(_scan_result())
        files = list((tmp_path / ".dazzle" / "sentinel").glob("sentinel_*.json"))
        assert len(files) >= 2


class TestLoadLatestFindings:
    def test_returns_empty_when_no_scans(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        assert store.load_latest_findings() == []

    def test_returns_findings_from_latest(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        f = _finding("DI-99")
        store.save_scan(_scan_result([f]))
        latest = store.load_latest_findings()
        assert len(latest) == 1
        assert latest[0].heuristic_id == "DI-99"


class TestLoadScan:
    def test_returns_none_for_missing_id(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        assert store.load_scan("nonexistent") is None

    def test_returns_scan_by_id(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        result = _scan_result()
        store.save_scan(result)
        loaded = store.load_scan(result.scan_id)
        assert loaded is not None
        assert loaded.scan_id == result.scan_id
        assert len(loaded.findings) == 1


class TestListScans:
    def test_empty(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        assert store.list_scans() == []

    def test_returns_summaries(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result())
        scans = store.list_scans()
        assert len(scans) == 1
        assert "scan_id" in scans[0]
        assert scans[0]["total_findings"] == 1

    def test_respects_limit(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        for _ in range(5):
            store.save_scan(_scan_result())
        assert len(store.list_scans(limit=2)) == 2


class TestSuppressFinding:
    def test_suppresses_by_id(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        f = _finding("DI-01")
        store.save_scan(_scan_result([f]))
        ok = store.suppress_finding(f.finding_id, "false positive")
        assert ok is True
        latest = store.load_latest_findings()
        assert latest[0].status == FindingStatus.FALSE_POSITIVE
        assert latest[0].suppression_reason == "false positive"

    def test_returns_false_for_unknown_finding(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        store.save_scan(_scan_result())
        assert store.suppress_finding("nonexistent", "reason") is False

    def test_returns_false_when_no_scans(self, tmp_path: Path) -> None:
        store = FindingStore(tmp_path)
        assert store.suppress_finding("any", "reason") is False
