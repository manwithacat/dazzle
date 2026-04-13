"""Tests for the regression comparator (v1 task 16)."""

from __future__ import annotations

from datetime import UTC, datetime

from dazzle.fitness.comparator import RegressionReport, compare_cycles
from dazzle.fitness.models import EvidenceEmbedded, Finding


def _finding(id_: str) -> Finding:
    return Finding(
        id=id_,
        created=datetime(2026, 4, 13, tzinfo=UTC),
        run_id="r",
        cycle=None,
        axis="conformance",
        locus="lifecycle",
        severity="high",
        persona="agent",
        capability_ref=f"cap:{id_}",
        expected="x",
        observed="y",
        evidence_embedded=EvidenceEmbedded({}, [], []),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="hard",
        fix_commit=None,
        alternative_fix=None,
    )


def test_new_findings_after_hard_correction_is_regression() -> None:
    previous = [_finding("FIND-001")]
    current = [_finding("FIND-002")]  # different finding appeared
    report: RegressionReport = compare_cycles(
        previous=previous,
        current=current,
        previous_had_hard_correction=True,
    )
    assert report.regression_detected is True
    assert len(report.new_findings) == 1
    assert len(report.fixed_findings) == 1


def test_same_findings_no_regression() -> None:
    f = [_finding("FIND-001")]
    report = compare_cycles(previous=f, current=f, previous_had_hard_correction=True)
    assert report.regression_detected is False
    assert len(report.persistent_findings) == 1


def test_finding_cleared_with_no_new_findings() -> None:
    previous = [_finding("FIND-001")]
    current: list[Finding] = []
    report = compare_cycles(previous=previous, current=current, previous_had_hard_correction=True)
    assert report.regression_detected is False
    assert len(report.fixed_findings) == 1
