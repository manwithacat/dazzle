# Fitness Investigator Subsystem — Design Spec

**Date:** 2026-04-14
**Status:** Approved for implementation planning
**Depends on:** Fitness Triage Subsystem (v0.54.4+, `src/dazzle/fitness/triage.py`), DazzleAgent framework (`src/dazzle/agent/core.py`), fitness engine + findings model (`src/dazzle/fitness/models.py`)
**Supersedes (eventually):** `src/dazzle/fitness/corrector.py` — legacy single-finding fix generator, to be audited and deleted in a follow-up ship after Phase 1 lands

## Goal

Build an agent-led subsystem that takes a ranked cluster from the fitness queue and produces a structured `Proposal` on disk. The proposal describes how to fix the cluster, what alternatives were considered, and how to verify the fix worked — enough detail for a future actor subsystem to apply it mechanically. The investigator is read-only at the codebase level; the only thing it writes is its own proposal files under `.dazzle/fitness-proposals/`.

The end state for the whole loop is **Option 2** in the brainstorm — fully autonomous investigator → actor → verify → commit. This spec ships **Option 3**: investigator-only, proposals on disk. The actor is a separate spec that will consume the proposal files produced here. The reason for shipping investigator first is that proposal quality is the bottleneck for the whole autonomous loop, and we need to measure it before wiring up the destructive apply path.

## Non-goals (explicit)

- **Not in scope:** applying proposals, running Phase B to verify fixes, reverting bad fixes, writing commits. Those belong to the actor subsystem (separate spec, separate ship).
- **Not in scope:** human review UI, proposal ranking, batch proposal merging, automatic re-investigation on proposal staleness.
- **Not in scope:** refactoring `corrector.py`, extracting shared primitives, touching the fitness engine, changing the triage output format. The investigator is purely additive at the module boundary.
- **Not in scope:** mutating `fitness-queue.md` or `fitness-backlog.md`. Those are read-only inputs. Only the triage subsystem writes the queue; only the fitness engine writes the backlog.

## Architecture overview

New package: `src/dazzle/fitness/investigator/`. Six modules, one CLI touchpoint, and one documentation file.

```
src/dazzle/fitness/investigator/
  __init__.py          # public exports: run_investigation, walk_queue, Proposal, CaseFile
  case_file.py         # CaseFile dataclass + build_case_file(cluster, dazzle_root)
  proposal.py          # Proposal + FixInput dataclasses + markdown (de)serialisation
  attempted.py         # AttemptedIndex (load/save/rebuild) — idempotence cache
  tools.py             # 6 AgentTool definitions + ToolState
  mission.py           # build_investigator_mission + system prompt
  runner.py            # run_investigation + walk_queue + metrics sink
  metrics.py           # append_metric for .dazzle/fitness-proposals/_metrics.jsonl
```

CLI touchpoint: `src/dazzle/cli/fitness.py` gets a new `investigate` subcommand.

Documentation: `docs/reference/fitness-investigator.md` (new user reference), `CHANGELOG.md` Unreleased entry, one-line pointer in `CLAUDE.md` under "Extending".

### Data flow

```
fitness-queue.md          fitness-backlog.md
  (ranked clusters)         (raw findings)
         │                         │
         ▼                         ▼
   CLI investigate            case_file.py
         │                         │
         ▼                         ▼
      runner.py  ─────────▶  mission.py  ─────────▶  DazzleAgent loop
         │                         │                      │
         │                         │                      ▼
         │                         │                   tools.py
         │                         │                  (5 read-only
         │                         │                   + propose_fix)
         │                         │                      │
         │                         │                      ▼
         ▼                         ▼                 Proposal on disk
   .dazzle/fitness-proposals/<cluster_id>-<proposal_id[:8]>.md
   .dazzle/fitness-proposals/_blocked/<cluster_id>.md
   .dazzle/fitness-proposals/_attempted.json
   .dazzle/fitness-proposals/_metrics.jsonl
```

### Layer responsibilities

| Layer | Owns | Does not own |
|---|---|---|
| `runner.py` | Idempotence (skip-if-proposal-exists), cluster resolution from the queue, iteration over `--top N`, calling the metrics sink, translating `MissionComplete` status into return values. | Decision-making, LLM calls, file mutation outside `.dazzle/fitness-proposals/`. |
| `case_file.py` | Reading the sample + siblings from the backlog, reading the locus file with the windowing heuristic, emitting an immutable `CaseFile`. | Pulling DSL, spec, or git history — those are tool-time lookups. |
| `mission.py` | Assembling the `Mission` object: system prompt, tool list, termination criteria. Case file goes in as seed observation. | The agent loop itself — that's `DazzleAgent`. |
| `tools.py` | Per-tool implementations as pure functions of `(dazzle_root, case_file, state, args) → ToolResult`. `propose_fix` is the only terminal tool. | Semantic interpretation — all semantics are the LLM's job. |
| `proposal.py` | `Proposal` / `FixInput` dataclasses, frontmatter+markdown serialisation, disk layout, validation (non-empty fixes, diff parses, paths in bounds). | Anything about applying the proposal — that's the actor. |
| `attempted.py` | The `_attempted.json` cache: load, save, rebuild from disk on corruption. | Authoritative state — disk is authoritative, this is a cache. |
| `metrics.py` | Appending one JSONL line per investigation attempt to `_metrics.jsonl`. | Analytics, querying, alerting — downstream tools' job. |

### Invariants

