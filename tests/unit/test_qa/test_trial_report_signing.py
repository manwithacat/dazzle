"""Tests for SigningOutcome block in trial reports (Task 9)."""

from __future__ import annotations

from dazzle.qa.signing_verifier import SigningOutcome
from dazzle.qa.trial_report import build_trial_report, render_trial_report


def test_report_includes_signing_outcomes() -> None:
    outcome = SigningOutcome(
        detected=True,
        expected_outcome_inferred="signed",
        functional={
            "status": "pass",
            "final_row_status": "signed",
            "audit_row_present": True,
            "reason": None,
        },
        signature_integrity={"valid": True, "summary": "PAdES B-T OK"},
        latency_ms={"get_sign": 142, "post_sign": 891},
    )
    report = build_trial_report(
        scenario_name="happy",
        user_identity="Priya",
        verdict="All good.",
        friction=[],
        signing_outcome=outcome,
    )
    assert report.signing_outcomes is not None
    assert report.signing_outcomes["detected"] is True
    assert report.signing_outcomes["functional"]["status"] == "pass"
    md = render_trial_report(report)
    assert "Signing Outcomes" in md
    assert "PAdES B-T OK" in md


def test_report_omits_signing_outcomes_when_none() -> None:
    # When signing_outcome is omitted, signing_outcomes should be None
    # (the block is opt-in based on whether signing was graded).
    report = build_trial_report(
        scenario_name="t",
        user_identity="P",
        verdict="fine",
        friction=[],
    )
    assert report.signing_outcomes is None
    md = render_trial_report(report)
    assert "Signing Outcomes" not in md
