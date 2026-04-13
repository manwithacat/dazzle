# Fitness Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `dazzle fitness triage` — a deduped, ranked queue view over `fitness-backlog.md` that surfaces ~10–25 distinct actionable clusters per example in priority order, so autonomous agents have a clear next-action signal without reading thousands of raw findings.

**Architecture:** Single-file core module `src/dazzle/fitness/triage.py` (pure functions + `Cluster` dataclass) consumes the existing `read_backlog()` helper, groups findings by `(locus, axis, canonical_summary, persona)` into clusters, ranks them by `(-severity_rank, -cluster_size, cluster_id)`, and writes `fitness-queue.md` atomically. CLI exposes `triage` (write) and `queue` (read) commands; MCP exposes a read-only `queue` operation. No state tracking, no classification, no auto-invocation.

**Tech Stack:** Python 3.12+, `dataclasses`, `hashlib.sha256`, `typer`, existing `dazzle.fitness.backlog.read_backlog()`, existing MCP handler registration pattern (`handlers_consolidated.py` + `tools_consolidated.py`).

**Spec reference:** `docs/superpowers/specs/2026-04-14-fitness-triage-design.md`

---

## File Structure

**New files (10):**

| Path | Purpose |
|------|---------|
| `src/dazzle/fitness/triage.py` | Core module — `Cluster`, `DedupeKey`, `canonicalize_summary`, `dedupe_key_for`, `compute_cluster_id`, `cluster_findings`, `write_queue_file`, `read_queue_file` |
| `src/dazzle/cli/fitness.py` | `fitness_app` Typer with `triage` and `queue` commands |
| `src/dazzle/mcp/server/handlers/fitness.py` | Read-only MCP handler — `queue` operation |
| `tests/unit/fitness/test_triage.py` | 12 unit tests for the core module |
| `tests/fixtures/fitness_triage/__init__.py` | Empty fixture package marker |
| `tests/fixtures/fitness_triage/empty.md` | Just the header, 0 rows |
| `tests/fixtures/fitness_triage/small.md` | 10 rows with 3 distinct dedupe keys |
| `tests/fixtures/fitness_triage/malformed.md` | Mixed valid + malformed rows |
| `tests/unit/fitness/test_triage_cli.py` | 1 CLI smoke test for `dazzle fitness triage` |
| `tests/unit/mcp/test_fitness_handler.py` | 1 MCP handler smoke test |
| `docs/reference/fitness-triage.md` | User-facing reference doc |

**Modified files (3):**

| Path | Change |
|------|--------|
| `src/dazzle/cli/__init__.py` | Import and register `fitness_app` |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Register `handle_fitness` |
| `src/dazzle/mcp/server/tools_consolidated.py` | Add `Tool(name="fitness", ...)` |

---

## Task 1: Core dataclasses + canonicalize_summary

**Files:**
- Create: `src/dazzle/fitness/triage.py`
- Create: `tests/unit/fitness/test_triage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/fitness/test_triage.py`:

```python
"""Unit tests for dazzle.fitness.triage."""

from __future__ import annotations

from dazzle.fitness.triage import (
    SEVERITY_RANK,
    canonicalize_summary,
)


class TestCanonicalizeSummary:
    def test_lowercases(self) -> None:
        assert canonicalize_summary("FooBar") == "foobar"

    def test_strips_outer_whitespace(self) -> None:
        assert canonicalize_summary("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self) -> None:
        assert canonicalize_summary("a  b\t c\n d") == "a b c d"

    def test_truncates_at_120_chars(self) -> None:
        long = "x" * 200
        assert len(canonicalize_summary(long)) == 120

    def test_idempotent(self) -> None:
        s = "  Hello   World  "
        once = canonicalize_summary(s)
        assert canonicalize_summary(once) == once


class TestSeverityRank:
    def test_rank_ordering(self) -> None:
        assert SEVERITY_RANK["critical"] > SEVERITY_RANK["high"]
        assert SEVERITY_RANK["high"] > SEVERITY_RANK["medium"]
        assert SEVERITY_RANK["medium"] > SEVERITY_RANK["low"]

    def test_all_four_levels_present(self) -> None:
        assert set(SEVERITY_RANK.keys()) == {"critical", "high", "medium", "low"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_triage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.fitness.triage'`

- [ ] **Step 3: Implement the module skeleton**

Create `src/dazzle/fitness/triage.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_triage.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/triage.py tests/unit/fitness/test_triage.py
git commit -m "$(cat <<'EOF'
feat(fitness): add triage module skeleton + canonicalize_summary

First piece of the fitness-triage subsystem (docs/superpowers/specs/
2026-04-14-fitness-triage-design.md). Defines SEVERITY_RANK and the
canonicalize_summary helper used to build dedupe keys. Covered by 7
unit tests.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: DedupeKey + cluster_id

**Files:**
- Modify: `src/dazzle/fitness/triage.py`
- Modify: `tests/unit/fitness/test_triage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/fitness/test_triage.py`:

```python
from dazzle.fitness.triage import (
    DedupeKey,
    compute_cluster_id,
    dedupe_key_for,
)