1. **One `Proposal` per cluster per mission run.** The terminal `propose_fix` call ends the mission; no second proposal is possible in the same invocation.
2. **Tools are read-only over the repo.** `propose_fix` is the only tool that writes, and it writes only to `.dazzle/fitness-proposals/`. No tool touches source files, DSL files, tests, config, or git state.
3. **Idempotent by default.** `run_investigation(cluster)` returns the existing proposal (or `None` if blocked) without re-running the LLM if a proposal is already on disk. `--force` overrides.
4. **Deterministic case file.** Given the same `Cluster` and the same repo state, `build_case_file` produces a `CaseFile` that differs from a re-run only in the `built_at` timestamp. `--dry-run` reproducibility depends on this.
5. **Mission isolation.** Each cluster investigation gets its own `DazzleAgent` instance with its own transcript. A stuck or misbehaving cluster cannot contaminate the next one.
6. **`corrector.py` untouched during Phase 1.** `Fix` is imported as a value type only. The legacy `generate_fix` / `route_finding` / `_LlmClient` functions are not called, not modified, and not moved. A follow-up ship audits live callers and deletes the module.
7. **No writes outside `.dazzle/fitness-proposals/`.** Metrics, proposals, blocked artefacts, and the attempted index all live under that directory. Nothing else.

### Failure modes and artefacts

| Failure | Artefact | Index state |
|---|---|---|
| LLM fails to call `propose_fix` within the 25-step cap | `.dazzle/fitness-proposals/_blocked/<cluster_id>.md` with transcript | `AttemptedEntry(status="blocked")`, `last_attempt` now |
| Stagnation: 4 consecutive steps with no tool call | Same blocked artefact, transcript up to abort point | Same |
| `propose_fix` terminal call has invalid schema (bad diff, missing fields) | Blocked artefact with the raw LLM args embedded for debugging | Same |
| `build_case_file` fails (sample missing, traversal guard fires) | None written; runner logs warning and returns `None` | No state change — next run retries |
| LLM client errors (rate limit, network, crash) | None written; runner raises; CLI exits with code 3 | No state change — transient, retry later |
| Proposal write collision (disk race with existing file of same ID) | None written; `ProposalWriteError` bubbles up; CLI exits 3 | No state change |

---

## Section 1 — CaseFile

### Dataclasses

```python
# src/dazzle/fitness/investigator/case_file.py

@dataclass(frozen=True)
class LocusExcerpt:
    file_path: str                           # repo-relative
    total_lines: int
    mode: Literal["full", "windowed"]
    chunks: tuple[tuple[int, int, str], ...] # (start_line, end_line, text) triples, 1-indexed

@dataclass(frozen=True)
class CaseFile:
    cluster: Cluster                          # from fitness/triage.py
    sample_finding: Finding                   # from fitness/models.py, pointed at by cluster.sample_id
    siblings: tuple[Finding, ...]             # up to 5, diversity-picked
    locus: LocusExcerpt | None                # None only if the locus file can't be read
    dazzle_root: Path                         # absolute
    example_root: Path | None                 # absolute, set iff locus is inside an example app
    built_at: datetime                        # wall clock; NOT used for determinism

    def to_prompt_text(self) -> str: ...
```

### `build_case_file` contract

```python
def build_case_file(
    cluster: Cluster,
    dazzle_root: Path,
    *,
    backlog_reader: BacklogReader | None = None,  # injectable for tests
) -> CaseFile:
    ...

class BacklogReader(Protocol):
    def findings_in(self, path: Path) -> list[Finding]: ...

class CaseFileBuildError(Exception): ...
class CaseFileTraversalError(CaseFileBuildError): ...
```

Pure function. No mutation, no LLM calls, no network. Raises `CaseFileBuildError` when:

1. The sample `Finding` (by `cluster.sample_id`) cannot be found in any `fitness-backlog.md`.
2. `cluster.locus` resolves outside `dazzle_root` (path traversal guard) → `CaseFileTraversalError`.

Does NOT raise when the locus file is missing or binary — sets `locus=None` and lets the mission handle it as its own signal.

### Build steps

1. **Resolve example root.** If `cluster.locus` starts with `examples/<name>/`, set `example_root = dazzle_root / "examples" / <name>`. Otherwise `example_root = None`. The locus is always interpreted relative to `dazzle_root`.

2. **Load the sample Finding.** Use the existing `fitness-backlog.md` parser (reused from `fitness/triage.py`). Search order: if `example_root` is set, look in `example_root/dev_docs/fitness-backlog.md` first, fall back to `dazzle_root/dev_docs/fitness-backlog.md`. Raise `CaseFileBuildError("sample finding <sample_id> not in any backlog")` if not found.

3. **Load sibling candidates.** From the same backlog file that held the sample, select all findings whose dedupe key (as computed by the existing `triage.canonicalize_summary` + key derivation) matches the cluster's dedupe key. That's the candidate pool.

4. **Pick up to 5 siblings deterministically.**
   - Exclude the sample itself.
   - Sort the pool by `(persona, finding.id)` ascending — stable baseline order.
   - The first sibling is the first element of the sorted pool.
   - Subsequent picks prefer candidates whose `observed` text has the largest Levenshtein distance from already-picked siblings' `observed` texts. Ties broken by sort order.
   - Stop at `min(5, len(pool))`.
   - Empty pool ⇒ `siblings = ()`. Not an error.

