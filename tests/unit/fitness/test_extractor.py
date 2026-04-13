"""Tests for the extractor — diffs to self-contained Findings (v1 task 14)."""

from __future__ import annotations

from datetime import UTC, datetime

from dazzle.fitness.extractor import extract_findings_from_diff
from dazzle.fitness.models import (
    FitnessDiff,
    LedgerStep,
    ProgressRecord,
    RowChange,
)


def _step(n: int, expect: str) -> LedgerStep:
    return LedgerStep(
        step_no=n,
        txn_id=None,
        expected=expect,
        action_summary=f"action {n}",
        observed_ui=f"ui {n}",
        observed_changes=[],
        delta={},
    )


def test_motion_without_progress_emits_lifecycle_finding() -> None:
    diff = FitnessDiff(
        run_id="r1",
        steps=[_step(1, "status advances")],
        created=[],
        updated=[
            RowChange(
                table="ticket",
                row_id="t1",
                kind="update",
                semantic_repr="Ticket(status=resolved)",
                field_deltas={"status": ("in_progress", "resolved")},
            )
        ],
        deleted=[],
        progress=[
            ProgressRecord(
                entity="Ticket",
                row_id="t1",
                transitions_observed=[("in_progress", "resolved")],
                evidence_satisfied=[False],
                ended_at_state="resolved",
                was_progress=False,
            )
        ],
        semantic_repr_config={},
    )
    findings = extract_findings_from_diff(
        diff,
        run_id="r1",
        persona="support_agent",
        low_confidence=False,
        now=datetime(2026, 4, 13, tzinfo=UTC),
    )
    lifecycle = [f for f in findings if f.locus == "lifecycle"]
    assert len(lifecycle) == 1
    assert lifecycle[0].axis == "conformance"
    assert lifecycle[0].severity == "high"
    assert "t1" in lifecycle[0].observed
    # Evidence is embedded for durability after ledger TTL
    assert lifecycle[0].evidence_embedded.diff_summary


def test_clean_run_emits_no_findings() -> None:
    diff = FitnessDiff(
        run_id="r",
        steps=[_step(1, "ok")],
        created=[],
        updated=[],
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    findings = extract_findings_from_diff(
        diff,
        run_id="r",
        persona="agent",
        low_confidence=False,
        now=datetime(2026, 4, 13, tzinfo=UTC),
    )
    assert findings == []


def test_low_confidence_flag_propagates() -> None:
    diff = FitnessDiff(
        run_id="r",
        steps=[_step(1, "status advances")],
        created=[],
        updated=[
            RowChange(
                table="ticket",
                row_id="t1",
                kind="update",
                semantic_repr="",
                field_deltas={"status": ("in_progress", "resolved")},
            )
        ],
        deleted=[],
        progress=[
            ProgressRecord(
                entity="Ticket",
                row_id="t1",
                transitions_observed=[("in_progress", "resolved")],
                evidence_satisfied=[False],
                ended_at_state="resolved",
                was_progress=False,
            )
        ],
        semantic_repr_config={},
    )
    findings = extract_findings_from_diff(
        diff,
        run_id="r",
        persona="agent",
        low_confidence=True,
        now=datetime(2026, 4, 13, tzinfo=UTC),
    )
    assert all(f.low_confidence for f in findings)
