"""Regression comparator (v1 task 16).

Compares the findings from one cycle to the next. A regression is
declared when NEW findings appear after a previous cycle that had
applied a hard correction — in other words, a fix that made things
worse somewhere else (or silently reverted).

Finding identity is content-based: two findings describe the same
underlying issue iff they share ``(capability_ref, expected, persona,
locus)``. We deliberately ignore ``run_id`` and ``id`` here so findings
can be compared across cycles.
"""

from __future__ import annotations

from dataclasses import dataclass

from dazzle.fitness.models import Finding


@dataclass(frozen=True)
class RegressionReport:
    new_findings: list[Finding]
    fixed_findings: list[Finding]
    persistent_findings: list[Finding]
    regression_detected: bool


def _key(f: Finding) -> tuple[str, str, str, str]:
    """Content-identity key for a finding."""
    return (f.capability_ref, f.expected, f.persona, f.locus)


def compare_cycles(
    previous: list[Finding],
    current: list[Finding],
    previous_had_hard_correction: bool,
) -> RegressionReport:
    """Compare two cycles of findings and decide whether a regression occurred.

    Regression = NEW findings appeared AND the previous cycle applied a
    hard correction. That signals the fix either didn't work or caused
    collateral damage.
    """
    prev_map = {_key(f): f for f in previous}
    curr_map = {_key(f): f for f in current}

    new_keys = set(curr_map) - set(prev_map)
    fixed_keys = set(prev_map) - set(curr_map)
    persistent_keys = set(prev_map) & set(curr_map)

    new_findings = [curr_map[k] for k in new_keys]
    fixed_findings = [prev_map[k] for k in fixed_keys]
    persistent_findings = [curr_map[k] for k in persistent_keys]

    regression = bool(new_findings) and previous_had_hard_correction

    return RegressionReport(
        new_findings=new_findings,
        fixed_findings=fixed_findings,
        persistent_findings=persistent_findings,
        regression_detected=regression,
    )
