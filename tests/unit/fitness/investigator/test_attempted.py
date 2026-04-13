"""Tests for AttemptedIndex — the rebuildable idempotence cache."""

from datetime import UTC, datetime
from pathlib import Path

from dazzle.fitness.investigator.attempted import (
    AttemptedEntry,
    AttemptedIndex,
    load_attempted,
    mark_attempted,
    rebuild_attempted,
    save_attempted,
)
from dazzle.fitness.investigator.proposal import (
    Proposal,
    ProposedFix,
    save_proposal,
    write_blocked_artefact,
)


def _proposal(cluster_id: str = "CL-deadbeef", proposal_id: str = "abc12345ef678901") -> Proposal:
    return Proposal(
        proposal_id=proposal_id,
        cluster_id=cluster_id,
        created=datetime(2026, 4, 14, tzinfo=UTC),
        investigator_run_id="run-1",
        fixes=(
            ProposedFix(
                file_path="src/foo.py",
                line_range=(1, 2),
                diff="--- a/src/foo.py\n+++ b/src/foo.py\n",
                rationale="y",
                confidence=0.9,
            ),
        ),
        overall_confidence=0.9,
        rationale="A sufficiently long rationale for validation purposes here.",
        alternatives_considered=(),
        verification_plan="Re-run Phase B and look for cluster disappearance.",
        evidence_paths=(),
        tool_calls_summary=(),
        status="proposed",
    )


def test_load_attempted_missing_file_rebuilds_from_disk(tmp_path: Path) -> None:
    save_proposal(_proposal(), tmp_path, case_file_text="", investigation_log="")

    index = load_attempted(tmp_path)
    assert "CL-deadbeef" in index.clusters
    assert index.clusters["CL-deadbeef"].status == "proposed"
    assert "abc12345ef678901" in index.clusters["CL-deadbeef"].proposal_ids


def test_mark_attempted_updates_entry(tmp_path: Path) -> None:
    index = AttemptedIndex(clusters={})
    mark_attempted(index, "CL-cafef00d", proposal_id="deadbeef11112222", status="proposed")
    assert index.clusters["CL-cafef00d"].proposal_ids == ["deadbeef11112222"]
    assert index.clusters["CL-cafef00d"].status == "proposed"


def test_save_load_round_trip(tmp_path: Path) -> None:
    index = AttemptedIndex(
        clusters={
            "CL-11112222": AttemptedEntry(
                proposal_ids=["p1"],
                last_attempt=datetime(2026, 4, 14, tzinfo=UTC),
                status="proposed",
            ),
        }
    )
    save_attempted(index, tmp_path)

    reloaded = load_attempted(tmp_path)
    assert "CL-11112222" in reloaded.clusters
    assert reloaded.clusters["CL-11112222"].status == "proposed"


def test_rebuild_from_blocked_artefact(tmp_path: Path) -> None:
    write_blocked_artefact(
        "CL-33334444",
        tmp_path,
        reason="step_cap",
        case_file_text="",
        transcript="",
    )
    index = rebuild_attempted(tmp_path)
    assert "CL-33334444" in index.clusters
    assert index.clusters["CL-33334444"].status == "blocked"


def test_rebuild_proposal_wins_over_blocked(tmp_path: Path) -> None:
    """When both a proposal and a blocked artefact exist for the same cluster,
    the proposal's status wins — the blocked artefact is treated as stale history."""
    save_proposal(_proposal(), tmp_path, case_file_text="", investigation_log="")
    write_blocked_artefact(
        "CL-deadbeef",
        tmp_path,
        reason="step_cap",
        case_file_text="",
        transcript="",
    )

    index = rebuild_attempted(tmp_path)
    assert index.clusters["CL-deadbeef"].status == "proposed"
    assert "abc12345ef678901" in index.clusters["CL-deadbeef"].proposal_ids


def test_load_attempted_handles_corrupt_index(tmp_path: Path) -> None:
    proposals_dir = tmp_path / ".dazzle" / "fitness-proposals"
    proposals_dir.mkdir(parents=True)
    (proposals_dir / "_attempted.json").write_text("not valid json {")

    # Should silently rebuild from disk
    index = load_attempted(tmp_path)
    assert isinstance(index, AttemptedIndex)
