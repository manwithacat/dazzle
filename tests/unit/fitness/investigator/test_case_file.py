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
from dazzle.fitness.triage import Cluster, canonicalize_summary


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


def test_build_case_file_picks_siblings_matching_cluster(tmp_path: Path) -> None:
    """Siblings in the same cluster (same locus/axis/persona + canonical_summary) are returned."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [
            # Sample with a file path in evidence so build_case_file can locate the locus
            _finding(
                "f_001",
                summary_observed="aria-describedby missing",
                evidence_text="src/dazzle_ui/templates/form.html:47 — control has no describedby",
            ),
            # Sibling that canonicalises to the same summary
            _finding(
                "f_002",
                summary_observed="Aria-describedby missing",  # case variation
                evidence_text="src/dazzle_ui/templates/form.html:64 — label missing",
            ),
            # Non-sibling: different canonical summary
            _finding(
                "f_003",
                summary_observed="completely different issue",
                evidence_text="src/dazzle_ui/templates/form.html:100 — other",
            ),
        ],
    )
    locus_dir = tmp_path / "src" / "dazzle_ui" / "templates"
    locus_dir.mkdir(parents=True)
    (locus_dir / "form.html").write_text("\n".join(f"<div>line {i}</div>" for i in range(1, 21)))

    case_file = build_case_file(_cluster(), tmp_path)
    assert case_file.sample_finding.id == "f_001"
    sibling_ids = [s.id for s in case_file.siblings]
    assert "f_002" in sibling_ids
    assert "f_003" not in sibling_ids  # different summary, not in cluster
    assert len(case_file.siblings) == 1


def test_build_case_file_empty_locus_file(tmp_path: Path) -> None:
    """Empty locus file produces a LocusExcerpt with empty chunks tuple."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="src/empty.py:1 — nothing")],
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "empty.py").write_text("")

    case_file = build_case_file(_cluster(), tmp_path)
    assert case_file.locus is not None
    assert case_file.locus.total_lines == 0
    assert case_file.locus.chunks == ()


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