5. **Load the locus file.** Read `dazzle_root / cluster.locus`. Traversal guard: `resolve()` both paths and assert `resolved_locus.is_relative_to(resolved_dazzle_root)` — raise `CaseFileTraversalError` on failure. If the file is missing, binary (null byte in first 1 KB), or ≥ 2 MB, set `locus=None` and continue. Otherwise:
   - `total_lines ≤ 500`: `mode="full"`, `chunks=((1, total_lines, content),)`.
   - `total_lines > 500`: `mode="windowed"`. Chunks:
     - First 200 lines: `(1, 200, content_lines[0:200])`.
     - One chunk per distinct line number mentioned in `sample.evidence_embedded` or any sibling's `evidence_embedded`, with a ±20 line window. Regex for line extraction: `(?:line\s+|:\s*)(\d+)` — handles both `"line 47"` and `"form.html:47"`.
     - Overlapping windows merged before storage.
     - Chunks sorted by start line ascending.

6. **Return `CaseFile`.** Frozen, immutable. `built_at = datetime.now(UTC)` (informational only).

### Determinism guarantee

Two calls to `build_case_file(cluster, dazzle_root)` with identical backlog and repo state produce `CaseFile` objects that differ only in `built_at`. This is load-bearing for `--dry-run` reproducibility, test snapshots, and retry idempotence.

### `to_prompt_text` rendering

Single opinionated formatter so the mission can embed the case file as one string in its seed observation. Format (verbatim structure; values are per-cluster):

```
# Case File

## Cluster
id: <cluster.cluster_id>
locus: <cluster.locus>
axis: <cluster.axis>
severity: <cluster.severity>
persona: <cluster.persona>
summary: "<cluster.canonical_summary>"
size: <cluster.cluster_size> findings
first_seen: <ISO8601>
last_seen: <ISO8601>

## Sample Finding (<sample.id>)
created: <ISO8601>
expected: "<sample.expected>"
observed: "<sample.observed>"
evidence:
  <sample.evidence_embedded transcript excerpt, verbatim>

## Sibling Findings (<N> shown; cluster_size=<M>)

### <sibling.id> (persona=<sibling.persona>)
expected: "<sibling.expected>"
observed: "<sibling.observed>"
evidence: <excerpt>

### <next sibling>
...

## Locus File: <locus.file_path> (<locus.total_lines> lines, mode=<full|windowed>)

  1: <line content>
  2: <line content>
  ...

... (lines X..Y omitted)

  <next chunk start>: <line content>
  ...
```

Line numbers are prepended to every locus line so the LLM can reference them in diffs. Windowed mode inserts `... (lines X..Y omitted)` separators between chunks.

---

## Section 2 — Proposal

### Dataclasses

```python
# src/dazzle/fitness/investigator/proposal.py

from dazzle.fitness.corrector import Fix  # reused — value type only

ProposalStatus = Literal[
    "proposed",   # investigator wrote it; actor hasn't touched it
    "applied",    # actor applied the diff; not yet verified
    "verified",   # actor applied + re-ran Phase B + cluster is gone
    "reverted",   # actor applied + verify failed → rolled back
    "rejected",   # human or actor spot-check deemed the proposal wrong
]

@dataclass(frozen=True)
class FixInput:
    """LLM-facing wrapper; converted to Fix inside propose_fix."""
    file_path: str
    line_range: tuple[int, int] | None
    diff: str                                # unified diff
    rationale: str                           # per-fix, one or two sentences
    confidence: float                        # per-fix, 0..1

@dataclass(frozen=True)
class Proposal:
    proposal_id: str                         # UUID4 hex, stable per mission run
    cluster_id: str                          # back-reference, e.g. "CL-a1b2c3d4"
    created: datetime                        # UTC, when propose_fix was called
    investigator_run_id: str                 # DazzleAgent mission run id
    fixes: tuple[Fix, ...]                   # ≥1, may span multiple files
    overall_confidence: float                # 0..1, the LLM's own self-report
    rationale: str                           # overall "why", ≥20 chars
    alternatives_considered: tuple[str, ...] # ≤5 entries, each a single line
    verification_plan: str                   # ≥20 chars, what to re-run + expect
    evidence_paths: tuple[str, ...]          # repo-relative, from ToolState.evidence_paths
    tool_calls_summary: tuple[str, ...]      # ordered log from ToolState
    status: ProposalStatus                   # initial "proposed"; actor transitions
```

### On-disk layout

```
.dazzle/fitness-proposals/
  CL-a1b2c3d4-6b3cfe42.md
  CL-e5f67890-9d2a1b47.md
  _blocked/
    CL-33445566.md
  _attempted.json
  _metrics.jsonl
```

- Top-level proposals: filename `<cluster_id>-<proposal_id[:8]>.md`.
- `_blocked/` holds failed-run artefacts. One file per cluster, overwritten on re-attempt.
- `_attempted.json` is the rebuildable idempotence cache (see `attempted.py` below).
- `_metrics.jsonl` is append-only metrics (see `metrics.py` below).

### Markdown + frontmatter serialisation

Format:

```markdown
---
proposal_id: 6b3cfe4278f74aa29e8c94f1d85b3a7c
cluster_id: CL-a1b2c3d4
created: 2026-04-14T22:04:17Z
investigator_run_id: 9afdcfa9-a803-48f2-85a7-894ea288fe58
overall_confidence: 0.82
status: proposed
rationale: |
  <multi-line overall rationale>
fixes:
  - file_path: src/dazzle_ui/templates/macros/form_field.html
    line_range: [47, 52]
    rationale: "<per-fix reasoning>"
    confidence: 0.85
  - file_path: src/dazzle_ui/templates/macros/form_field.html
    line_range: [64, 66]
    rationale: "<per-fix reasoning>"
    confidence: 0.90
verification_plan: |
  <multi-line plan>
alternatives_considered:
  - "<alternative 1 — one line — why rejected>"
  - "<alternative 2 — one line — why rejected>"
evidence_paths:
  - src/dazzle_ui/templates/macros/form_field.html
  - src/dazzle/fitness/semantics_kb/core.toml
tool_calls_summary:
  - "read_file(src/dazzle_ui/templates/macros/form_field.html)"
  - "query_dsl(Ticket)"
  - "search_spec(aria-describedby)"
  - "propose_fix(2 fixes)"
---

## Case file

<verbatim CaseFile.to_prompt_text() output>

## Investigation log

<LLM-written free-form markdown; the narrative of what was explored and why>

## Proposed diff

```diff
<unified diff covering all fixes>
```
```

