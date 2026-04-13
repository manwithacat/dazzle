"""Tests for build_case_file and CaseFile dataclasses."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dazzle.fitness.backlog import upsert_findings
from dazzle.fitness.investigator.case_file import (
    CaseFileBuildError,
    CaseFileTraversalError,
    build_case_file,
)
from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.triage import Cluster


def _finding(
    fid: str,
    *,
    persona: str = "admin",
    summary_observed: str = "aria-describedby missing",
    evidence_text: str = "src/dazzle_ui/templates/form.html:47 — control has no describedby",
) -> Finding:
    return Finding(
        id=fid,
        created=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
        run_id="run-1",
        cycle=None,
        axis="coverage",
        locus="implementation",
        severity="high",
        persona=persona,
        capability_ref="Ticket.create",
        expected="error announced via aria-describedby",
        observed=summary_observed,
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={"step": 1, "description": "check aria"},
            diff_summary=[],
            transcript_excerpt=[{"kind": "observe", "text": evidence_text}],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )


def _cluster(sample_id: str = "f_001", cluster_size: int = 3) -> Cluster:
    return Cluster(
        cluster_id="CL-deadbeef",
        locus="implementation",  # enum kind, not a file path
        axis="coverage",
        canonical_summary="aria-describedby missing",
        persona="admin",
        severity="high",
        cluster_size=cluster_size,
        first_seen=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
        last_seen=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
        sample_id=sample_id,
    )


def test_build_case_file_happy_path(tmp_path: Path) -> None:
    """Evidence text contains a file path; builder extracts + loads it as locus."""
    (tmp_path / "dev_docs").mkdir()
    backlog_path = tmp_path / "dev_docs" / "fitness-backlog.md"
    upsert_findings(
        backlog_path,
        [
            _finding("f_001", summary_observed="describedby missing on control"),
            _finding("f_002", summary_observed="describedby missing (variant 2)"),
        ],
    )

    locus_dir = tmp_path / "src" / "dazzle_ui" / "templates"
    locus_dir.mkdir(parents=True)
    locus_file = locus_dir / "form.html"
    locus_file.write_text("\n".join(f"<div>line {i}</div>" for i in range(1, 21)))

    case_file = build_case_file(_cluster(), tmp_path)

    assert case_file.cluster.cluster_id == "CL-deadbeef"
    assert case_file.sample_finding.id == "f_001"
    assert case_file.locus is not None
    assert case_file.locus.file_path == "src/dazzle_ui/templates/form.html"
    assert case_file.locus.mode == "full"
    assert case_file.locus.total_lines == 20
    assert case_file.dazzle_root == tmp_path


def test_build_case_file_missing_sample(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    (tmp_path / "dev_docs" / "fitness-backlog.md").write_text("# empty\n")

    with pytest.raises(CaseFileBuildError, match="sample"):
        build_case_file(_cluster(), tmp_path)


def test_build_case_file_no_file_path_in_evidence_yields_none_locus(tmp_path: Path) -> None:
    """When evidence contains no file path, CaseFile.locus is None — not an error."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="something went wrong but no file path here")],
    )
    case_file = build_case_file(_cluster(), tmp_path)
    assert case_file.locus is None


def test_build_case_file_extracted_file_missing_yields_none_locus(tmp_path: Path) -> None:
    """When evidence points at a file that doesn't exist on disk, locus is None."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="src/does/not/exist.html:10 — missing")],
    )
    case_file = build_case_file(_cluster(), tmp_path)
    assert case_file.locus is None


def test_build_case_file_traversal_guard(tmp_path: Path) -> None:
    """When evidence points at a file outside dazzle_root, raise CaseFileTraversalError."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="../../etc/passwd:1 — escaped")],
    )
    with pytest.raises(CaseFileTraversalError):
        build_case_file(_cluster(), tmp_path)


def test_build_case_file_example_root_detection(tmp_path: Path) -> None:
    """When extracted file path starts with examples/<name>/, example_root is set."""
    example_dir = tmp_path / "examples" / "support_tickets" / "dev_docs"
    example_dir.mkdir(parents=True)
    upsert_findings(
        example_dir / "fitness-backlog.md",
        [
            _finding(
                "f_001",
                evidence_text="examples/support_tickets/dsl/entities/ticket.dsl:5 — entity issue",
            )
        ],
    )
    locus_file = tmp_path / "examples" / "support_tickets" / "dsl" / "entities" / "ticket.dsl"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("entity Ticket: id uuid pk\n")

    case_file = build_case_file(_cluster(), tmp_path)
    assert case_file.example_root == tmp_path / "examples" / "support_tickets"
    assert case_file.locus is not None
    assert case_file.locus.file_path == "examples/support_tickets/dsl/entities/ticket.dsl"
    assert case_file.sample_finding.id == "f_001"
