# Fitness Triage — Design

**Date:** 2026-04-14
**Status:** Draft — user review pending
**Author:** Dazzle core + Claude (brainstorm)
**Related:**
- `docs/reference/fitness-methodology.md` — Agent-Led Fitness Methodology v1
- `docs/superpowers/specs/2026-04-14-e2e-environment-strategy-design.md` — the e2e harness that produces the raw findings
- `src/dazzle/fitness/backlog.py` — existing flat-file backlog reader/writer this spec consumes
- ADR-0002 — MCP/CLI boundary (stateless reads vs process operations)

---

## Goal

Give agents a ranked, deduped view of fitness findings so they can pick the next actionable item without reading thousands of raw rows. Transform flat `examples/<app>/dev_docs/fitness-backlog.md` files (today: ~11,750 lines across 5 examples, most near-duplicates) into `fitness-queue.md` files that surface **roughly 10–25 distinct clusters per example** in priority order.

The design principle throughout: **rough rubric beats perfect algorithm**. A 5-minute heuristic that keeps agents productively employed is worth more than a 5-hour optimisation that blocks real work.

---

## Non-goals

- **Investigation** — deciding what a cluster *means*, what the right fix is, or whether a cluster is noise. That's a separate future subsystem.
- **Action** — proposing, applying, or verifying fixes. Separate future subsystem.
- **State tracking** — no "owner", no "claimed by", no lease protocol. The queue is ephemeral; the backlog is durable; git log + commit messages are the state history.
- **Classification / noise filtering** — every dedupe-key-distinct cluster appears in the queue regardless of whether a human would consider it actionable. Agents read the queue and decide.
- **Auto-invocation** — triage is a manual CLI call. The fitness engine doesn't trigger it after Phase B runs (in v1). Agents can chain it themselves if they want a fresh queue.
- **Cross-project clustering** — a finding in `support_tickets` and an identically-worded finding in `ops_dashboard` stay distinct (they live in separate backlog files and are written to separate queue files). The `--all` flag produces a merged ranked *view*, not a merged cluster.
- **Perfect summary matching** — no fuzzy matching, no embedding similarity, no NLP. Exact match on a canonicalised-whitespace-lowercase-truncated-at-120-chars summary. Good enough.

---

## Dedupe model

A cluster is defined by the tuple:

```python
DedupeKey = (locus, axis, canonical_summary, persona)
```

Where:
- `locus ∈ {implementation, story_drift, spec_stale, lifecycle}` — from the existing `Finding` model
- `axis ∈ {coverage, conformance}` — from the existing `Finding` model
- `canonical_summary` — `" ".join(summary.strip().lower().split())[:120]` (lowercase, strip, collapse whitespace, truncate to 120 chars)
- `persona` — from the existing `Finding` model, preserved verbatim

**Cluster ID:** `cluster_id = "CL-" + sha256(dedupe_key_repr)[:8]` — 8-hex suffix so it fits cleanly in table cells and commit messages ("`fix: resolve CL-a7f3 story_drift for Administrator`").

**Why this key:** It's the smallest set of fields that preserves the "who is affected" dimension (persona) while collapsing the obvious duplicates (same route, same drift type, same message). Rough target compression ratio: ~7–10×.

**Alternatives considered and rejected:**
- `(locus, axis, summary)` — loses persona dimension, so agents can't target persona-specific fixes.
- `(locus, axis, capability_ref)` — `capability_ref` is often missing or noisy, making the key unreliable.
- Content-hash over `evidence_embedded.expected_ledger_step` — catches literal duplicates but misses semantic duplicates ("No matching story found" across different routes/personas).
- Fuzzy summary matching — introduces tuning complexity for marginal gain.

---

## Ranking model

```python
SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}

def sort_key(cluster: Cluster) -> tuple[int, int, str]:
    return (
        -SEVERITY_RANK[cluster.severity],
        -cluster.cluster_size,
        cluster.cluster_id,
    )
```

Negated so a plain `sorted()` call orders by descending severity, then descending cluster size, then lexicographic cluster ID (stable tiebreaker).