The frontmatter is machine-readable (YAML); the body below is human-readable and for debugging only. The actor only reads the frontmatter.

### (De)serialisation functions

```python
def save_proposal(
    proposal: Proposal,
    dazzle_root: Path,
    *,
    case_file_text: str,       # verbatim seed context for the audit body
    investigation_log: str,    # LLM-written markdown for the audit body
) -> Path:
    """Write one proposal file. Returns the path written.

    Raises:
      ProposalValidationError — if the Proposal violates the rules below.
      ProposalWriteError       — if the target file already exists or disk write fails.
    """

def load_proposal(path: Path) -> Proposal: ...
def list_proposals(dazzle_root: Path, *, cluster_id: str | None = None) -> list[Proposal]: ...
def write_blocked_artefact(
    cluster_id: str,
    dazzle_root: Path,
    *,
    reason: str,
    case_file_text: str,
    transcript: str,
) -> Path: ...
```

### Validation rules (enforced at `save_proposal`)

1. `fixes` non-empty.
2. Each `fix.diff` parses as a unified diff whose `---/+++` path matches `fix.file_path`.
3. `0.0 ≤ overall_confidence ≤ 1.0`; same for each `fix.confidence`.
4. `0 ≤ len(alternatives_considered) ≤ 5`.
5. `verification_plan` length ≥ 20 chars.
6. `rationale` length ≥ 20 chars.
7. `cluster_id` matches `^CL-[0-9a-f]{8,}$`.
8. No `fix.file_path` escapes `dazzle_root` (same traversal guard as `build_case_file`).

Validation failures raise `ProposalValidationError`. The terminal `propose_fix` tool catches it, writes a blocked artefact with the raw LLM args, and raises `MissionComplete(status="blocked_invalid_proposal")`.

### Error types

```python
class ProposalError(Exception): ...
class ProposalValidationError(ProposalError): ...
class ProposalWriteError(ProposalError): ...
class ProposalParseError(ProposalError): ...
```

---

## Section 3 — AttemptedIndex

Rebuildable cache for idempotence checks.

```python
# src/dazzle/fitness/investigator/attempted.py

@dataclass
class AttemptedEntry:
    proposal_ids: list[str]
    last_attempt: datetime
    status: ProposalStatus | Literal["blocked"]

@dataclass
class AttemptedIndex:
    clusters: dict[str, AttemptedEntry]

def load_attempted(dazzle_root: Path) -> AttemptedIndex:
    """Load .dazzle/fitness-proposals/_attempted.json. If missing or corrupt,
    rebuild from disk via rebuild_attempted."""

def save_attempted(index: AttemptedIndex, dazzle_root: Path) -> None:
    """Atomic write via tempfile + os.replace."""

def rebuild_attempted(dazzle_root: Path) -> AttemptedIndex:
    """Glob .dazzle/fitness-proposals/*.md + _blocked/*.md, parse frontmatter,
    reconstruct the index. Source of truth is disk."""

def mark_attempted(
    index: AttemptedIndex,
    cluster_id: str,
    *,
    proposal_id: str | None,
    status: ProposalStatus | Literal["blocked"],
) -> None:
    """Update the index in-place. Caller is responsible for calling save_attempted."""
```

The index is never authoritative — if it's deleted or corrupt, `load_attempted` calls `rebuild_attempted` which re-scans the disk. The CLI's idempotence behaviour survives index loss without losing history.

---

## Section 4 — Tools

### Tool framework

Each tool is an `AgentTool` (existing type in `src/dazzle/agent/core.py`). The tool builder returns all six with a shared `ToolState`:

```python
# src/dazzle/fitness/investigator/tools.py

@dataclass
class ToolState:
    evidence_paths: set[str] = field(default_factory=set)
    tool_calls_summary: list[str] = field(default_factory=list)
    findings_seen: dict[str, int] = field(default_factory=dict)

def build_investigator_tools(
    case_file: CaseFile,
    dazzle_root: Path,
    llm_run_id: str,
    state: ToolState,
) -> list[AgentTool]:
    return [
        _read_file_tool(case_file, dazzle_root, state),
        _query_dsl_tool(case_file, dazzle_root, state),
        _get_cluster_findings_tool(case_file, dazzle_root, state),
        _get_related_clusters_tool(case_file, dazzle_root, state),
        _search_spec_tool(case_file, dazzle_root, state),
        _propose_fix_tool(case_file, dazzle_root, llm_run_id, state),
    ]
```

Every tool appends to `state.tool_calls_summary` as its first action — including on validation failures — so the audit trail records attempts, not just successes.

### Universal tool behaviour rule

**No opaque errors.** Any LLM-caller-fault failure (wrong name, missing file, too-short query, bad cluster ID) returns a `ToolResult` with structured `error` content that tells the agent what was wrong *and* what to try instead. Exceptions are reserved for infrastructure failures (disk full, subprocess crashed) where the agent cannot recover.