class TestDedupeKeyFor:
    def test_extracts_all_four_fields(self) -> None:
        row = {
            "id": "FIND-abc",
            "created": "2026-04-13T19:13:10+00:00",
            "locus": "story_drift",
            "axis": "coverage",
            "severity": "medium",
            "persona": "Administrator",
            "status": "PROPOSED",
            "route": "soft",
            "summary": "No matching story found",
        }
        key = dedupe_key_for(row)
        assert key.locus == "story_drift"
        assert key.axis == "coverage"
        assert key.canonical_summary == "no matching story found"
        assert key.persona == "Administrator"

    def test_canonicalises_summary(self) -> None:
        row = {
            "id": "FIND-abc",
            "created": "2026-04-13T19:13:10+00:00",
            "locus": "spec_stale",
            "axis": "conformance",
            "severity": "high",
            "persona": "Admin",
            "status": "PROPOSED",
            "route": "hard",
            "summary": "  MIXED  CASE  Summary  ",
        }
        key = dedupe_key_for(row)
        assert key.canonical_summary == "mixed case summary"


class TestComputeClusterID:
    def test_format(self) -> None:
        key = DedupeKey(
            locus="story_drift",
            axis="coverage",
            canonical_summary="no matching story found",
            persona="Administrator",
        )
        cluster_id = compute_cluster_id(key)
        assert cluster_id.startswith("CL-")
        assert len(cluster_id) == 3 + 8  # "CL-" + 8 hex chars

    def test_deterministic(self) -> None:
        key = DedupeKey(
            locus="story_drift",
            axis="coverage",
            canonical_summary="foo",
            persona="Admin",
        )
        assert compute_cluster_id(key) == compute_cluster_id(key)

    def test_different_keys_produce_different_ids(self) -> None:
        key1 = DedupeKey(locus="story_drift", axis="coverage", canonical_summary="foo", persona="A")
        key2 = DedupeKey(locus="story_drift", axis="coverage", canonical_summary="foo", persona="B")
        assert compute_cluster_id(key1) != compute_cluster_id(key2)

    def test_hex_characters_only(self) -> None:
        key = DedupeKey(locus="l", axis="a", canonical_summary="s", persona="p")
        suffix = compute_cluster_id(key)[3:]  # strip "CL-"
        assert all(c in "0123456789abcdef" for c in suffix)


