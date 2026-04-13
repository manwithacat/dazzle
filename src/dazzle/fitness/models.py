"""Shared dataclasses for the Agent-Led Fitness methodology (v1 Task 3).

All downstream fitness modules depend on these types. Defining them up
front avoids circular imports between ledger, progress evaluator,
adversary, and finding-producer subsystems.

The shapes mirror the design in
``docs/superpowers/specs/2026-04-13-agent-led-fitness-methodology-design.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Axis = Literal["coverage", "conformance"]
Locus = Literal["implementation", "story_drift", "spec_stale", "lifecycle"]
Severity = Literal["critical", "high", "medium", "low"]
Route = Literal["hard", "soft"]
FindingStatus = Literal["PROPOSED", "ACCEPTED", "IN_PROGRESS", "FIXED", "VERIFIED", "REJECTED"]
ChangeKind = Literal["insert", "update", "delete"]


@dataclass(frozen=True)
class RowChange:
    """A single row-level change observed during a fitness run.

    ``semantic_repr`` is the compact rendering of the row as defined by the
    entity's ``fitness.repr_fields`` projection — stable, domain-essential,
    diffable.
    """

    table: str
    row_id: str
    kind: ChangeKind
    semantic_repr: str
    field_deltas: dict[str, tuple[Any, Any]]


@dataclass(frozen=True)
class ProgressRecord:
    """A single lifecycle-progress observation.

    Produced by ``progress_evaluator.py`` from lifecycle-declared entities
    touched during the run. A transition counts as progress iff it advances
    ``order`` AND the evidence predicate holds.
    """

    entity: str
    row_id: str
    transitions_observed: list[tuple[str, str]]  # (from_state, to_state)
    evidence_satisfied: list[bool]  # parallel to transitions_observed
    ended_at_state: str
    was_progress: bool


@dataclass(frozen=True)
class LedgerStep:
    """One step in the action ledger.

    The interlock requires ``expected`` to be non-empty: the agent must
    commit an expectation before acting. Violation raises at construction
    time so the rule cannot be bypassed anywhere downstream.
    """

    step_no: int
    txn_id: str | None
    expected: str
    action_summary: str
    observed_ui: str
    observed_changes: list[RowChange]
    delta: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.expected or not self.expected.strip():
            raise ValueError(
                "LedgerStep.expected must be non-empty (interlock enforces EXPECT before ACTION)"
            )


@dataclass(frozen=True)
class FitnessDiff:
    """Aggregated diff produced by one fitness run.

    Consumed by the finding producers (conformance, coverage, regression).
    """

    run_id: str
    steps: list[LedgerStep]
    created: list[RowChange]
    updated: list[RowChange]
    deleted: list[RowChange]
    progress: list[ProgressRecord]
    semantic_repr_config: dict[str, list[str]]


@dataclass(frozen=True)
class EvidenceEmbedded:
    """Evidence bundle attached to each Finding.

    ``transcript_excerpt`` carries the raw step dicts centered (±3) around
    the finding, so downstream consumers never need to re-read the full
    transcript.
    """

    expected_ledger_step: dict[str, Any]
    diff_summary: list[RowChange]
    transcript_excerpt: list[dict[str, Any]]


@dataclass(frozen=True)
class Finding:
    """A single fitness finding.

    Findings are emitted by the conformance / coverage / regression
    producers and consumed by the router, which decides hard vs soft
    routing, dedupes, and writes them to the audit log.
    """

    id: str
    created: datetime
    run_id: str
    cycle: str | None
    axis: Axis
    locus: Locus
    severity: Severity
    persona: str
    capability_ref: str
    expected: str
    observed: str
    evidence_embedded: EvidenceEmbedded
    disambiguation: bool
    low_confidence: bool
    status: FindingStatus
    route: Route
    fix_commit: str | None
    alternative_fix: str | None
