"""Proposal dataclasses and on-disk serialisation.

A Proposal is the investigator's terminal output — one per cluster per run.
Serialised as markdown with YAML frontmatter to
.dazzle/fitness-proposals/<cluster_id>-<proposal_id[:8]>.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ProposalStatus = Literal[
    "proposed",
    "applied",
    "verified",
    "reverted",
    "rejected",
]


@dataclass(frozen=True)
class ProposedFix:
    """A single-file fix inside a Proposal.

    Distinct from corrector.Fix (which is a multi-file bundle) — the
    investigator models one diff per file so the per-file rationale
    and confidence are meaningful.
    """

    file_path: str  # repo-relative
    line_range: tuple[int, int] | None
    diff: str  # unified diff anchored to file_path
    rationale: str  # one or two sentences
    confidence: float  # 0.0..1.0


@dataclass(frozen=True)
class Proposal:
    """Terminal output of one investigator mission run."""

    proposal_id: str  # UUID4 hex
    cluster_id: str  # back-reference, e.g. "CL-a1b2c3d4"
    created: datetime  # UTC
    investigator_run_id: str  # DazzleAgent transcript anchor
    fixes: tuple[ProposedFix, ...]
    overall_confidence: float  # 0.0..1.0
    rationale: str  # the "why"
    alternatives_considered: tuple[str, ...]
    verification_plan: str  # what the actor should re-run and expect
    evidence_paths: tuple[str, ...]  # repo-relative
    tool_calls_summary: tuple[str, ...]  # ordered
    status: ProposalStatus