class TestDedupeKeyFrozen:
    def test_is_frozen(self) -> None:
        import pytest

        key = DedupeKey(locus="l", axis="a", canonical_summary="s", persona="p")
        with pytest.raises((AttributeError, TypeError)):
            key.locus = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fitness/test_triage.py -v`
Expected: FAIL — `ImportError: cannot import name 'DedupeKey'`.

- [ ] **Step 3: Implement DedupeKey and cluster_id helpers**

Append to `src/dazzle/fitness/triage.py`:

```python
import hashlib
from dataclasses import dataclass


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
    the full ``fitness-backlog.md`` → ``fitness-queue.md`` round trip.
    """
    payload = f"{key.locus}\x1f{key.axis}\x1f{key.canonical_summary}\x1f{key.persona}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{CLUSTER_ID_PREFIX}{digest[:CLUSTER_ID_LENGTH]}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/test_triage.py -v`
Expected: PASS — 7 (from Task 1) + 7 = 14 tests.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/triage.py tests/unit/fitness/test_triage.py
git commit -m "$(cat <<'EOF'
feat(fitness): add DedupeKey + compute_cluster_id for triage

Extract (locus, axis, canonical_summary, persona) from a backlog row
and hash it to a deterministic CL-<8hex> cluster identifier. Stable
across regenerations so agents can reference clusters in commit
messages.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Cluster dataclass + cluster_findings

**Files:**
- Modify: `src/dazzle/fitness/triage.py`
- Modify: `tests/unit/fitness/test_triage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/fitness/test_triage.py`:

```python
from datetime import datetime, timezone

from dazzle.fitness.triage import Cluster, cluster_findings


def _row(
    *,
    finding_id: str = "FIND-abc",
    created: str = "2026-04-13T19:13:10+00:00",
    locus: str = "story_drift",
    axis: str = "coverage",
    severity: str = "medium",
    persona: str = "Administrator",
    summary: str = "No matching story found",
) -> dict[str, str]:
    return {
        "id": finding_id,
        "created": created,
        "locus": locus,
        "axis": axis,
        "severity": severity,
        "persona": persona,
        "status": "PROPOSED",
        "route": "soft",
        "summary": summary,
    }


class TestClusterFindings:
    def test_empty_input_returns_empty_list(self) -> None:
        assert cluster_findings([]) == []

    def test_single_row_produces_single_cluster(self) -> None:
        clusters = cluster_findings([_row()])
        assert len(clusters) == 1
        c = clusters[0]
        assert c.cluster_size == 1
        assert c.severity == "medium"
        assert c.persona == "Administrator"

    def test_three_distinct_keys_produce_three_clusters(self) -> None:
        rows = [
            _row(finding_id="FIND-1", persona="A"),
            _row(finding_id="FIND-2", persona="B"),
            _row(finding_id="FIND-3", persona="C"),
        ]
        clusters = cluster_findings(rows)
        assert len(clusters) == 3
        personas = {c.persona for c in clusters}
        assert personas == {"A", "B", "C"}

    def test_identical_keys_aggregate(self) -> None:
        rows = [
            _row(finding_id="FIND-1", created="2026-04-13T19:00:00+00:00"),
            _row(finding_id="FIND-2", created="2026-04-13T19:30:00+00:00"),
            _row(finding_id="FIND-3", created="2026-04-13T20:00:00+00:00"),
        ]
        clusters = cluster_findings(rows)
        assert len(clusters) == 1
        c = clusters[0]
        assert c.cluster_size == 3
        assert c.first_seen == datetime(2026, 4, 13, 19, 0, 0, tzinfo=timezone.utc)
        assert c.last_seen == datetime(2026, 4, 13, 20, 0, 0, tzinfo=timezone.utc)
        assert c.sample_id == "FIND-1"

    def test_severity_aggregation_takes_max(self) -> None:
        rows = [
            _row(finding_id="FIND-1", severity="medium"),
            _row(finding_id="FIND-2", severity="high"),
            _row(finding_id="FIND-3", severity="low"),
        ]
        clusters = cluster_findings(rows)
        assert len(clusters) == 1
        assert clusters[0].severity == "high"

    def test_sort_order_severity_descending(self) -> None:
        rows = [
            _row(finding_id="FIND-1", persona="X", severity="low"),
            _row(finding_id="FIND-2", persona="Y", severity="critical"),
            _row(finding_id="FIND-3", persona="Z", severity="medium"),
        ]
        clusters = cluster_findings(rows)
        severities = [c.severity for c in clusters]
        assert severities == ["critical", "medium", "low"]

    def test_sort_order_within_severity_by_cluster_size_desc(self) -> None:
        rows = [
            # cluster A: 1 member, medium
            _row(finding_id="FIND-a1", persona="A", severity="medium"),
            # cluster B: 3 members, medium
            _row(finding_id="FIND-b1", persona="B", severity="medium"),
            _row(finding_id="FIND-b2", persona="B", severity="medium"),
            _row(finding_id="FIND-b3", persona="B", severity="medium"),
        ]
        clusters = cluster_findings(rows)
        assert len(clusters) == 2
        assert clusters[0].persona == "B"  # size 3 first
        assert clusters[1].persona == "A"  # size 1 second

    def test_sort_tiebreaker_is_cluster_id(self) -> None:
        """Same severity, same size → sort by cluster_id lex for stability."""
        rows = [
            _row(finding_id="FIND-1", persona="Zebra", severity="medium"),
            _row(finding_id="FIND-2", persona="Alpha", severity="medium"),
        ]
        clusters_1 = cluster_findings(rows)
        clusters_2 = cluster_findings(list(reversed(rows)))
        # Same set of clusters, same stable order, regardless of input order.
        assert [c.cluster_id for c in clusters_1] == [c.cluster_id for c in clusters_2]


class TestClusterUnknownSeverity:
    def test_falls_back_to_lowest_rank(self) -> None:
        rows = [
            _row(finding_id="FIND-1", severity="wonky"),
        ]
        clusters = cluster_findings(rows)
        # Unknown severity → rank 0 (lowest) → preserved as-is in the
        # aggregated severity field so callers see the raw value.
        assert len(clusters) == 1
        assert clusters[0].severity == "wonky"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fitness/test_triage.py::TestClusterFindings -v`
Expected: FAIL — `ImportError: cannot import name 'Cluster'`.

- [ ] **Step 3: Implement Cluster + cluster_findings**

Append to `src/dazzle/fitness/triage.py`:

```python
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable


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
        return datetime.fromtimestamp(0, tz=timezone.utc)


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/test_triage.py -v`
Expected: PASS — 14 (prior) + 9 = 23 tests.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/triage.py tests/unit/fitness/test_triage.py
git commit -m "$(cat <<'EOF'
feat(fitness): cluster_findings — group rows into ranked Clusters

Core triage pipeline: group parsed backlog rows by DedupeKey, build
Cluster records with max-severity aggregation + first/last seen
timestamps, sort by (-severity_rank, -cluster_size, cluster_id).
Stable across regenerations.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: write_queue_file + read_queue_file round-trip

**Files:**
- Modify: `src/dazzle/fitness/triage.py`
- Modify: `tests/unit/fitness/test_triage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/fitness/test_triage.py`:

```python
from pathlib import Path

import pytest

from dazzle.fitness.triage import read_queue_file, write_queue_file


class TestWriteQueueFile:
    def test_writes_file_with_header(self, tmp_path: Path) -> None:
        path = tmp_path / "fitness-queue.md"
        clusters = cluster_findings([_row(persona="Admin")])
        write_queue_file(
            path,
            clusters,
            project_name="demo",
            raw_findings_count=1,
        )
        content = path.read_text()
        assert "# Fitness Queue" in content
        assert "**Project:** demo" in content
        assert "**Raw findings:** 1" in content
        assert "**Clusters:** 1" in content
        assert "| rank | cluster_id |" in content

    def test_writes_file_atomically(self, tmp_path: Path) -> None:
        path = tmp_path / "fitness-queue.md"
        clusters = cluster_findings([_row()])
        write_queue_file(path, clusters, project_name="demo", raw_findings_count=1)
        # The canonical file exists, the .tmp file does NOT.
        assert path.exists()
        assert not path.with_suffix(path.suffix + ".tmp").exists()

    def test_dedup_ratio_in_header(self, tmp_path: Path) -> None:
        path = tmp_path / "fitness-queue.md"
        rows = [_row(finding_id=f"FIND-{i}") for i in range(20)]
        clusters = cluster_findings(rows)
        assert len(clusters) == 1  # all 20 rows collapse into 1 cluster
        write_queue_file(path, clusters, project_name="demo", raw_findings_count=20)
        content = path.read_text()
        assert "**Dedup ratio:** 20.0×" in content


class TestReadQueueFile:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.md"
        assert read_queue_file(path) == []

    def test_round_trip_preserves_cluster_order(self, tmp_path: Path) -> None:
        rows = [
            _row(finding_id="FIND-1", persona="A", severity="low"),
            _row(finding_id="FIND-2", persona="B", severity="critical"),
            _row(finding_id="FIND-3", persona="C", severity="medium"),
        ]
        original = cluster_findings(rows)
        path = tmp_path / "fitness-queue.md"
        write_queue_file(path, original, project_name="demo", raw_findings_count=3)

        roundtripped = read_queue_file(path)
        assert len(roundtripped) == len(original)
        for a, b in zip(original, roundtripped):
            assert a.cluster_id == b.cluster_id
            assert a.severity == b.severity
            assert a.locus == b.locus
            assert a.axis == b.axis
            assert a.persona == b.persona
            assert a.cluster_size == b.cluster_size

    def test_round_trip_preserves_first_last_seen(self, tmp_path: Path) -> None:
        rows = [
            _row(finding_id="FIND-1", created="2026-04-13T19:00:00+00:00"),
            _row(finding_id="FIND-2", created="2026-04-13T20:00:00+00:00"),
        ]
        original = cluster_findings(rows)
        path = tmp_path / "fitness-queue.md"
        write_queue_file(path, original, project_name="demo", raw_findings_count=2)

        roundtripped = read_queue_file(path)
        assert roundtripped[0].first_seen == original[0].first_seen
        assert roundtripped[0].last_seen == original[0].last_seen
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fitness/test_triage.py -v`
Expected: FAIL — `ImportError: cannot import name 'write_queue_file'`.

- [ ] **Step 3: Implement write_queue_file and read_queue_file**

Append to `src/dazzle/fitness/triage.py`:

```python
import re
from pathlib import Path

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
    r" (?P<last_seen>[^|]+) \| (?P<sample_id>FIND-\w+) \|$"
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
    import os

    dedup_ratio = (
        f"{raw_findings_count / len(clusters):.1f}" if clusters else "0.0"
    )
    header = _QUEUE_HEADER_TEMPLATE.format(
        project_name=project_name,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/test_triage.py -v`
Expected: PASS — 23 (prior) + 6 = 29 tests.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/triage.py tests/unit/fitness/test_triage.py
git commit -m "$(cat <<'EOF'
feat(fitness): write/read_queue_file — atomic markdown round-trip

Renders Clusters to a fitness-queue.md table (with header metadata
for dedup ratio, counts, timestamps) and parses the same file back
into Cluster records. Round-trip is lossless modulo the generation
timestamp. Atomic write via .tmp + os.replace.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: CLI — `dazzle fitness triage` and `dazzle fitness queue`

**Files:**
- Create: `src/dazzle/cli/fitness.py`
- Modify: `src/dazzle/cli/__init__.py` (register fitness_app)
- Create: `tests/unit/fitness/test_triage_cli.py`

- [ ] **Step 1: Write the failing smoke test**

Create `tests/unit/fitness/test_triage_cli.py`:

```python
"""Smoke tests for `dazzle fitness triage` and `dazzle fitness queue`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dazzle.cli.fitness import fitness_app

