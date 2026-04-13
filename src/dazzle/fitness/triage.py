"""Fitness triage — dedupe, rank, and surface the top findings.

Transforms a flat ``fitness-backlog.md`` (thousands of near-duplicate
findings) into a ``fitness-queue.md`` that surfaces ~10-25 distinct
clusters in priority order. Agents and humans read the queue to pick
their next action.

Design: docs/superpowers/specs/2026-04-14-fitness-triage-design.md
"""

from __future__ import annotations

SEVERITY_RANK: dict[str, int] = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 0,
}

CLUSTER_ID_PREFIX = "CL-"
CLUSTER_ID_LENGTH = 8  # hex characters after the prefix
CANONICAL_SUMMARY_MAX_LEN = 120


def canonicalize_summary(summary: str) -> str:
    """Normalise a finding summary for dedupe-key construction.

    Lowercases, strips outer whitespace, collapses internal whitespace
    to single spaces, then truncates at CANONICAL_SUMMARY_MAX_LEN chars.
    Matches the write-side truncation in
    ``dazzle.fitness.backlog._finding_to_row``.
    """
    return " ".join(summary.strip().lower().split())[:CANONICAL_SUMMARY_MAX_LEN]