Applied shape (every tool's error path):

```python
{"error": "<specific reason>", "did_you_mean": [...] | "similar": [...] | "hint": "<corrective hint>"}
```

`propose_fix` is the one exception — its failures raise `MissionComplete(blocked_*)` because they end the run. The blocked artefact still captures structured diagnostic content.

### Tool signatures + behaviour

#### `read_file(path: str, line_range: tuple[int, int] | None = None) -> ToolResult`

**Purpose:** Fetch any file in the repo. Escape hatch for content beyond the case file.

**Validation / error payloads:**
- Reject absolute paths (`/`-prefixed) with `{"error": "path must be repo-relative", "hint": "drop leading slash"}`.
- Traversal guard via `resolve().is_relative_to(dazzle_root)` — reject with `{"error": "path escapes repo root"}`. No hint — security issue, not an LLM correction case.
- Missing file: `{"error": "file not found: <path>", "similar": [<up to 3 nearest matches by filename stem>]}`.
- Binary file (null byte in first 1 KB): `{"error": "binary file; not readable"}`.
- File ≥ 2 MB: `{"error": "file too large: <n> bytes, cap is 2 MB", "hint": "use line_range to read a slice"}`.
- Clamp invalid `line_range` silently; error only if the clamp produces an empty range.

**Success:** returns content with line numbers prepended, same format as `CaseFile.to_prompt_text`.

**Side effects:** `state.evidence_paths.add(path)`; `state.tool_calls_summary.append(f"read_file({path}{suffix})")`.

#### `query_dsl(name: str) -> ToolResult`

**Purpose:** Fetch the parsed DSL node for any IR type. Faster than grepping DSL files.

**Implementation:** Wraps the existing `dazzle.mcp.server.handlers.dsl.inspect_entity` / `inspect_surface` / `inspect_workspace` / etc. code paths. Tries each type in turn (entity, surface, workspace, service, process, persona, enum) until one matches.

**Resolution scope:** If `case_file.example_root` is set, resolve inside that example's DSL. Otherwise resolve against `dazzle_root`'s DSL (fixtures + framework tests).

**Return shape on success:** A dict keyed by `kind` discriminator — `{"kind": "entity", "name": ..., "fields": [...], "scope_rules": [...], "source_file": ..., "line_range": [...]}`.

**Error payload:** `{"error": "no DSL node named <name>", "did_you_mean": [<up to 3 fuzzy suggestions from the IR name index>]}`. No raise.

**Side effects:** `state.tool_calls_summary.append(f"query_dsl({name})")`; `state.evidence_paths.add(source_file)` on success.

#### `get_cluster_findings(cluster_id: str, limit: int = 10) -> ToolResult`

**Purpose:** Fetch more sibling findings beyond the 5 in the case file.

**Validation / error payloads:**
- `cluster_id != case_file.cluster.cluster_id`: allowed (wide-pattern exploration), but result includes `{"warning": "querying a different cluster than the one being investigated"}`.
- Unknown `cluster_id`: `{"error": "cluster not found", "did_you_mean": [<case_file.cluster.cluster_id>]}`.
- Per-cluster cap: 30 total findings returned across all calls in one mission. Enforced via `state.findings_seen[cluster_id]`. Once hit: `{"findings": [], "note": "30 findings already fetched for this cluster. Remaining findings have equivalent canonical summaries (that's how they got clustered). For variation signal try get_related_clusters(locus=...) or read_file on the locus; for evidence depth re-read the existing samples' evidence_embedded fields."}`.
- `limit` values outside `[1, 20]` clamped silently to that range.

**Success:** list of Finding dicts, excluding any already in `case_file.siblings`.

**Side effects:** `state.findings_seen[cluster_id] += len(returned)`; `state.tool_calls_summary.append(f"get_cluster_findings({cluster_id}, limit={limit})")`.

#### `get_related_clusters(locus: str) -> ToolResult`

**Purpose:** Surface other clusters pointing at the same file — the "is this a wider pattern?" check.

**Behaviour:**
- Exact-match filter over `fitness-queue.md` by `locus`. No fuzzy matching — deliberate.
- Excludes the current cluster.
- Order: severity descending, then `cluster_size` descending (matches the triage queue ranking).
- Empty result: `{"hits": [], "note": "no other clusters at this locus; the issue is unique to this file/region"}`.

**Error payloads:** none — empty is valid, no input can be "wrong."

**Side effects:** `state.tool_calls_summary.append(f"get_related_clusters({locus})")`. No evidence path added (reads the queue, not source).

#### `search_spec(query: str) -> ToolResult`

**Purpose:** Grep `docs/superpowers/specs/` and `docs/reference/` for a term.

**Implementation:**
- Primary: subprocess call to `rg -F -n -C 2 -i <query> docs/superpowers/specs/ docs/reference/`.
- Fallback: if ripgrep is unavailable, pure-Python `Path.rglob("*.md")` + line-by-line literal match.

**Return shape:** list of `{"file": str, "line": int, "excerpt": str}` dicts; capped at 10 hits.

**Validation / error payloads:**
- Queries shorter than 3 chars: `{"error": "query too short (min 3 chars)", "hint": "try a more specific term"}`.
- Zero hits: `{"hits": [], "note": "no matches in spec or reference docs; try rephrasing or search a broader term"}`.
- Subprocess failure: treated as infrastructure (raise) — the LLM can't recover from ripgrep crashing.

**Side effects:** `state.evidence_paths.add(hit["file"])` for each hit; `state.tool_calls_summary.append(f"search_spec({query})")`.

#### `propose_fix(...) -> NoReturn` (terminal)

**Purpose:** Terminal action. Validates, serialises, and writes the Proposal to disk. Ends the mission via `MissionComplete`.

**LLM-facing schema:**

```python
{
  "fixes": [
    {
      "file_path": str,
      "line_range": [int, int] | None,
      "diff": str,
      "rationale": str,
      "confidence": float,
    },
    ...
  ],
  "rationale": str,
  "overall_confidence": float,
  "verification_plan": str,
  "alternatives_considered": [str, ...],
  "investigation_log": str,
}
```

**Behaviour:**

1. Append `f"propose_fix({len(fixes)} fixes)"` to `state.tool_calls_summary` *before* validation.
2. Build `list[Fix]` from the `fixes` input (one `Fix(...)` per entry).
3. Build `Proposal` dataclass:
   - `proposal_id = uuid4().hex`
   - `cluster_id = case_file.cluster.cluster_id`
   - `created = datetime.now(UTC)`
   - `investigator_run_id = llm_run_id`
   - `evidence_paths = tuple(sorted(state.evidence_paths))`
   - `tool_calls_summary = tuple(state.tool_calls_summary)`
   - `status = "proposed"`
4. Call `save_proposal(proposal, dazzle_root, case_file_text=case_file.to_prompt_text(), investigation_log=...)`.
5. On `ProposalValidationError`: `write_blocked_artefact(cluster_id, dazzle_root, reason=f"validation: {err}", case_file_text=..., transcript=<raw LLM args>)`; raise `MissionComplete(status="blocked_invalid_proposal")`.
6. On `ProposalWriteError`: log, raise `MissionComplete(status="blocked_write_error")`.
7. On success: raise `MissionComplete(status="proposed", proposal_id=proposal.proposal_id)`.

**`MissionComplete`:** the existing exception from `agent/core.py` that signals the loop to stop.

---

## Section 5 — Mission

### `build_investigator_mission`

```python
# src/dazzle/fitness/investigator/mission.py

def build_investigator_mission(
    case_file: CaseFile,
    dazzle_root: Path,
    llm_run_id: str,
) -> tuple[Mission, ToolState]:
    tool_state = ToolState()
    tools = build_investigator_tools(
        case_file=case_file,
        dazzle_root=dazzle_root,
        llm_run_id=llm_run_id,
        state=tool_state,
    )
    return (
        Mission(
            name="investigator",
            system_prompt=_render_system_prompt(case_file),
            seed_observation=case_file.to_prompt_text(),
            tools=tools,
            max_steps=25,
            completion_criteria=make_stagnation_completion(
                window=4,
                label="investigator-stagnation",
            ),
        ),
        tool_state,
    )
```

The caller (runner) keeps the `tool_state` reference so it can read `evidence_paths` and `tool_calls_summary` after the mission completes.

### System prompt

The system prompt is the single biggest lever on proposal quality. This is the v1 starting point; it will be iterated on as "there will be bugs" data comes in.

```
You are an investigator in the Dazzle fitness loop. Your job is to examine
one cluster of fitness findings and produce a structured fix proposal that
a later actor subsystem can apply mechanically.

# Context

You will receive a case file in the first turn. It contains:
- The cluster header (id, locus, axis, severity, persona, canonical summary)
- The sample finding, including evidence transcript excerpts
- Up to 5 sibling findings showing variation across the cluster
- The locus file content (full if small, windowed around evidence lines if large)

The case file is your starting point. It is NOT exhaustive. Use your tools
to pull any additional context you need.

# Your goal

Produce a single call to `propose_fix` describing how to resolve this
cluster. The proposal must:

1. Fix the root cause, not the symptom. If the evidence points at a shared
   helper, propose a change to the helper — not a copy-paste in every caller.
2. When the evidence points at a shared helper, a template partial, or a
   repeated pattern, prefer a fix at the shared layer even if the diff is
   larger. A correct refactor is preferable to a narrow patch that leaves
   siblings broken.
3. Explain WHY the fix is correct in its rationale.
4. List at least two alternatives you considered and why you rejected them.
5. Provide a verification plan the actor can execute to confirm the fix works.
6. Use real line numbers from files you have read. Never guess at diffs.

# Tools

You have six tools. Five are read-only observers; the sixth ends the mission.

**read_file(path, line_range?)** — read any repo file. Line numbers are
prepended to every line; use those line numbers in your diffs.

**query_dsl(name)** — fetch the parsed DSL node for an entity, surface,
workspace, service, process, persona, or enum. If the name is wrong
you'll get a `did_you_mean` list.

**get_cluster_findings(cluster_id, limit)** — fetch more sibling findings
beyond the 5 in the case file. Capped at 30 per cluster per mission.

**get_related_clusters(locus)** — find other clusters pointing at the
same file. Use this to decide whether your fix should address one symptom
or a shared root cause.

**search_spec(query)** — grep docs/superpowers/specs/ and docs/reference/
for a literal term. Use when you need to know the design intent.

**propose_fix(fixes, rationale, overall_confidence, verification_plan,
alternatives_considered, investigation_log)** — terminal. Calling this
ends the mission. Only call it when you have:
  - read the locus file (always)
  - verified the diff lines exist at the line numbers you reference
  - considered at least one alternative
  - written a verification plan more specific than "re-run Phase B"

# Termination

You have at most 25 steps. If you cannot produce a proposal within that
budget, end with `propose_fix` anyway and set overall_confidence low
(< 0.4). The proposal will still be recorded; a low-confidence proposal
is better than no proposal because it captures what you learned.

If the case file is insufficient and your tools cannot help — for example,
the locus points at a missing file — call `propose_fix` with one fix whose
rationale explains the blocker and overall_confidence=0.0. Never get stuck
in a tool-call loop; make progress or explain why you cannot.

# Style

- Keep per-fix rationales brief: two sentences.
- Keep alternatives brief: one line each, explaining WHY rejected.
- The investigation log is free-form markdown; write it as a future-you
  would want to read it when the proposal needs debugging.
- Confidence is your honest self-assessment. A 0.7 that turns out correct
  is better than a 0.95 that turns out wrong. The actor uses confidence
  to decide whether to auto-apply or flag for review.
```

### LLM client parameters

- **Model:** `claude-sonnet-4-6` (default); overridable via `--model`.
- **Temperature:** `0.2` (lower than the walker's 0.7 for determinism).
- **Max tokens per turn:** `4000`.
- **System prompt:** the block above.
- **Seed user turn:** `case_file.to_prompt_text()`.
- **Tools:** the 6-tool list from `build_investigator_tools`.

---

## Section 6 — Runner, CLI, Metrics

### Runner

```python
# src/dazzle/fitness/investigator/runner.py

@dataclass(frozen=True)
class InvestigationResult:
    status: Literal["proposed", "blocked_invalid_proposal", "blocked_write_error",
                    "blocked_step_cap", "blocked_stagnation"]
    proposal_id: str | None
    tool_state: ToolState
    transcript: AgentTranscript

async def run_investigation(
    cluster: Cluster,
    dazzle_root: Path,
    llm_client: LlmClient,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> Proposal | None:
    """Investigate one cluster.

    - If force=False and a proposal for this cluster exists on disk, return
      the existing Proposal without running the LLM.
    - If dry_run=True, print case_file.to_prompt_text() and return None.
    - Otherwise build the case file, run the mission, write the proposal or
      blocked artefact, call the metrics sink, return the Proposal (or None
      if blocked).
    """

async def walk_queue(
    dazzle_root: Path,
    llm_client: LlmClient,
    *,
    top: int,
    force: bool,
    dry_run: bool,
    progress_callback: Callable[[int, int, Cluster, str], None] | None = None,
) -> list[Proposal | None]:
    """Walk top N clusters from fitness-queue.md, calling run_investigation on each."""
```

### CLI subcommand

```python
# src/dazzle/cli/fitness.py (new subcommand)

@fitness_app.command("investigate")
def investigate(
    top: int = typer.Option(1, "--top", help="Investigate the top N clusters from the queue."),
    cluster: str | None = typer.Option(None, "--cluster", help="Investigate a specific cluster ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build + print the case file; do not call LLM."),
    force: bool = typer.Option(False, "--force", help="Re-investigate clusters that already have a proposal."),
    project: Path | None = typer.Option(None, "--project", help="Override project root (default: cwd)."),
    model: str | None = typer.Option(None, "--model", help="LLM model override (default: claude-sonnet-4-6)."),
) -> None: ...
```

**Flag precedence:** `--cluster` overrides `--top`. `--dry-run` and `--force` are orthogonal.

**Exit codes:**
- `0`: at least one proposal was written, or dry-run completed successfully.
- `1`: nothing to do (queue empty, or all top N clusters already have proposals and `--force` was not set).
- `2`: invalid arguments (`--cluster` not in queue, etc.).
- `3`: infrastructure failure (LLM client crash, disk write denied).

**Compact output format (one cluster per block):**

```
[1/3] CL-a1b2c3d4  form-field  coverage:high  persona=admin  size=17
      → investigating... (6 tool calls, 12.4s, 9690 tokens)
      → proposed: .dazzle/fitness-proposals/CL-a1b2c3d4-6b3cfe42.md (conf 0.82)

[2/3] CL-e5f67890  form-validation  conformance:medium  persona=admin  size=8
      → skipped (already proposed: CL-e5f67890-9d2a1b47)

[3/3] CL-33445566  dashboard-grid  coverage:critical  persona=admin  size=23
      → investigating... (25 tool calls, 45.1s, 18203 tokens)
      → blocked: step_cap → .dazzle/fitness-proposals/_blocked/CL-33445566.md
```

### Metrics sink

```python
# src/dazzle/fitness/investigator/metrics.py

def append_metric(
    dazzle_root: Path,
    *,
    cluster_id: str,
    proposal_id: str | None,
    status: str,
    tokens_in: int,
    tokens_out: int,
    tool_calls: int,
    duration_ms: int,
    model: str,
) -> None:
    """Append one JSONL line to .dazzle/fitness-proposals/_metrics.jsonl."""
```

Line format (one per attempt, success or blocked):

```json
{"cluster_id":"CL-a1b2c3d4","proposal_id":"6b3cfe42...","status":"proposed","tokens_in":8234,"tokens_out":1456,"tool_calls":6,"duration_ms":12400,"created":"2026-04-14T10:15:23Z","model":"claude-sonnet-4-6"}
```

Called exactly once per investigation attempt by the runner. Append-only; file creation is idempotent.

---

## Testing strategy

Four test levels, ordered by speed.

### Level 1: Unit tests (fast, no LLM)

- `tests/unit/fitness/investigator/test_case_file.py` — `build_case_file` determinism, sibling diversity picker, locus windowing, traversal guard, `BacklogReader` injection. ~20 tests.
- `tests/unit/fitness/investigator/test_proposal.py` — `Proposal` round-trip (save → load), validation rules (all 8), frontmatter parse, blocked-artefact writer. ~15 tests.
- `tests/unit/fitness/investigator/test_tools.py` — each tool in isolation with fixture `dazzle_root`, mutable `ToolState` verified explicitly, every error-payload shape covered. ~25 tests across 6 tools.
- `tests/unit/fitness/investigator/test_attempted.py` — `AttemptedIndex` load/save/rebuild cycles, corruption recovery. ~8 tests.

### Level 2: Mission tests (medium, stubbed LLM)

`tests/unit/fitness/investigator/test_mission.py` — stub `LlmClient` that returns pre-recorded tool-call sequences. Drives the mission loop end-to-end without network. Verifies:

- Well-formed tool-call sequence → `Proposal` written.
- Invalid `propose_fix` call → blocked artefact written, status `blocked_invalid_proposal`.
- 25 steps reached → blocked artefact, status `blocked_step_cap`.
- 4 consecutive no-tool-call turns → blocked artefact, status `blocked_stagnation`.
- `--dry-run` path → case file printed, no disk writes.
- `--force` path → existing proposal ignored, new proposal with distinct `proposal_id`.

~15 tests.

### Level 3: CLI tests (medium, stubbed LLM)

`tests/unit/fitness/test_investigate_cli.py` — Typer `CliRunner` + stub LLM. Verifies:

- `--cluster CL-...` runs the named cluster.
- `--cluster BAD` exits 2 with "cluster not in queue".
- `--top 3` with 2 clusters runs 2 investigations and exits 0.
- `--top 1` on empty queue exits 1.
- `--dry-run` exits 0 and prints the case file.
- `--force` bypasses `_attempted.json`.

~8 tests.

### Level 4: Integration smoke (slow, real LLM, gated)

`tests/integration/fitness/test_investigator_real.py` — one test, `@pytest.mark.e2e`.

- Fixture: a minimal `fixtures/investigator_smoke/` project with one deliberately-broken file that produces a predictable finding when Phase B is run against it.
- Runs `dazzle fitness investigate --cluster CL-... --model claude-sonnet-4-6`.
- Asserts: the proposal file exists, frontmatter parses, `cluster_id` matches, `overall_confidence` is a float, `_metrics.jsonl` has a new line.
- Content-agnostic beyond that — we are testing that the pipeline runs end-to-end with a real LLM, not that the LLM produces a specific answer.

Runs only when `--runintegration` is passed to pytest. Expensive but catches prompt regressions.

---

## Documentation touches

1. **`docs/reference/fitness-investigator.md`** (new) — user reference covering what the investigator does, when to run it, the CLI flags, how to read a proposal file, how to debug blocked artefacts, the "there will be bugs" iteration workflow.
2. **`CHANGELOG.md` Unreleased → Added** — entry describing the subsystem.
3. **`CLAUDE.md` Extending section** — one-line pointer: `"Fitness investigator: see \`docs/reference/fitness-investigator.md\`. Run \`dazzle fitness investigate --top 1\` to produce proposals from the queue."`

Deliberately not touching: `ROADMAP.md`, ADRs, `dev_docs/` per-session summaries.

---

## Open questions for v0.2 (post-ship)

These are NOT part of this spec — they are items we intentionally defer until we have empirical data from running the v1 investigator:

- **Case file size tuning.** The 500/200 threshold and 5-sibling cap are guesses. After 20+ real investigations we can see whether the LLM is context-starved or context-overloaded and adjust.
- **Tool set expansion.** `run_validate`, `grep` (over source), `git_log` were considered and deferred. If specific clusters show "I needed X and had no tool for it," we add the tool.
- **Multi-cluster batching.** Right now each cluster gets a fresh mission. If many adjacent clusters share context (same locus, same shared helper), it may be worth batching — but only after measuring the cost.
- **Re-investigation policy.** What happens when a cluster's queue rank changes but a proposal already exists? V1 skips (idempotence). V2 may want "re-investigate if severity escalated."
- **Corrector deletion.** Audit `corrector.py` live callers, migrate or delete. Separate ship after v1 ships and we have investigator-quality data.
- **Actor subsystem spec.** The terminal state of the autonomous loop. Consumes `.dazzle/fitness-proposals/*.md`, applies diffs, runs Phase B, updates `status` in the frontmatter. Separate spec, separate ship.

---

## Summary of locked decisions

1. **Scope path:** investigator-only first (Option 3), actor follows, Option 2 full autonomy as end state.
2. **Context gathering:** medium case file — cluster + sample + ≤5 siblings + locus file (full ≤500 lines, else 200 + evidence-windowed).
3. **Output schema:** `Proposal` wrapping `Fix`, markdown+frontmatter at `.dazzle/fitness-proposals/<cluster_id>-<proposal_id[:8]>.md`.
4. **Tools:** `read_file`, `query_dsl`, `get_cluster_findings`, `get_related_clusters`, `search_spec`, `propose_fix` (terminal). Mutable `ToolState`. "No opaque errors" principle — all tools return structured error payloads with corrective hints.
5. **Termination:** single terminal action + 25-step cap + 4-step stagnation + downstream confidence gate + blocked artefacts + one-cluster-per-run + no mission-level cost budget.
6. **Driver:** `dazzle fitness investigate [--top N | --cluster CL-... | --dry-run | --force | --project | --model]`, idempotent by default.
7. **Build approach:** greenfield `src/dazzle/fitness/investigator/` package, reuse `Fix`, delete `corrector.py` in a separate post-Phase-1 ship.
8. **Temperature 0.2, metrics kept.**
9. **System prompt leads with root-cause + refactor-preference framing.**