runner = CliRunner()


def _write_backlog(path: Path, rows_table: str) -> None:
    """Write a minimal fitness-backlog.md with the given rows block."""
    header = (
        "# Fitness Backlog\n\n"
        "Structured findings.\n\n"
        "| id | created | locus | axis | severity | persona | status | route | summary |\n"
        "|----|---------|-------|------|----------|---------|--------|-------|---------|\n"
    )
    path.write_text(header + rows_table)


def test_triage_writes_queue_file(tmp_path: Path) -> None:
    backlog = tmp_path / "dev_docs" / "fitness-backlog.md"
    backlog.parent.mkdir(parents=True)
    rows = (
        "| FIND-1 | 2026-04-13T19:00:00+00:00 | story_drift | coverage | medium | Admin | PROPOSED | soft | No matching story found |\n"
        "| FIND-2 | 2026-04-13T19:00:01+00:00 | story_drift | coverage | medium | Admin | PROPOSED | soft | No matching story found |\n"
        "| FIND-3 | 2026-04-13T19:00:02+00:00 | story_drift | coverage | high | User | PROPOSED | soft | Route mismatch |\n"
    )
    _write_backlog(backlog, rows)

    result = runner.invoke(
        fitness_app, ["triage", "--project", str(tmp_path)]
    )
    assert result.exit_code == 0, result.stdout

    queue_file = tmp_path / "dev_docs" / "fitness-queue.md"
    assert queue_file.exists()
    content = queue_file.read_text()
    assert "# Fitness Queue" in content
    assert "CL-" in content


