"""Fitness triage — dedupe, rank, and surface the top findings.

Transforms a flat ``fitness-backlog.md`` (thousands of near-duplicate
findings) into a ``fitness-queue.md`` that surfaces ~10-25 distinct
clusters in priority order. Agents and humans read the queue to pick
their next action.

Design: docs/superpowers/specs/2026-04-14-fitness-triage-design.md
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

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


@dataclass(frozen=True)
class DedupeKey:
    """Composite key identifying a cluster of equivalent findings.

    Two findings are considered equivalent for triage purposes when
    their (locus, axis, canonical_summary, persona) tuples are identical.
    """

    locus: str
    axis: str
    canonical_summary: str
    persona: str


def dedupe_key_for(row: dict[str, str]) -> DedupeKey:
    """Extract a DedupeKey from a parsed fitness-backlog row.

    Expects the dict shape returned by
    ``dazzle.fitness.backlog.read_backlog`` — nine-string columns
    (id, created, locus, axis, severity, persona, status, route, summary).
    """
    return DedupeKey(
        locus=row["locus"],
        axis=row["axis"],
        canonical_summary=canonicalize_summary(row["summary"]),
        persona=row["persona"],
    )


def compute_cluster_id(key: DedupeKey) -> str:
    """Return the canonical ``CL-<8hex>`` cluster identifier for a key.

    Uses SHA-256 over a simple repr so identical keys always produce
    identical IDs across regenerations and processes. Stable across
    the full ``fitness-backlog.md`` -> ``fitness-queue.md`` round trip.
    """
    payload = f"{key.locus}\x1f{key.axis}\x1f{key.canonical_summary}\x1f{key.persona}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{CLUSTER_ID_PREFIX}{digest[:CLUSTER_ID_LENGTH]}"
