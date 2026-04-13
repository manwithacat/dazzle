"""Tests for Proposal and ProposedFix dataclasses."""

from datetime import UTC, datetime

import pytest

from dazzle.fitness.investigator.proposal import Proposal, ProposedFix


def _fix(
    file_path: str = "src/foo.py", diff: str = "--- a/src/foo.py\n+++ b/src/foo.py\n"
) -> ProposedFix:
    return ProposedFix(
        file_path=file_path,
        line_range=(10, 15),
        diff=diff,
        rationale="add the missing attribute",
        confidence=0.8,
    )


def test_proposed_fix_is_frozen() -> None:
    import dataclasses

    f = _fix()
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.confidence = 0.9  # type: ignore[misc]


def test_proposal_construction() -> None:
    p = Proposal(
        proposal_id="abc123",
        cluster_id="CL-deadbeef",
        created=datetime(2026, 4, 14, tzinfo=UTC),
        investigator_run_id="run-1",
        fixes=(_fix(),),
        overall_confidence=0.82,
        rationale="the reason we are doing this fix for real",
        alternatives_considered=("option A — rejected because X",),
        verification_plan="re-run Phase B against support_tickets with admin persona",
        evidence_paths=("src/foo.py",),
        tool_calls_summary=("read_file(src/foo.py)", "propose_fix(1 fixes)"),
        status="proposed",
    )
    assert p.cluster_id == "CL-deadbeef"
    assert p.fixes[0].file_path == "src/foo.py"
    assert p.status == "proposed"
