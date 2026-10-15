"""Tests for the FindingStore JSON persistence layer."""

from pathlib import Path

import pytest

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


def _finding(heuristic_id: str = "DI-01") -> Finding:
    return Finding(
        agent=AgentId.DI,
        heuristic_id=heuristic_id,
        category="test",
        subcategory="test",
        severity=Severity.HIGH,
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


def test_empty_store_reads_as_empty(tmp_path: Path) -> None:
    store = FindingStore(tmp_path)
    assert store.load_latest_findings() == []
    assert store.load_scan("nonexistent") is None
    assert store.list_scans() == []
    assert store.suppress_finding("any", "reason") is False


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    store = FindingStore(tmp_path)
    older = _scan_result([_finding("DI-01")])
    newer = _scan_result([_finding("DI-99")])
    older_path = store.save_scan(older)
    newer_path = store.save_scan(newer)

    # One sentinel_*.json file per scan under .dazzle/sentinel.
    sentinel_dir = tmp_path / ".dazzle" / "sentinel"
    assert {older_path, newer_path} == set(sentinel_dir.glob("sentinel_*.json"))

    # Filenames carry whole-second timestamps, so two scans in one second do
    # not order reliably; "latest" is only asserted with a single scan below.
    for scan, ids in ((older, ["DI-01"]), (newer, ["DI-99"])):
        loaded = store.load_scan(scan.scan_id)
        assert loaded is not None
        assert [f.heuristic_id for f in loaded.findings] == ids


def test_latest_findings_come_from_the_saved_scan(tmp_path: Path) -> None:
    store = FindingStore(tmp_path)
    store.save_scan(_scan_result([_finding("DI-99")]))
    assert [f.heuristic_id for f in store.load_latest_findings()] == ["DI-99"]


@pytest.mark.parametrize(("n_scans", "limit", "count"), [(1, 10, 1), (5, 2, 2)])
def test_list_scans_summarises_within_limit(
    tmp_path: Path, n_scans: int, limit: int, count: int
) -> None:
    store = FindingStore(tmp_path)
    scans = [_scan_result() for _ in range(n_scans)]
    paths = [store.save_scan(s) for s in scans]
    listed = store.list_scans(limit=limit)
    assert len(listed) == count
    by_id = {s.scan_id: p.name for s, p in zip(scans, paths, strict=True)}
    for summary in listed:
        assert summary["file"] == by_id[summary["scan_id"]]
        assert summary["total_findings"] == 1


def test_suppress_marks_latest_finding_false_positive(tmp_path: Path) -> None:
    store = FindingStore(tmp_path)
    f = _finding("DI-01")
    store.save_scan(_scan_result([f]))
    assert store.suppress_finding("nonexistent", "reason") is False
    assert store.suppress_finding(f.finding_id, "false positive") is True
    (latest,) = store.load_latest_findings()
    assert latest.status == FindingStatus.SUPPRESSED
    assert latest.suppression_reason == "false positive"
