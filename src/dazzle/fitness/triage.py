"""Fitness triage — dedupe, rank, and surface the top findings.

Transforms a flat ``fitness-backlog.md`` (thousands of near-duplicate
findings) into a ``fitness-queue.md`` that surfaces ~10-25 distinct
clusters in priority order. Agents and humans read the queue to pick
their next action.

Design: docs/superpowers/specs/2026-04-14-fitness-triage-design.md
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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


@dataclass(frozen=True)
class Cluster:
    """A grouped set of equivalent findings.

    Sort key: ``(-severity_rank, -cluster_size, cluster_id)`` — highest
    severity first, biggest clusters within a severity band first,
    cluster_id lexicographic as a deterministic tiebreaker.
    """

    cluster_id: str
    locus: str
    axis: str
    canonical_summary: str
    persona: str
    severity: str
    cluster_size: int
    first_seen: datetime
    last_seen: datetime
    sample_id: str

    @property
    def sort_key(self) -> tuple[int, int, str]:
        # Negated so `sorted()` ascending yields the desired order.
        rank = SEVERITY_RANK.get(self.severity, 0)
        return (-rank, -self.cluster_size, self.cluster_id)


def _parse_created(value: str) -> datetime:
    """Parse a backlog-row 'created' string into a UTC datetime.

    Falls back to the epoch on unparseable input so clustering never
    crashes on a malformed row.
    """
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.fromtimestamp(0, tz=UTC)


def _aggregate_severity(severities: list[str]) -> str:
    """Return the highest-ranked severity string in the list.

    Unknown severity values are treated as rank 0 (lowest) but are
    still eligible for selection when they're the *only* severity in
    the cluster — in that case the raw value is returned unchanged so
    callers see what's there.
    """
    ranked = [(SEVERITY_RANK.get(s, 0), s) for s in severities]
    ranked.sort(key=lambda pair: pair[0])
    return ranked[-1][1]


def cluster_findings(rows: Iterable[dict[str, str]]) -> list[Cluster]:
    """Group parsed backlog rows into clusters, sorted by priority.

    Input: iterable of dicts as produced by
    ``dazzle.fitness.backlog.read_backlog``. Order-independent.

    Output: list of Clusters sorted by ``Cluster.sort_key`` ascending,
    which corresponds to "highest priority first" — see the spec.
    """
    groups: dict[DedupeKey, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[dedupe_key_for(row)].append(row)

    clusters: list[Cluster] = []
    for key, members in groups.items():
        created_datetimes = [_parse_created(r["created"]) for r in members]
        severity = _aggregate_severity([r["severity"] for r in members])
        clusters.append(
            Cluster(
                cluster_id=compute_cluster_id(key),
                locus=key.locus,
                axis=key.axis,
                canonical_summary=key.canonical_summary,
                persona=key.persona,
                severity=severity,
                cluster_size=len(members),
                first_seen=min(created_datetimes),
                last_seen=max(created_datetimes),
                sample_id=members[0]["id"],
            )
        )

    clusters.sort(key=lambda c: c.sort_key)
    return clusters


_QUEUE_HEADER_TEMPLATE = """# Fitness Queue

Ranked, deduped view of `fitness-backlog.md`. Regenerated by
`dazzle fitness triage`. Re-run after each fitness cycle to refresh.

**Project:** {project_name}
**Generated:** {generated}
**Raw findings:** {raw_findings}
**Clusters:** {clusters_count}
**Dedup ratio:** {dedup_ratio}×

| rank | cluster_id | severity | locus | axis | persona | size | summary | first_seen | last_seen | sample_id |
|------|-----------|----------|-------|------|---------|------|---------|------------|-----------|-----------|
"""

_QUEUE_ROW_RE = re.compile(
    r"^\| (?P<rank>\d+) \| (?P<cluster_id>CL-\w+) \| (?P<severity>[^|]+) \|"
    r" (?P<locus>[^|]+) \| (?P<axis>[^|]+) \| (?P<persona>[^|]+) \|"
    r" (?P<size>\d+) \| (?P<summary>[^|]*) \| (?P<first_seen>[^|]+) \|"
    r" (?P<last_seen>[^|]+) \| (?P<sample_id>[^|]+) \|$"
)


def _queue_row(rank: int, cluster: Cluster) -> str:
    summary = cluster.canonical_summary.replace("|", "/")
    return (
        f"| {rank} | {cluster.cluster_id} | {cluster.severity} | "
        f"{cluster.locus} | {cluster.axis} | {cluster.persona} | "
        f"{cluster.cluster_size} | {summary} | "
        f"{cluster.first_seen.isoformat()} | {cluster.last_seen.isoformat()} | "
        f"{cluster.sample_id} |"
    )


def write_queue_file(
    path: Path,
    clusters: list[Cluster],
    *,
    project_name: str,
    raw_findings_count: int,
) -> None:
    """Write clusters to a fitness-queue.md file atomically.

    Writes to ``<path>.tmp`` and calls ``os.replace`` so readers never
    observe a half-written file.
    """
    dedup_ratio = f"{raw_findings_count / len(clusters):.1f}" if clusters else "0.0"
    header = _QUEUE_HEADER_TEMPLATE.format(
        project_name=project_name,
        generated=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        raw_findings=raw_findings_count,
        clusters_count=len(clusters),
        dedup_ratio=dedup_ratio,
    )
    rows = [_queue_row(i + 1, c) for i, c in enumerate(clusters)]

    content = header + "\n".join(rows) + ("\n" if rows else "")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def read_queue_file(path: Path) -> list[Cluster]:
    """Parse a previously-written fitness-queue.md back into Clusters.

    Returns an empty list if the file is missing or entirely malformed.
    Malformed individual rows are silently skipped.
    """
    if not path.exists():
        return []
    try:
        text = path.read_text()
    except OSError:
        return []

    clusters: list[Cluster] = []
    for line in text.splitlines():
        m = _QUEUE_ROW_RE.match(line.strip())
        if not m:
            continue
        g = m.groupdict()
        try:
            first_seen = datetime.fromisoformat(g["first_seen"].strip())
            last_seen = datetime.fromisoformat(g["last_seen"].strip())
        except ValueError:
            continue
        clusters.append(
            Cluster(
                cluster_id=g["cluster_id"].strip(),
                locus=g["locus"].strip(),
                axis=g["axis"].strip(),
                canonical_summary=g["summary"].strip(),
                persona=g["persona"].strip(),
                severity=g["severity"].strip(),
                cluster_size=int(g["size"]),
                first_seen=first_seen,
                last_seen=last_seen,
                sample_id=g["sample_id"].strip(),
            )
        )
    return clusters
