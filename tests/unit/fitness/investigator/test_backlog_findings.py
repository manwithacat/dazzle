"""Tests for read_backlog_findings — round-trip a Finding through backlog I/O."""

from datetime import UTC, datetime
from pathlib import Path

from dazzle.fitness.backlog import read_backlog_findings, upsert_findings
from dazzle.fitness.models import EvidenceEmbedded, Finding


def _sample_finding(fid: str = "f_001") -> Finding:
    return Finding(
        id=fid,
        created=datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC),
        run_id="run_abc",
        cycle=None,
        axis="coverage",
        locus="implementation",
        severity="high",
        persona="admin",
        capability_ref="Ticket.create",
        expected="error announced via aria-describedby",
        observed="aria-describedby missing on control",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={"step": 1, "description": "check aria-describedby"},
            diff_summary=[],
            transcript_excerpt=[{"kind": "observe", "text": "control has no describedby"}],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )


def test_read_backlog_findings_round_trip(tmp_path: Path) -> None:
    backlog = tmp_path / "fitness-backlog.md"
    original = _sample_finding("f_001")
    upsert_findings(backlog, [original])

    findings = read_backlog_findings(backlog)
    assert len(findings) == 1
    got = findings[0]
    assert got.id == "f_001"
    assert got.axis == "coverage"
    assert got.severity == "high"
    assert got.persona == "admin"
    assert got.expected == "error announced via aria-describedby"
    assert got.observed == "aria-describedby missing on control"
    assert got.evidence_embedded.transcript_excerpt == [
        {"kind": "observe", "text": "control has no describedby"}
    ]
    assert got.created == original.created


def test_read_backlog_findings_missing_file(tmp_path: Path) -> None:
    assert read_backlog_findings(tmp_path / "does-not-exist.md") == []


def test_read_backlog_findings_multiple(tmp_path: Path) -> None:
    backlog = tmp_path / "fitness-backlog.md"
    upsert_findings(backlog, [_sample_finding("f_001"), _sample_finding("f_002")])

    findings = read_backlog_findings(backlog)
    assert sorted(f.id for f in findings) == ["f_001", "f_002"]


def test_read_backlog_findings_round_trip_with_diff_summary(tmp_path: Path) -> None:
    """A Finding with a non-empty diff_summary must round-trip cleanly —
    diff_summary entries should come back as RowChange instances, not raw dicts."""
    from dazzle.fitness.models import RowChange

    backlog = tmp_path / "fitness-backlog.md"

    row_change = RowChange(
        table="tickets",
        row_id="row-42",
        kind="update",
        semantic_repr="tickets/row-42: status=open",
        field_deltas={},
    )
    original = Finding(
        id="f_diff_001",
        created=datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC),
        run_id="run_abc",
        cycle=None,
        axis="coverage",
        locus="implementation",
        severity="medium",
        persona="admin",
        capability_ref="Ticket.update",
        expected="status field updated",
        observed="status unchanged",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={"step": 2, "description": "update status"},
            diff_summary=[row_change],
            transcript_excerpt=[],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )
    upsert_findings(backlog, [original])

    got = read_backlog_findings(backlog)[0]
    assert got.evidence_embedded.diff_summary  # non-empty
    assert isinstance(got.evidence_embedded.diff_summary[0], RowChange)
    rc = got.evidence_embedded.diff_summary[0]
    assert rc.table == "tickets"
    assert rc.row_id == "row-42"
    assert rc.kind == "update"
    assert rc.semantic_repr == "tickets/row-42: status=open"


def test_read_backlog_findings_ignores_table_only_rows(tmp_path: Path) -> None:
    """A row in the table with no matching envelope block should be skipped."""
    backlog = tmp_path / "fitness-backlog.md"
    backlog.write_text(
        "# Fitness Backlog\n\n"
        "| id | created | locus | axis | severity | persona | status | route | summary |\n"
        "|----|---------|-------|------|----------|---------|--------|-------|---------|\n"
        "| f_orphan | 2026-04-14T12:00:00+00:00 | implementation | coverage | high | admin | PROPOSED | soft | some summary |\n"
        "\n## Evidence\n\n"
    )
    assert read_backlog_findings(backlog) == []