**Severity aggregation within a cluster:** max of member severities. One high-severity instance in a mostly-medium cluster elevates the whole cluster. Alternatives (average, min) would bury outliers.

**Rationale for this specific ranking:**
- A critical singleton still beats any cluster at lower severity (rare but important wins priority)
- Within a severity band, bigger clusters win (most agent-effort-per-fix pays off on ubiquitous drift)
- The `cluster_id` tiebreaker is deterministic so ordering is stable across regenerations — agents that pick "the third cluster" get the same cluster every run

**Knobs deliberately omitted:**
- No weighting by `route` (hard vs soft)
- No weighting by `axis` (coverage vs conformance)
- No decay over time (old findings don't auto-deprioritise)
- No confidence factor for `low_confidence` findings

All four are future-friendly — the `sort_key` function is one tuple definition, and adding a field to the tuple is a one-line diff. We start simple and add weighting only when we can point to a specific case where the simple rule misranks.

---

## Architecture

### New package structure

```
src/dazzle/fitness/
  ├── triage.py             # NEW — ~200 lines, single file
  ├── backlog.py            # existing — reused via read_backlog()
  ├── models.py             # existing — Finding, Severity, Locus, Axis
  └── ...

src/dazzle/cli/
  └── fitness.py            # NEW — fitness_app Typer with `triage` + `queue`

src/dazzle/mcp/server/
  ├── handlers/
  │   └── fitness.py        # NEW — one handler: queue
  ├── handlers_consolidated.py  # MODIFY — register handle_fitness
  └── tools_consolidated.py     # MODIFY — add Tool(name="fitness", ...)

tests/unit/fitness/
  └── test_triage.py        # NEW — ~14 tests

tests/fixtures/fitness_triage/
  ├── empty.md              # NEW — just the header
  ├── small.md              # NEW — 10 rows, 3 distinct keys
  └── malformed.md          # NEW — mixed valid + malformed rows
```

**Why single-file `triage.py`:** clustering + ranking + I/O comes to ~200 lines. Splitting into `clustering.py` + `ranking.py` + `io.py` is premature abstraction for v1. If it grows past 400 lines in follow-ups, split at that point.

**Why colocated in `dazzle.fitness`:** `triage` reads `Finding`-derived dicts via `read_backlog()` from the same package. Keeping it next to its data source avoids cross-package hops.

**Why new `cli/fitness.py` and `mcp/.../fitness.py`:** neither a fitness CLI typer nor a fitness MCP tool exists today. Creating both from scratch is cleaner than shoehorning into an existing namespace. Future investigator/actor subsystems will add operations to the same files.

### ADR-0002 boundary

- **CLI `dazzle fitness triage`** — process op (writes `fitness-queue.md`). Never in MCP.
- **CLI `dazzle fitness queue`** — read op for humans (prints the queue).
- **MCP `mcp__dazzle__fitness queue`** — read op for agents (returns JSON). Never regenerates; if the file is missing it returns an error suggesting `dazzle fitness triage`.

---

## Data flow

```
fitness-backlog.md                        fitness-queue.md
    │                                            ▲
    │ read_backlog() → list[dict]                │ write_queue_file()
    │                                            │
    ▼                                            │
┌──────────────────────────────────────────┐     │
│ TRIAGE PIPELINE                          │     │
│                                          │     │
│ 1. parse rows via existing               │     │
│    read_backlog() helper                 │     │
│ 2. compute dedupe key per row:           │     │
│    (locus, axis, canonical(summary),     │     │
│     persona)                             │     │
│ 3. group rows by dedupe key              │     │
│ 4. build Cluster records:                │     │
│      cluster_id = sha256(key)[:8]        │     │
│      severity = max(member severities)   │     │
│      cluster_size = len(members)         │     │
│      first_seen = min(member created)    │     │
│      last_seen = max(member created)     │     │
│      sample_id = members[0]["id"]        │     │
│ 5. sort by                               │     │
│    (-severity_rank, -size, cluster_id)   │     │
│                                          │     │
└──────────────────────────────────────────┘─────┘
```

### Steps in detail

**Step 1 — Parse.** Call existing `read_backlog(path)`. Returns `list[dict[str, str]]` with keys `id, created, locus, axis, severity, persona, status, route, summary`. Malformed rows are silently skipped (existing helper behaviour — inherited).

**Step 2 — Canonicalise summary.**
```python
def canonicalize_summary(s: str) -> str:
    return " ".join(s.strip().lower().split())[:120]
```
Matches the write-side 120-char truncation in `_finding_to_row`.

**Step 3 — Group.** `defaultdict(list)` keyed on `DedupeKey`. O(n) in finding count.

**Step 4 — Build `Cluster` records.**

```python
@dataclass(frozen=True)
class Cluster:
    cluster_id: str
    locus: str
    axis: str
    canonical_summary: str
    persona: str
    severity: str
    cluster_size: int
    first_seen: datetime
    last_seen: datetime
    sample_id: str        # id of the first raw finding — drill-down handle

    @property
    def sort_key(self) -> tuple[int, int, str]:
        return (-SEVERITY_RANK[self.severity], -self.cluster_size, self.cluster_id)
```

The `sample_id` lets agents look up a representative raw finding in the backlog for full evidence drill-down.

**Step 5 — Sort.** Single `sorted(clusters, key=lambda c: c.sort_key)` call.

### Regeneration semantics

- **Overwrite.** Every `dazzle fitness triage` call rewrites the whole queue file. No merging, no append.
- **Atomic write.** Write to `fitness-queue.md.tmp`, then `os.replace` to `fitness-queue.md`. Readers never see partial files.
- **Idempotency.** Running triage twice with an unchanged backlog produces a byte-identical queue file (modulo the `Generated:` timestamp in the header).
- **Stable cluster IDs.** Same dedupe-key → same cluster ID → same position in the sorted output.

---

## Output file format

`examples/<app>/dev_docs/fitness-queue.md`:

```markdown
# Fitness Queue

Ranked, deduped view of `fitness-backlog.md`. Regenerated by
`dazzle fitness triage`. Re-run after each fitness cycle to refresh.

**Project:** support_tickets
**Generated:** 2026-04-13T21:07:45Z
**Raw findings:** 138
**Clusters:** 19
**Dedup ratio:** 7.3×

| rank | cluster_id | severity | locus | axis | persona | size | summary | first_seen | last_seen | sample_id |
|------|-----------|----------|-------|------|---------|------|---------|------------|-----------|-----------|
| 1 | CL-a7f3b2c1 | high | spec_stale | coverage | Administrator | 12 | no matching story found | 2026-04-13T19:13 | 2026-04-13T20:55 | FIND-5778be8a |
| 2 | CL-b9e14d88 | medium | story_drift | coverage | Support Staff | 18 | no matching story found | 2026-04-13T19:13 | 2026-04-13T20:55 | FIND-5bd06764 |
…
```

The header metadata (`Raw findings`, `Clusters`, `Dedup ratio`) gives humans a quick sanity check.

---

## CLI surface

### `dazzle fitness triage` — regenerator

```bash
dazzle fitness triage                         # cwd
dazzle fitness triage --project <path>        # specific project
dazzle fitness triage --all                   # all examples/* under cwd
dazzle fitness triage --top 10                # write file + print top 10 to stdout
```

**Human-format stdout on `--top N`:**
```
[triage] support_tickets: 138 findings → 19 clusters (7.3×)
[triage] wrote examples/support_tickets/dev_docs/fitness-queue.md

Top 10:
  1. CL-a7f3b2c1 high     story_drift  Administrator  size=12  "no matching story found"
  2. CL-b9e14d88 medium   story_drift  Support Staff  size=18  "no matching story found"
  …
```

**Exit codes:** 0 on success, 1 if `fitness-backlog.md` missing, 2 on unrecoverable error.

### `dazzle fitness queue` — reader

```bash
dazzle fitness queue                          # cwd
dazzle fitness queue --project <path>         # specific project
dazzle fitness queue --top 5                  # print top 5 (default 10)
dazzle fitness queue --json                   # JSON output for agents
```

**Read-only.** If `fitness-queue.md` doesn't exist, exits 1 with a message suggesting `dazzle fitness triage`. Never auto-regenerates.

**JSON shape:**
```json
{
  "project": "support_tickets",
  "generated": "2026-04-13T21:07:45Z",
  "raw_findings": 138,
  "clusters_total": 19,
  "clusters": [
    {
      "rank": 1,
      "cluster_id": "CL-a7f3b2c1",
      "severity": "high",
      "locus": "spec_stale",
      "axis": "coverage",
      "persona": "Administrator",
      "cluster_size": 12,
      "summary": "no matching story found",
      "first_seen": "2026-04-13T19:13:10+00:00",
      "last_seen": "2026-04-13T20:55:22+00:00",
      "sample_id": "FIND-5778be8a"
    }
  ]
}
```

---

## MCP surface

**Tool name:** `mcp__dazzle__fitness`
**Read-only** per ADR-0002.

### Operations (v1)

```
queue(project_root: str, top: int = 10) -> QueueRecord
```

Reads `<project_root>/dev_docs/fitness-queue.md` via `triage.read_queue_file()`. Returns the parsed shape as JSON. Never triggers regeneration.

**Error paths:**
- File missing → `{"error": "no fitness queue — run 'dazzle fitness triage' first", "project_root": "..."}`
- File malformed → `{"error": "could not parse fitness-queue.md: <reason>", "project_root": "..."}`
- Otherwise → same JSON shape as `dazzle fitness queue --json`.

### Deliberately NOT in MCP (v1)

- `triage` (regenerate) — CLI-only, process op per ADR-0002.
- `investigate` — future feature, separate design.
- `claim` / `release` — no state tracking in v1.

Future investigator and actor operations will land in the same `fitness` tool namespace.

---

## Error handling

| Scenario | Handling |
|---|---|
| `fitness-backlog.md` missing | `triage` exits 1 with a clear path. `queue` exits 1 suggesting `triage` first. |
| `fitness-backlog.md` empty | Writes empty queue. Exit 0. |
| Single malformed row | Skipped silently (inherited from `read_backlog`). Logged at DEBUG. |
| All rows malformed | Empty queue, exit 0. |
| Unknown `locus` / `axis` | Passes through verbatim into dedupe key. No validation. |
| Unknown `severity` | Falls back to severity rank 0. Logged at WARN. Cluster still builds. |
| Unparseable `created` timestamp | Falls back to `datetime.fromtimestamp(0)`. Logged at DEBUG. |
| Atomic rename fails on write | Exits 2 with the OSError. `.tmp` file remains for diagnosis. |
| MCP: file missing | Returns `{"error": ..., "project_root": ...}`. Never raises. |
| MCP: file malformed | Returns `{"error": ..., "project_root": ...}`. Never raises. |

**Guiding principle:** the triage pipeline is a *view* over the backlog. It degrades gracefully on anything short of a filesystem error.

---

## Testing strategy

Single test file: `tests/unit/fitness/test_triage.py`. ~14 tests, target runtime <1 second.

### Unit tests

1. `canonicalize_summary` — lowercase, strip, collapse whitespace, truncate at 120 chars.
2. `dedupe_key_for` — returns expected `(locus, axis, canonical, persona)` tuple.
3. `compute_cluster_id` — deterministic 8-char hex; identical keys → identical IDs; different keys → different IDs.
4. `cluster_findings` — 5 rows with 3 distinct keys produce 3 clusters.
5. `cluster_findings` — rows with identical keys aggregate: `cluster_size=N`, `severity=max`, `first_seen=min`, `last_seen=max`.
6. `cluster_findings` — severity aggregation: medium + high + low → `high`.
7. `cluster_findings` — sort order: `(high, 1) < (high, 5) < (critical, 1)`.
8. `cluster_findings` — tiebreaker is `cluster_id` lexicographic (stable).
9. `write_queue_file` → `read_queue_file` round trip: same clusters in same order.
10. `write_queue_file` atomic write: simulated `os.replace` failure leaves no canonical file.
11. `read_queue_file` on missing file → `[]`.
12. `read_queue_file` on corrupt file → `[]` + WARN log.

Plus two integration smoke tests:

13. CLI smoke: `dazzle fitness triage --project <fixture>` writes `fitness-queue.md` with expected content.
14. MCP handler smoke: `queue` operation on a fixture project returns the expected JSON shape.

### Fixtures

`tests/fixtures/fitness_triage/`:
- `empty.md` — just the header, no rows.
- `small.md` — 10 rows with 3 distinct dedupe keys.
- `malformed.md` — mixed valid + malformed rows.

### Out of scope for tests

- Performance / scale (11,750 lines parses in <100ms; no perf test needed)
- MCP dispatch end-to-end via a real MCP client (handlers are unit-testable via direct import)
- Cross-example aggregation (`--all`) — smoke-tested manually, not with fixtures

---

## Implementation order

Suggested sequence for writing-plans:

1. `src/dazzle/fitness/triage.py` — core dataclasses + pure functions (canonicalize, dedupe_key_for, compute_cluster_id, cluster_findings).
2. `src/dazzle/fitness/triage.py` — I/O functions (write_queue_file, read_queue_file).
3. `tests/unit/fitness/test_triage.py` — unit tests (1–12) + fixtures.
4. `src/dazzle/cli/fitness.py` — `fitness_app` Typer with `triage` and `queue` commands.
5. `src/dazzle/cli/__init__.py` — register `fitness_app` in the root Typer.
6. CLI smoke test.
7. `src/dazzle/mcp/server/handlers/fitness.py` — `queue` handler.
8. `handlers_consolidated.py` + `tools_consolidated.py` — register the `fitness` MCP tool.
9. MCP handler test.
10. Documentation: `docs/reference/fitness-triage.md` (user-facing reference).

Each step commits independently.

---

## Risks

1. **Canonicalisation too strict** — `canonicalize_summary` truncates at 120 chars. Two findings whose full summaries diverge after char 120 but match before would collapse into one cluster. Mitigation: the raw backlog's `_finding_to_row` already truncates at 120, so we're matching existing truncation.
2. **Canonicalisation too loose** — lowercase + whitespace collapse might over-dedupe. If we hit this, tighten to case-sensitive + truncate-only. Monitorable by the `dedup ratio` number in the queue header.
3. **Severity aggregation surprises** — one stray `critical` member elevates a mostly-medium cluster. By design, but could misrank if severities are noisy. Mitigation: severity levels are from an upstream validator, so noise should be rare.
4. **Stable cluster IDs across schema changes** — if the `Finding` schema gains a new field relevant to dedupe, cluster IDs shift en masse. Acceptable for v1; future schema changes can handle migration separately.
5. **Concurrency on regeneration** — two agents calling `dazzle fitness triage` simultaneously both write `fitness-queue.md.tmp` then rename. Last writer wins, but `os.replace` is atomic per-OS so the reader never sees a half-file. Mitigation: skip lock file for v1 (low risk in single-developer workflow).

---

## Summary

- **`dazzle fitness triage`** parses `fitness-backlog.md`, dedupes into clusters via `(locus, axis, canonical_summary, persona)`, ranks by `(severity, cluster_size)`, writes `fitness-queue.md`.
- **`dazzle fitness queue`** reads the queue file for humans (pretty-print) or agents (`--json`).
- **`mcp__dazzle__fitness queue`** is the read-only MCP surface for agents.
- **No state tracking, no classification, no auto-invocation.** Regenerate after each Phase B, trust the numbers.
- **~200 lines of new code** + 14 tests. Lands in one implementation plan.
- Investigation and action are explicit non-goals for v1 — separate brainstorms once we see how the queue behaves in practice.
