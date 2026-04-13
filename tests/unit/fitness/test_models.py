"""Tests for shared fitness dataclasses (Agent-Led Fitness v1 Task 3)."""

from datetime import UTC, datetime

import pytest

from dazzle.fitness.models import (
    EvidenceEmbedded,
    Finding,
    FitnessDiff,
    LedgerStep,
    ProgressRecord,
    RowChange,
)


def test_ledger_step_requires_expect() -> None:
    with pytest.raises(ValueError, match="expect"):
        LedgerStep(
            step_no=1,
            txn_id=None,
            expected="",
            action_summary="click button",
            observed_ui="ok",
            observed_changes=[],
            delta={},
        )


def test_ledger_step_happy_path() -> None:
    step = LedgerStep(
        step_no=1,
        txn_id=None,
        expected="a new ticket exists",
        action_summary="click create",
        observed_ui="Ticket saved",
        observed_changes=[],
        delta={},
    )
    assert step.step_no == 1
    assert step.expected == "a new ticket exists"


def test_row_change_with_semantic_repr() -> None:
    rc = RowChange(
        table="ticket",
        row_id="ab12",
        kind="insert",
        semantic_repr="Ticket(title=Bug, status=new, assignee=alice)",
        field_deltas={"status": (None, "new")},
    )
    assert rc.kind == "insert"
    assert rc.semantic_repr == "Ticket(title=Bug, status=new, assignee=alice)"
    assert rc.field_deltas == {"status": (None, "new")}


def test_finding_serialisation_roundtrip() -> None:
    f = Finding(
        id="FIND-001",
        created=datetime(2026, 4, 13, tzinfo=UTC),
        run_id="run-abc",
        cycle=None,
        axis="conformance",
        locus="implementation",
        severity="high",
        persona="support_agent",
        capability_ref="story:resolve_ticket",
        expected="ticket.status becomes resolved",
        observed="ticket.status unchanged",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={"expect": "x", "action": "y", "observed": "z"},
            diff_summary=[],
            transcript_excerpt=[],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="hard",
        fix_commit=None,
        alternative_fix=None,
    )
    assert f.axis == "conformance"
    assert f.evidence_embedded.expected_ledger_step["expect"] == "x"


def test_fitness_diff_aggregates() -> None:
    diff = FitnessDiff(
        run_id="r1",
        steps=[],
        created=[],
        updated=[],
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    assert diff.run_id == "r1"
    # Progress records should be storable
    pr = ProgressRecord(
        entity="Ticket",
        row_id="row-1",
        transitions_observed=[("new", "in_progress")],
        evidence_satisfied=[True],
        ended_at_state="in_progress",
        was_progress=True,
    )
    diff2 = FitnessDiff(
        run_id="r2",
        steps=[],
        created=[],
        updated=[],
        deleted=[],
        progress=[pr],
        semantic_repr_config={"ticket": ["title", "status"]},
    )
    assert diff2.progress[0].entity == "Ticket"
    assert diff2.semantic_repr_config == {"ticket": ["title", "status"]}