def test_queue_json_output(tmp_path: Path) -> None:
    backlog = tmp_path / "dev_docs" / "fitness-backlog.md"
    backlog.parent.mkdir(parents=True)
    rows = (
        "| FIND-1 | 2026-04-13T19:00:00+00:00 | story_drift | coverage | high | Admin | PROPOSED | soft | Example finding |\n"
    )
    _write_backlog(backlog, rows)

    # Regenerate first.
    runner.invoke(fitness_app, ["triage", "--project", str(tmp_path)])

    # Now read as JSON.
    result = runner.invoke(
        fitness_app, ["queue", "--project", str(tmp_path), "--json"]
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["clusters_total"] == 1
    assert payload["raw_findings"] == 1
    assert len(payload["clusters"]) == 1
    assert payload["clusters"][0]["severity"] == "high"


def test_queue_missing_file_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(
        fitness_app, ["queue", "--project", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "fitness triage" in (result.stdout + result.stderr).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fitness/test_triage_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.cli.fitness'`.

- [ ] **Step 3: Create the CLI module**

Create `src/dazzle/cli/fitness.py`:

```python
"""`dazzle fitness triage` and `dazzle fitness queue` commands.

Thin wrappers over ``dazzle.fitness.triage``. ``triage`` regenerates
``<project>/dev_docs/fitness-queue.md`` from the current
``fitness-backlog.md``; ``queue`` is read-only and prints the existing
queue for humans or agents.

Design: docs/superpowers/specs/2026-04-14-fitness-triage-design.md
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dazzle.fitness.backlog import read_backlog
from dazzle.fitness.triage import (
    cluster_findings,
    read_queue_file,
    write_queue_file,
)

fitness_app = typer.Typer(
    name="fitness",
    help="Agent-Led Fitness Methodology queries and triage.",
    no_args_is_help=True,
)


def _backlog_path(project: Path) -> Path:
    return project / "dev_docs" / "fitness-backlog.md"


def _queue_path(project: Path) -> Path:
    return project / "dev_docs" / "fitness-queue.md"


def _find_examples(root: Path) -> list[Path]:
    examples_dir = root / "examples"
    if not examples_dir.exists():
        return []
    return [
        p
        for p in sorted(examples_dir.iterdir())
        if p.is_dir() and (p / "dazzle.toml").exists()
    ]


@fitness_app.command("triage")
def triage_command(
    project: Path | None = typer.Option(
        None, "--project", help="Project root (default: cwd)"
    ),
    all_examples: bool = typer.Option(
        False, "--all", help="Run triage for every examples/<name> under cwd"
    ),
    top: int = typer.Option(
        0,
        "--top",
        help="After regenerating, print the top N clusters to stdout (0 = silent)",
    ),
) -> None:
    """Dedupe + rank fitness findings into a fitness-queue.md file."""

    if all_examples:
        projects = _find_examples(Path.cwd())
        if not projects:
            typer.echo("[triage] no examples/ directory found", err=True)
            raise typer.Exit(code=1)
    else:
        projects = [project or Path.cwd()]

    for proj in projects:
        backlog = _backlog_path(proj)
        if not backlog.exists():
            typer.echo(
                f"[triage] {proj.name}: no fitness-backlog.md at {backlog}",
                err=True,
            )
            if all_examples:
                continue
            raise typer.Exit(code=1)

        rows = read_backlog(backlog)
        clusters = cluster_findings(rows)
        write_queue_file(
            _queue_path(proj),
            clusters,
            project_name=proj.name,
            raw_findings_count=len(rows),
        )
        ratio = (len(rows) / len(clusters)) if clusters else 0.0
        typer.echo(
            f"[triage] {proj.name}: {len(rows)} findings → "
            f"{len(clusters)} clusters ({ratio:.1f}×)"
        )
        typer.echo(f"[triage] wrote {_queue_path(proj)}")

        if top and clusters:
            typer.echo("")
            typer.echo(f"Top {top}:")
            for rank, c in enumerate(clusters[:top], start=1):
                typer.echo(
                    f"  {rank}. {c.cluster_id} {c.severity:8s} "
                    f"{c.locus:12s} {c.persona:16s} "
                    f"size={c.cluster_size:<3d} \"{c.canonical_summary}\""
                )


@fitness_app.command("queue")
def queue_command(
    project: Path | None = typer.Option(
        None, "--project", help="Project root (default: cwd)"
    ),
    top: int = typer.Option(10, "--top", help="Number of clusters to show"),
    as_json: bool = typer.Option(
        False, "--json", help="Emit JSON instead of the human-readable table"
    ),
) -> None:
    """Print the current fitness-queue.md for a project."""
    proj = project or Path.cwd()
    queue_file = _queue_path(proj)
    if not queue_file.exists():
        typer.echo(
            f"[queue] no fitness-queue.md at {queue_file} — "
            "run `dazzle fitness triage` first",
            err=True,
        )
        raise typer.Exit(code=1)

    clusters = read_queue_file(queue_file)
    shown = clusters[:top]

    if as_json:
        payload = {
            "project": proj.name,
            "queue_file": str(queue_file),
            "raw_findings": _header_int(queue_file, "Raw findings"),
            "clusters_total": len(clusters),
            "clusters": [
                {
                    "rank": i + 1,
                    "cluster_id": c.cluster_id,
                    "severity": c.severity,
                    "locus": c.locus,
                    "axis": c.axis,
                    "persona": c.persona,
                    "cluster_size": c.cluster_size,
                    "summary": c.canonical_summary,
                    "first_seen": c.first_seen.isoformat(),
                    "last_seen": c.last_seen.isoformat(),
                    "sample_id": c.sample_id,
                }
                for i, c in enumerate(shown)
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo(f"Fitness queue for {proj.name} (top {top} of {len(clusters)})")
    for rank, c in enumerate(shown, start=1):
        typer.echo(
            f"  {rank}. {c.cluster_id} {c.severity:8s} "
            f"{c.locus:12s} {c.persona:16s} "
            f"size={c.cluster_size:<3d} \"{c.canonical_summary}\""
        )


def _header_int(queue_file: Path, field: str) -> int:
    """Extract an integer field from the queue file header."""
    for line in queue_file.read_text().splitlines():
        if line.startswith(f"**{field}:**"):
            try:
                return int(line.split(":**", 1)[1].strip())
            except (IndexError, ValueError):
                return 0
    return 0
```

- [ ] **Step 4: Register fitness_app in the root CLI**

Read `src/dazzle/cli/__init__.py` to find the block of `app.add_typer(...)` calls (around line 273 where `db_app` is registered and line 283 where `e2e_app` is registered). Add a registration for `fitness_app`:

First add the import, alphabetically between `feedback` and `kg`:

```python
from dazzle.cli.feedback import feedback_app  # noqa: E402
from dazzle.cli.fitness import fitness_app  # noqa: E402
from dazzle.cli.kg import kg_app  # noqa: E402
```

Then add the `add_typer` call near the other typer registrations, alphabetically after `feedback_app`:

```python
app.add_typer(fitness_app, name="fitness")
```

- [ ] **Step 5: Run CLI smoke tests**

Run: `pytest tests/unit/fitness/test_triage_cli.py -v`
Expected: PASS — 3 tests.

Also verify the command is visible:

Run: `dazzle fitness --help`
Expected: shows `triage` and `queue` subcommands.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/fitness.py src/dazzle/cli/__init__.py tests/unit/fitness/test_triage_cli.py
git commit -m "$(cat <<'EOF'
feat(cli): add `dazzle fitness triage` + `dazzle fitness queue`

New fitness_app Typer wired into the root dazzle CLI. `triage`
regenerates <project>/dev_docs/fitness-queue.md from the existing
fitness-backlog.md (with --all for every example under cwd and
--top N to print the ranked head). `queue` is read-only — prints
the existing queue as a human-readable table or --json.

Both commands exit 1 with an actionable message when the underlying
file is missing. ADR-0002 maintained: only the CLI can regenerate.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: MCP handler

**Files:**
- Create: `src/dazzle/mcp/server/handlers/fitness.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`
- Create: `tests/unit/mcp/test_fitness_handler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/mcp/test_fitness_handler.py`:

```python
"""Unit tests for the mcp__dazzle__fitness handler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.mcp.server.handlers.fitness import fitness_queue_handler


def _write_queue(
    path: Path,
    *,
    project: str = "demo",
    raw: int = 5,
    clusters: int = 1,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Fitness Queue\n\n"
        "Ranked, deduped view.\n\n"
        f"**Project:** {project}\n"
        "**Generated:** 2026-04-14T00:00:00Z\n"
        f"**Raw findings:** {raw}\n"
        f"**Clusters:** {clusters}\n"
        f"**Dedup ratio:** {raw / clusters:.1f}×\n\n"
        "| rank | cluster_id | severity | locus | axis | persona | size | summary | first_seen | last_seen | sample_id |\n"
        "|------|-----------|----------|-------|------|---------|------|---------|------------|-----------|-----------|\n"
        "| 1 | CL-abc12345 | high | story_drift | coverage | Admin | 5 | example summary | 2026-04-13T19:00:00+00:00 | 2026-04-13T20:00:00+00:00 | FIND-xyz |\n"
    )


def test_queue_operation_returns_json(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_queue(project_root / "dev_docs" / "fitness-queue.md")

    result = fitness_queue_handler(
        tmp_path,
        {"project_root": str(project_root), "top": 10},
    )
    payload = json.loads(result)
    assert payload["project"] == "project"
    assert payload["raw_findings"] == 5
    assert payload["clusters_total"] == 1
    assert len(payload["clusters"]) == 1
    assert payload["clusters"][0]["cluster_id"] == "CL-abc12345"
    assert payload["clusters"][0]["severity"] == "high"


def test_queue_missing_file_returns_error(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = fitness_queue_handler(
        tmp_path,
        {"project_root": str(project_root), "top": 10},
    )
    payload = json.loads(result)
    assert "error" in payload
    assert "fitness triage" in payload["error"]


def test_queue_respects_top_parameter(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    queue_file = project_root / "dev_docs" / "fitness-queue.md"
    queue_file.parent.mkdir(parents=True)
    queue_file.write_text(
        "# Fitness Queue\n\n"
        "**Project:** project\n"
        "**Generated:** 2026-04-14T00:00:00Z\n"
        "**Raw findings:** 3\n"
        "**Clusters:** 3\n"
        "**Dedup ratio:** 1.0×\n\n"
        "| rank | cluster_id | severity | locus | axis | persona | size | summary | first_seen | last_seen | sample_id |\n"
        "|------|-----------|----------|-------|------|---------|------|---------|------------|-----------|-----------|\n"
        "| 1 | CL-000aaa11 | high | story_drift | coverage | A | 1 | first | 2026-04-13T19:00:00+00:00 | 2026-04-13T19:00:00+00:00 | FIND-1 |\n"
        "| 2 | CL-000bbb22 | medium | story_drift | coverage | B | 1 | second | 2026-04-13T19:00:00+00:00 | 2026-04-13T19:00:00+00:00 | FIND-2 |\n"
        "| 3 | CL-000ccc33 | low | story_drift | coverage | C | 1 | third | 2026-04-13T19:00:00+00:00 | 2026-04-13T19:00:00+00:00 | FIND-3 |\n"
    )

    result = fitness_queue_handler(
        tmp_path,
        {"project_root": str(project_root), "top": 2},
    )
    payload = json.loads(result)
    assert len(payload["clusters"]) == 2
    assert payload["clusters_total"] == 3  # total preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/mcp/test_fitness_handler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.mcp.server.handlers.fitness'`.

- [ ] **Step 3: Create the handler module**

Create `src/dazzle/mcp/server/handlers/fitness.py`:

```python
"""MCP handler for the fitness triage queue.

Read-only per ADR-0002. Regeneration happens via CLI
(`dazzle fitness triage`); this handler only parses the existing
fitness-queue.md and returns its contents as JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dazzle.fitness.triage import read_queue_file
from dazzle.mcp.server.handlers.common import wrap_handler_errors

_HEADER_RAW_RE = re.compile(r"^\*\*Raw findings:\*\*\s*(\d+)", re.MULTILINE)


def _parse_raw_findings(queue_file: Path) -> int:
    """Extract the 'Raw findings' count from the queue file header."""
    try:
        text = queue_file.read_text()
    except OSError:
        return 0
    m = _HEADER_RAW_RE.search(text)
    return int(m.group(1)) if m else 0


@wrap_handler_errors
def fitness_queue_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Return the ranked fitness queue for a project as JSON.

    Args:
        project_path: unused in this handler (MCP passes cwd)
        args: {
            "project_root": path to the example app,
            "top": max clusters to return (default 10),
        }
    """
    explicit = args.get("project_root")
    if not explicit:
        return json.dumps(
            {
                "error": "project_root is required",
                "project_root": None,
            },
            indent=2,
        )
    project_root = Path(explicit)
    queue_file = project_root / "dev_docs" / "fitness-queue.md"

    if not queue_file.exists():
        return json.dumps(
            {
                "error": "no fitness queue — run 'dazzle fitness triage' first",
                "project_root": str(project_root),
            },
            indent=2,
        )

    clusters = read_queue_file(queue_file)
    top = int(args.get("top", 10))
    shown = clusters[:top]
    raw_findings = _parse_raw_findings(queue_file)

    payload = {
        "project": project_root.name,
        "queue_file": str(queue_file),
        "raw_findings": raw_findings,
        "clusters_total": len(clusters),
        "clusters": [
            {
                "rank": i + 1,
                "cluster_id": c.cluster_id,
                "severity": c.severity,
                "locus": c.locus,
                "axis": c.axis,
                "persona": c.persona,
                "cluster_size": c.cluster_size,
                "summary": c.canonical_summary,
                "first_seen": c.first_seen.isoformat(),
                "last_seen": c.last_seen.isoformat(),
                "sample_id": c.sample_id,
            }
            for i, c in enumerate(shown)
        ],
    }
    return json.dumps(payload, indent=2)
```

- [ ] **Step 4: Register the handler in handlers_consolidated.py**

Read `src/dazzle/mcp/server/handlers_consolidated.py`. Find the block around the e2e handler registration (the section added in commit `6de9375c`). Add a new block AFTER it:

```python
# =============================================================================
# Fitness Triage Handler
# =============================================================================

_MOD_FITNESS = "dazzle.mcp.server.handlers.fitness"

handle_fitness: Callable[[dict[str, Any]], Any] = _make_project_handler_async(
    "fitness",
    {
        "queue": f"{_MOD_FITNESS}:fitness_queue_handler",
    },
)
```

Then find the handler dispatch dict (the one containing `"e2e": handle_e2e`) and add:

```python
"fitness": handle_fitness,
```

- [ ] **Step 5: Register the tool in tools_consolidated.py**

Read `src/dazzle/mcp/server/tools_consolidated.py`. Find the `Tool(name="e2e", ...)` block. Add AFTER it:

```python
        # =====================================================================
        # Fitness Triage (read-only — regenerate via CLI)
        # =====================================================================
        Tool(
            name="fitness",
            description=(
                "Agent-Led Fitness Methodology queries (read-only). "
                "Operations: queue (ranked deduped finding clusters for "
                "a project). To regenerate the queue, use CLI: "
                "dazzle fitness triage."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["queue"],
                        "description": "Operation to perform",
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Path to an example app project",
                    },
                    "top": {
                        "type": "integer",
                        "description": "Max clusters to return (default 10)",
                        "default": 10,
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation", "project_root"],
            },
        ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/mcp/test_fitness_handler.py -v`
Expected: PASS — 3 tests.

Run: `python -c "from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools; names = [t.name for t in get_all_consolidated_tools()]; assert 'fitness' in names, names; print('OK')"`
Expected: prints `OK`.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/mcp/server/handlers/fitness.py \
        src/dazzle/mcp/server/handlers_consolidated.py \
        src/dazzle/mcp/server/tools_consolidated.py \
        tests/unit/mcp/test_fitness_handler.py
git commit -m "$(cat <<'EOF'
feat(mcp): add read-only mcp__dazzle__fitness tool (queue op)

New MCP tool exposing the fitness triage queue to agents. Single
operation: queue(project_root, top) returns the ranked cluster list
as JSON. Gracefully returns an error payload (not raises) when the
fitness-queue.md file is missing or malformed — agents are told to
run `dazzle fitness triage` first. ADR-0002 maintained: regeneration
happens in CLI only.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: User reference documentation

**Files:**
- Create: `docs/reference/fitness-triage.md`

- [ ] **Step 1: Write the reference doc**

Create `docs/reference/fitness-triage.md`:

````markdown
# Fitness Triage — User Reference

Fitness triage turns a flat `fitness-backlog.md` (thousands of
near-duplicate findings) into a ranked, deduped `fitness-queue.md` that
agents and humans can read top-down. Use it to pick what to work on
next after a fitness run.

## Quick start

```bash
# Regenerate the queue for a single example
cd examples/support_tickets
dazzle fitness triage

# Regenerate for every example under the current directory
dazzle fitness triage --all

# Read the top 10 as JSON (agent-friendly)
dazzle fitness queue --top 10 --json
```

## How it works

1. `dazzle fitness triage` parses `dev_docs/fitness-backlog.md` using
   the existing fitness reader.
2. Each raw finding is mapped to a dedupe key —
   `(locus, axis, canonicalised_summary, persona)` — where
   `canonicalised_summary` is lowercased, whitespace-collapsed, and
   truncated to 120 characters.
3. Findings with the same key collapse into a single **cluster**.
   Each cluster has a stable `cluster_id` of the form `CL-<8 hex>`
   derived from a SHA-256 of the dedupe key.
4. Clusters are sorted by
   `(-severity_rank, -cluster_size, cluster_id)` — highest severity
   first, biggest clusters within a severity band first, alphabetical
   tiebreaker.
5. The result is written atomically to `dev_docs/fitness-queue.md`.

## File layout

```
examples/<app>/dev_docs/
    fitness-backlog.md   # raw findings, written by the fitness engine
    fitness-queue.md     # deduped + ranked view, written by triage
```

The queue file is always a pure projection of the backlog. It's safe
to delete; `dazzle fitness triage` will regenerate it from scratch.

## Commands

```bash
dazzle fitness triage [--project <path>] [--all] [--top N]
    # Regenerate fitness-queue.md. Writes the file; optionally prints
    # the top N clusters to stdout. Exit 1 if the backlog is missing.

dazzle fitness queue [--project <path>] [--top N] [--json]
    # Read-only: prints the existing queue. Exit 1 if the file doesn't
    # exist (run `dazzle fitness triage` first). `--json` for agents.
```

## MCP surface

Agents can query the queue without running the CLI:

```
mcp__dazzle__fitness queue(
    project_root="examples/support_tickets",
    top=10,
)
```

Returns the same JSON shape as `dazzle fitness queue --json`. This is
read-only; to regenerate the queue, agents call
`dazzle fitness triage` (shell-out), not an MCP operation.

## Referencing clusters in commit messages

Cluster IDs are stable across regenerations, so they make good commit
message anchors:

```
fix: resolve CL-a7f3b2c1 story_drift for Administrator

The Administrator persona was hitting "no matching story found" on
the /app/tickets/assign route because the DSL had no story covering
admin-side ticket reassignment. Added the missing story block and
re-ran fitness to confirm.
```

After the fix lands and the next fitness cycle runs, the cluster
either disappears (all members got fixed) or shrinks (partial fix),
and the queue re-ranks naturally.

## What triage deliberately does NOT do

- **Classify** findings as noise vs. real — every distinct cluster
  appears in the queue. Agents decide what to work on.
- **Investigate** individual clusters — reading the underlying
  evidence envelope in `fitness-backlog.md` (via `sample_id`) is
  the agent's job.
- **Track status** — the queue is ephemeral; regenerate after each
  fitness cycle and trust the new numbers. Git log + commit messages
  are the state history.
- **Auto-run after fitness cycles** — triage is a manual CLI call.
  Agents can chain it themselves via `/loop` if they want a fresh
  queue without intervention.

## Design notes

See `docs/superpowers/specs/2026-04-14-fitness-triage-design.md` for
the full design, including the rationale for the dedupe key choice,
the ranking formula, and what's deferred to future investigator and
actor subsystems.
````

- [ ] **Step 2: Commit**

```bash
git add docs/reference/fitness-triage.md
git commit -m "$(cat <<'EOF'
docs(fitness): user reference for dazzle fitness triage + queue

Explains the rough-rubric design principle, the dedupe key, the CLI
and MCP surfaces, and how cluster IDs are referenced in commit
messages. Points at the design spec for rationale details.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

**Spec coverage:**

- Dedupe model (`DedupeKey`) → Task 2 ✓
- Ranking model (`sort_key`) → Task 3 ✓
- Architecture (triage.py, cli/fitness.py, mcp/.../fitness.py) → Tasks 1–6 ✓
- Data flow (parse → dedupe → rank → serialize) → Tasks 1–4 ✓
- Output file format (queue.md header + table) → Task 4 ✓
- CLI surface (triage + queue) → Task 5 ✓
- MCP surface (queue op, read-only) → Task 6 ✓
- Error handling (missing file, malformed row, unknown severity) → Tasks 3+4+5+6 ✓
- Testing strategy (14 unit + 2 smoke) → Tasks 1–6 ✓
- User reference doc → Task 7 ✓

**Type/name consistency spot-checks:**

- `DedupeKey(locus, axis, canonical_summary, persona)` — same field names used across Tasks 2, 3, 4.
- `Cluster` has `cluster_id, locus, axis, canonical_summary, persona, severity, cluster_size, first_seen, last_seen, sample_id` — consistent across Tasks 3, 4, 6.
- `cluster_id` format `CL-<8 hex>` — consistent across spec, Task 2, Task 4 regex, Task 6 fixtures.
- `write_queue_file(path, clusters, *, project_name, raw_findings_count)` — same signature used in Task 4 test, Task 5 CLI.
- `read_queue_file(path) -> list[Cluster]` — same signature used in Task 4 test, Task 5 CLI, Task 6 handler.
- `fitness_queue_handler(project_path, args)` — matches the MCP handler dispatch pattern seen in other handlers.

**Placeholder scan:** no TBDs, no "similar to Task N", no "add error handling later". Every step contains complete code.

**Scope check:** single plan, 7 tasks, ~400 LoC of production + ~450 LoC of tests + ~180 LoC of docs. Comparable in size to the fitness v1.0.1 plan. Fits one implementation pass.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-fitness-triage-plan.md`.

Two execution options:
1. **Subagent-driven** (recommended) — fresh subagent per task + two-stage review
2. **Inline execution** — batch tasks in this session with checkpoints
