"""Tests for the fitness backlog reader/writer (v1 task 15)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dazzle.fitness.backlog import read_backlog, upsert_findings
from dazzle.fitness.models import EvidenceEmbedded, Finding, RowChange


def _finding(id_: str, locus: str = "lifecycle") -> Finding:
    return Finding(
        id=id_,
        created=datetime(2026, 4, 13, tzinfo=UTC),
        run_id="r1",
        cycle=None,
        axis="conformance",
        locus=locus,  # type: ignore[arg-type]
        severity="high",
        persona="support_agent",
        capability_ref="entity:Ticket/t1",
        expected="x",
        observed="y",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={},
            diff_summary=[
                RowChange(
                    table="ticket",
                    row_id="t1",
                    kind="update",
                    semantic_repr="Ticket(status=resolved)",
                    field_deltas={"status": ("open", "resolved")},
                )
            ],
            transcript_excerpt=[],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="hard",
        fix_commit=None,
        alternative_fix=None,
    )


def test_upsert_creates_backlog_file(tmp_path: Path) -> None:
    path = tmp_path / "fitness-backlog.md"
    upsert_findings(path, [_finding("FIND-001")])

    assert path.exists()
    text = path.read_text()
    assert "FIND-001" in text
    assert "lifecycle" in text


def test_upsert_is_idempotent_on_same_id(tmp_path: Path) -> None:
    path = tmp_path / "fitness-backlog.md"
    upsert_findings(path, [_finding("FIND-002")])
    upsert_findings(path, [_finding("FIND-002")])

    rows = read_backlog(path)
    matching = [r for r in rows if r["id"] == "FIND-002"]
    assert len(matching) == 1


def test_read_backlog_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "fitness-backlog.md"
    upsert_findings(path, [_finding("FIND-003"), _finding("FIND-004", locus="spec_stale")])
    rows = read_backlog(path)
    ids = {r["id"] for r in rows}
    assert ids == {"FIND-003", "FIND-004"}
