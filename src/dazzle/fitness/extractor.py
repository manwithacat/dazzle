"""Extractor — transform FitnessDiff into self-contained Findings (v1 task 14).

Each Finding carries an ``EvidenceEmbedded`` envelope that mirrors the
relevant transcript window and row-level diffs so downstream consumers
never need to re-read the underlying (potentially-expired) ledger.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from dazzle.fitness.models import (
    EvidenceEmbedded,
    Finding,
    FitnessDiff,
    LedgerStep,
)


def _context_window(
    steps: list[LedgerStep], center_step: int, radius: int = 3
) -> list[dict[str, Any]]:
    """Return ±``radius`` steps around ``center_step`` as plain dicts."""
    lo = max(0, center_step - radius - 1)
    hi = min(len(steps), center_step + radius)
    return [
        {
            "step_no": s.step_no,
            "expected": s.expected,
            "action": s.action_summary,
            "observed": s.observed_ui,
        }
        for s in steps[lo:hi]
    ]


def extract_findings_from_diff(
    diff: FitnessDiff,
    run_id: str,
    persona: str,
    low_confidence: bool,
    now: datetime,
) -> list[Finding]:
    """Produce Findings from a FitnessDiff.

    v1 scope: only "motion without progress" lifecycle findings. Extended
    producers (coverage, spec_stale, story_drift) land in later tasks.
    """
    findings: list[Finding] = []

    for progress in diff.progress:
        if progress.was_progress:
            continue

        evidence = EvidenceEmbedded(
            expected_ledger_step={
                "expect": diff.steps[-1].expected if diff.steps else "",
                "action": diff.steps[-1].action_summary if diff.steps else "",
                "observed": diff.steps[-1].observed_ui if diff.steps else "",
            },
            diff_summary=[rc for rc in diff.updated if rc.row_id == progress.row_id][:3],
            transcript_excerpt=_context_window(diff.steps, len(diff.steps), radius=3),
        )

        findings.append(
            Finding(
                id=f"FIND-{uuid4().hex[:8]}",
                created=now,
                run_id=run_id,
                cycle=None,
                axis="conformance",
                locus="lifecycle",
                severity="high",
                persona=persona,
                capability_ref=f"entity:{progress.entity}/{progress.row_id}",
                expected=(
                    f"{progress.entity} {progress.row_id} advances through "
                    f"its lifecycle with valid evidence"
                ),
                observed=(
                    f"{progress.entity} {progress.row_id} transitioned "
                    f"{progress.transitions_observed} but none satisfied the "
                    f"declared evidence predicate (motion without work)"
                ),
                evidence_embedded=evidence,
                disambiguation=False,
                low_confidence=low_confidence,
                status="PROPOSED",
                route="hard",
                fix_commit=None,
                alternative_fix=None,
            )
        )

    return findings