def test_sibling_picker_prefers_diverse_observed_text(tmp_path: Path) -> None:
    """When the pool exceeds SIBLING_LIMIT, the Levenshtein picker prefers
    observed-text variation over pure sort order.

    Fixture: 6 siblings where f_001/f_002/f_003 have near-identical ``observed``
    strings and f_004/f_005/f_006 have genuinely distinct ``observed`` strings.
    The picker should prefer the distinct variants over the near-duplicates.
    All 6 canonicalise to the same cluster summary thanks to the 120-char
    truncation in canonicalize_summary.
    """
    # LONG_PREFIX is 121 chars. canonicalize_summary truncates to 120 chars, so
    # every variant (LONG_PREFIX + <any tail>) maps to the same canonical summary.
    LONG_PREFIX = (
        "aria-describedby missing on form control with multi-step stage "
        "validation and HTMX 422 error swap after client-side guard"
    )
    assert len(LONG_PREFIX) >= 120, "prefix must exceed truncation threshold"

    # All 7 findings share the same canonical summary (verified by construction).
    findings = [
        _finding("f_000", summary_observed=LONG_PREFIX + " SAMPLE"),
        # Near-duplicates: identical observed tails across f_001..f_003
        _finding("f_001", summary_observed=LONG_PREFIX + " near"),
        _finding("f_002", summary_observed=LONG_PREFIX + " near"),
        _finding("f_003", summary_observed=LONG_PREFIX + " near"),
        # Distinct: each has a unique tail adding ~20 chars of Levenshtein distance
        _finding("f_004", summary_observed=LONG_PREFIX + " distinct-variant-alpha"),
        _finding("f_005", summary_observed=LONG_PREFIX + " distinct-variant-beta"),
        _finding("f_006", summary_observed=LONG_PREFIX + " distinct-variant-gamma"),
    ]

    # Sanity-check: all observed values canonicalise to the same 120-char string.
    expected_canonical = canonicalize_summary(LONG_PREFIX)
    assert len(expected_canonical) == 120
    for f in findings:
        assert canonicalize_summary(f.observed) == expected_canonical, (
            f"{f.id}: observed {f.observed!r} canonicalises to "
            f"{canonicalize_summary(f.observed)!r}, expected {expected_canonical!r}"
        )

    (tmp_path / "dev_docs").mkdir()
    upsert_findings(tmp_path / "dev_docs" / "fitness-backlog.md", findings)

    locus_dir = tmp_path / "src" / "dazzle_ui" / "templates"
    locus_dir.mkdir(parents=True)
    (locus_dir / "form.html").write_text("<div>form</div>\n")

    # Build an explicit cluster with the computed canonical summary so the pool
    # filter matches all 6 siblings (not the short "aria-describedby missing" used
    # elsewhere in this test module).
    cluster = Cluster(
        cluster_id="CL-deadbeef",
        locus="implementation",
        axis="coverage",
        canonical_summary=expected_canonical,
        persona="admin",
        severity="high",
        cluster_size=7,
        first_seen=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
        last_seen=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
        sample_id="f_000",
    )

    case_file = build_case_file(cluster, tmp_path)

    sibling_ids = [s.id for s in case_file.siblings]
    assert len(sibling_ids) == 5, f"expected 5 siblings, got {sibling_ids}"

    # The near-duplicates f_001/f_002/f_003 have identical observed text —
    # they contribute zero additional diversity after the first is picked.
    # The distinct variants f_004/f_005/f_006 each add real Levenshtein distance.
    # The picker should therefore select all 3 distinct variants before
    # exhausting the near-duplicate budget.
    distinct_picked = {sid for sid in sibling_ids if sid in {"f_004", "f_005", "f_006"}}
    near_dup_picked = {sid for sid in sibling_ids if sid in {"f_001", "f_002", "f_003"}}
    assert len(distinct_picked) == 3, (
        f"expected all 3 distinct variants picked, got {distinct_picked}"
    )
    # 5 total - 3 distinct = exactly 2 near-duplicate slots
    assert len(near_dup_picked) == 2, (
        f"expected exactly 2 near-duplicates picked, got {near_dup_picked}"
    )


def test_locus_windowing_large_file_with_evidence_lines(tmp_path: Path) -> None:
    """A large file (>500 lines) produces a windowed excerpt containing the
    first 200 lines plus ±20 windows around evidence-referenced line numbers."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="src/ui/large.html:750 — missing describedby")],
    )

    locus_file = tmp_path / "src" / "ui" / "large.html"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("\n".join(f"line {i}" for i in range(1, 1001)))

    case_file = build_case_file(_cluster(sample_id="f_001"), tmp_path)

    assert case_file.locus is not None
    assert case_file.locus.mode == "windowed"
    assert case_file.locus.total_lines == 1000

    # First chunk is the head
    head_chunk = case_file.locus.chunks[0]
    assert head_chunk[0] == 1
    assert head_chunk[1] == 200

    # Second chunk should cover a window around line 750
    window_chunks = [c for c in case_file.locus.chunks if c[0] > 200]
    assert window_chunks, "expected at least one evidence window beyond the head"
    assert any(c[0] <= 750 <= c[1] for c in window_chunks)


def test_locus_windowing_merges_overlapping_windows(tmp_path: Path) -> None:
    """Two evidence line numbers within ±20 of each other merge into one chunk."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [
            _finding(
                "f_001",
                summary_observed="aria-describedby missing",
                evidence_text="src/ui/large.html:750 here",
            ),
            _finding(
                "f_002",
                summary_observed="aria-describedby missing",
                evidence_text="src/ui/large.html:755 and here",
            ),
        ],
    )

    locus_file = tmp_path / "src" / "ui" / "large.html"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("\n".join(f"line {i}" for i in range(1, 1001)))

    case_file = build_case_file(_cluster(sample_id="f_001"), tmp_path)
    assert case_file.locus is not None

    # Head + one merged window = 2 chunks
    windows = [c for c in case_file.locus.chunks if c[0] > 200]
    assert len(windows) == 1
    assert windows[0][0] <= 750 <= windows[0][1]
    assert windows[0][0] <= 755 <= windows[0][1]


