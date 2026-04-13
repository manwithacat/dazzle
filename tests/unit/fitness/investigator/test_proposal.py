"""Tests for Proposal and ProposedFix dataclasses."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dazzle.fitness.investigator.proposal import (
    Proposal,
    ProposalParseError,
    ProposalValidationError,
    ProposalWriteError,
    ProposedFix,
    load_proposal,
    save_proposal,
    write_blocked_artefact,
)


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


def _valid_proposal(
    cluster_id: str = "CL-deadbeef", proposal_id: str = "abc12345ef678901"
) -> Proposal:
    return Proposal(
        proposal_id=proposal_id,
        cluster_id=cluster_id,
        created=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
        investigator_run_id="run-1",
        fixes=(
            ProposedFix(
                file_path="src/foo.py",
                line_range=(10, 15),
                diff="--- a/src/foo.py\n+++ b/src/foo.py\n@@ -10,1 +10,1 @@\n-old\n+new\n",
                rationale="add the missing thing",
                confidence=0.85,
            ),
        ),
        overall_confidence=0.82,
        rationale="A sufficiently long rationale that passes the 20-character minimum check.",
        alternatives_considered=("option A — rejected because X",),
        verification_plan="Re-run Phase B against support_tickets; expect cluster to disappear.",
        evidence_paths=("src/foo.py",),
        tool_calls_summary=("read_file(src/foo.py)", "propose_fix(1 fixes)"),
        status="proposed",
    )


def test_save_proposal_happy_path(tmp_path: Path) -> None:
    proposal = _valid_proposal()
    path = save_proposal(
        proposal,
        tmp_path,
        case_file_text="# Case File\n\n(example)\n",
        investigation_log="Looked at src/foo.py; found the missing attribute.\n",
    )
    assert path.exists()
    assert path.name == f"{proposal.cluster_id}-{proposal.proposal_id[:8]}.md"
    assert path.parent == tmp_path / ".dazzle" / "fitness-proposals"

    loaded = load_proposal(path)
    assert loaded.cluster_id == proposal.cluster_id
    assert loaded.proposal_id == proposal.proposal_id
    assert loaded.overall_confidence == 0.82
    assert loaded.status == "proposed"
    assert len(loaded.fixes) == 1
    assert loaded.fixes[0].file_path == "src/foo.py"


def test_save_proposal_rejects_empty_fixes(tmp_path: Path) -> None:
    p = _valid_proposal()
    empty = Proposal(**{**p.__dict__, "fixes": ()})
    with pytest.raises(ProposalValidationError, match="fixes"):
        save_proposal(empty, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_short_rationale(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad = Proposal(**{**p.__dict__, "rationale": "too short"})
    with pytest.raises(ProposalValidationError, match="rationale"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_short_verification_plan(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad = Proposal(**{**p.__dict__, "verification_plan": "nope"})
    with pytest.raises(ProposalValidationError, match="verification_plan"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_out_of_range_confidence(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad = Proposal(**{**p.__dict__, "overall_confidence": 1.5})
    with pytest.raises(ProposalValidationError, match="confidence"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_bad_cluster_id(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad = Proposal(**{**p.__dict__, "cluster_id": "not-a-cluster-id"})
    with pytest.raises(ProposalValidationError, match="cluster_id"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_diff_path_mismatch(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad_fix = ProposedFix(
        file_path="src/foo.py",
        line_range=(10, 15),
        diff="--- a/src/bar.py\n+++ b/src/bar.py\n",  # wrong path
        rationale="whatever",
        confidence=0.8,
    )
    bad = Proposal(**{**p.__dict__, "fixes": (bad_fix,)})
    with pytest.raises(ProposalValidationError, match="diff"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_too_many_alternatives(tmp_path: Path) -> None:
    p = _valid_proposal()
    too_many = tuple(f"alt {i}" for i in range(6))
    bad = Proposal(**{**p.__dict__, "alternatives_considered": too_many})
    with pytest.raises(ProposalValidationError, match="alternatives"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_traversal_fix_path(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad_fix = ProposedFix(
        file_path="../../etc/passwd",
        line_range=None,
        diff="--- a/../../etc/passwd\n+++ b/../../etc/passwd\n",
        rationale="no",
        confidence=0.1,
    )
    bad = Proposal(**{**p.__dict__, "fixes": (bad_fix,)})
    with pytest.raises(ProposalValidationError, match="traversal|escape"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_collision_raises(tmp_path: Path) -> None:
    p = _valid_proposal()
    save_proposal(p, tmp_path, case_file_text="", investigation_log="")
    with pytest.raises(ProposalWriteError, match="already exists"):
        save_proposal(p, tmp_path, case_file_text="", investigation_log="")


def test_write_blocked_artefact(tmp_path: Path) -> None:
    path = write_blocked_artefact(
        cluster_id="CL-abcdef12",
        dazzle_root=tmp_path,
        reason="step_cap",
        case_file_text="# Case File\n(example)\n",
        transcript="step 1 ... step 25",
    )
    assert path.exists()
    assert path.name == "CL-abcdef12.md"
    assert path.parent == tmp_path / ".dazzle" / "fitness-proposals" / "_blocked"
    content = path.read_text()
    assert "step_cap" in content
    assert "# Case File" in content


def test_load_proposal_malformed_frontmatter(tmp_path: Path) -> None:
    proposals_dir = tmp_path / ".dazzle" / "fitness-proposals"
    proposals_dir.mkdir(parents=True)
    bad = proposals_dir / "CL-deadbeef-12345678.md"
    bad.write_text("no frontmatter here\n")
    with pytest.raises(ProposalParseError):
        load_proposal(bad)
