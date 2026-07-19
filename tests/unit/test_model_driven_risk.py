"""Tests for the model-driven failure-mode scoring contract."""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from dazzle.risk.model_driven import (
    CATALOGUE,
    DetectorState,
    FailureModeEvidence,
    build_report,
    score_failure_mode,
)


def test_catalogue_matches_architecture_doc() -> None:
    doc = Path("docs/architecture/model-driven-failure-modes.md").read_text()
    documented = sorted(set(re.findall(r"\bMDF-\d{2}\b", doc)))
    coded = sorted(entry.id for entry in CATALOGUE)

    assert coded == documented


def test_score_uses_detector_coverage_escape_penalty_and_multiplier() -> None:
    spec = next(entry for entry in CATALOGUE if entry.id == "MDF-04")
    evidence = FailureModeEvidence(
        mode_id="MDF-04",
        exposure=0.5,
        detectors={
            "static": DetectorState.LIVE,
            "runtime": DetectorState.DEFINED,
        },
        serious_findings_90d=4,
        serious_findings_that_slipped_live_detectors_90d=1,
        evidence={"all_escape_hatches": 12, "unsafe_escape_hatches": 6},
    )

    score = score_failure_mode(spec, evidence)

    assert score.raw_detector_coverage == pytest.approx(0.7)
    assert score.escape_penalty == pytest.approx(0.25)
    assert score.detector_coverage == pytest.approx(0.525)
    assert score.detection_gap == pytest.approx(0.475)
    expected = round(100 * min(1.0, spec.severity * 0.5 * 0.475 * spec.agent_multiplier))
    assert score.risk == expected
    assert score.evidence["unsafe_escape_hatches"] == 6


def test_detection_gap_has_floor_for_live_detectors() -> None:
    spec = next(entry for entry in CATALOGUE if entry.id == "MDF-02")
    evidence = FailureModeEvidence(
        mode_id="MDF-02",
        exposure=1.0,
        detectors=dict.fromkeys(spec.required_dimensions, DetectorState.LIVE),
    )

    score = score_failure_mode(spec, evidence)

    assert score.detector_coverage == pytest.approx(1.0)
    assert score.detection_gap == pytest.approx(0.05)
    assert score.risk > 0


def test_build_report_scores_all_modes_and_penalises_multiple_high_modes() -> None:
    generated_at = datetime(2026, 6, 4, tzinfo=UTC)
    report = build_report(
        [
            FailureModeEvidence(mode_id="MDF-01", exposure=0.6),
            FailureModeEvidence(mode_id="MDF-04", exposure=0.6),
            FailureModeEvidence(mode_id="MDF-13", exposure=0.6),
        ],
        project_root="/tmp/example",
        generated_at=generated_at,
    )

    assert report.generated_at == generated_at
    assert report.project_root == "/tmp/example"
    assert len(report.scores) == len(CATALOGUE)
    assert report.overall["high_risk_count"] == 3
    assert report.overall["score"] == min(100, report.overall["max_risk"] + 10)


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown model-driven failure mode"):
        FailureModeEvidence(mode_id="MDF-99", exposure=0.5)


def test_slipped_findings_cannot_exceed_serious_findings() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        FailureModeEvidence(
            mode_id="MDF-12",
            exposure=0.5,
            serious_findings_90d=1,
            serious_findings_that_slipped_live_detectors_90d=2,
        )