def test_locus_windowing_evidence_only_in_head_region(tmp_path: Path) -> None:
    """Evidence referencing a line inside the head (1-200) on a large file
    produces a windowed excerpt with only the head chunk — no duplicate window."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="src/ui/large.html:50 — in head")],
    )
    locus_file = tmp_path / "src" / "ui" / "large.html"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("\n".join(f"line {i}" for i in range(1, 1001)))

    case_file = build_case_file(_cluster(sample_id="f_001"), tmp_path)
    assert case_file.locus is not None
    assert case_file.locus.mode == "windowed"
    assert len(case_file.locus.chunks) == 1  # head only
    assert case_file.locus.chunks[0][0] == 1
    assert case_file.locus.chunks[0][1] == 200


def test_locus_windowing_no_evidence_lines(tmp_path: Path) -> None:
    """A large file with no evidence line references produces just the head chunk."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [
            _finding(
                "f_001",
                evidence_text="src/ui/large.html — no line number here (just the filename)",
            )
        ],
    )
    locus_file = tmp_path / "src" / "ui" / "large.html"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("\n".join(f"line {i}" for i in range(1, 1001)))

    case_file = build_case_file(_cluster(sample_id="f_001"), tmp_path)
    assert case_file.locus is not None
    assert case_file.locus.mode == "windowed"
    assert len(case_file.locus.chunks) == 1  # head only, no evidence windows


def test_to_prompt_text_structure(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [
            _finding(
                "f_001",
                summary_observed="describedby missing on control",
                evidence_text="src/ui/form.html:1 — missing",
            ),
        ],
    )
    locus_dir = tmp_path / "src" / "ui"
    locus_dir.mkdir(parents=True)
    (locus_dir / "form.html").write_text("<div>hello</div>\n<div>world</div>\n")

    case_file = build_case_file(_cluster(), tmp_path)
    text = case_file.to_prompt_text()

    # Section headers
    assert "# Case File" in text
    assert "## Cluster" in text
    assert "## Sample Finding" in text
    assert "## Locus File" in text

    # Cluster fields
    assert "CL-deadbeef" in text
    assert "src/ui/form.html" in text
    assert "persona: admin" in text
    assert "severity: high" in text

    # Sample finding shape
    assert "f_001" in text
    assert "describedby missing on control" in text

    # Locus content with line-number prefixes
    assert "  1: <div>hello</div>" in text
    assert "  2: <div>world</div>" in text


def test_to_prompt_text_locus_none_shows_note(tmp_path: Path) -> None:
    """When locus is None (file not found or no path extracted), show a note."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="no file path here just text")],
    )
    case_file = build_case_file(_cluster(), tmp_path)
    assert case_file.locus is None  # no file path in evidence

    text = case_file.to_prompt_text()
    assert "Locus File" in text
    # Should say something like "not found" or "not available"
    assert "not found" in text or "not available" in text


def test_to_prompt_text_large_file_line_number_width(tmp_path: Path) -> None:
    """Line numbers in windowed excerpts use width based on total_lines,
    so a 1500-line file renders as 4-digit right-aligned."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="src/ui/huge.html:1250 — missing")],
    )
    locus_file = tmp_path / "src" / "ui" / "huge.html"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("\n".join(f"line {i}" for i in range(1, 1501)))

    case_file = build_case_file(_cluster(sample_id="f_001"), tmp_path)
    text = case_file.to_prompt_text()

    # 4-digit line numbers (1500 has 4 digits)
    assert "   1: line 1" in text  # head-region line 1 uses 4-char width
    assert "1250: line 1250" in text  # windowed line 1250 also 4-char
