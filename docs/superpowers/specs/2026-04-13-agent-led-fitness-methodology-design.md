# Agent-Led Fitness Methodology — Design

**Status:** Revised (v2, post-review)
**Date:** 2026-04-13
**Owner:** Dazzle team (self-hosted) + Dazzle users (via MCP)
**Supersedes:** N/A (new subsystem)
**Depends on:** DSL + /bootstrap + template compiler + DazzleAgent framework + mcp__dazzle__db
**Prerequisite:** ADR-NNNN "Lifecycle Evidence Predicates" — extends the `process` DSL construct with `evidence_predicate` per transition and `progress_order` on state enums. Must land before fitness v1 progress evaluation can function.

## 1. Overview

The **Agent-Led Fitness Methodology** is a continuous V&V loop that evaluates whether a Dazzle app is *fit for the purpose described by its founder's spec*. Unlike mechanical QA (does the form submit? does the route render?) it answers semantic questions: **does this perform useful work for the persona? does it change entropy in ways congruent with the spec? would a first-time user figure it out without training?**

The methodology triangulates three corners — `spec.md` (the founder's natural-language oracle), the `DSL` (the intermediate representation), and the `running app` — and emits a fitness signal that feeds back into the codebase either autonomously (hard correction) or via human-gated PR (soft correction).

It serves two use cases with a single shared engine:

- **Dazzle team (dogfooding):** integrated into `/ux-cycle` as a new strategy. Atomic per example app. Drives example quality + surfaces framework gaps.
- **Dazzle users (their own projects):** exposed via `mcp__dazzle__fitness` MCP tool. Same engine, scoped to their current project. Same methodology, thin invocation shim.

## 2. Goals

1. Distinguish "the spec was wrong", "the DSL was wrong", and "the implementation was wrong" — localise the disagreement, not just detect it.
2. Catch silent data-loss failures that pure-DOM observation would miss (the "motion without work" problem).
3. Surface implicit capabilities the spec mentions but no DSL story covers.
4. Produce findings in a format that supports autonomous correction (hard mode) or human review (soft mode).
5. Do all of this without asking the founder to write specs, stories, or process definitions in framework vocabulary they don't have.
6. Scale from MVP (one spec, a handful of personas, a few entities) to stable (dozens of personas, hundreds of stories, years of drift).
7. **Guarantee sensor independence empirically, not aspirationally.** Every cycle measures the correlation between independent validation sensors and emits a signal when independence has degraded below threshold.

## 3. Non-goals

1. **Not a test framework.** It's a usability methodology that happens to produce findings. It does not replace unit tests, integration tests, or the existing `dazzle ux verify --contracts` mechanical checks.
2. **Not a security auditor.** RBAC gaps, injection attacks, CSRF edges are out of scope. Fitness checks functional correctness, not threat model correctness.
3. **Not a performance profiler.** Findings about latency, query plans, or N+1 queries are out of scope.
4. **Not a replacement for human product review.** Soft correction mode routes findings to a human PR queue precisely because some judgments are not delegable.
5. **Not a schema-migration monitor.** Long-lived projects have schema drift across cycles. The fitness engine detects incomplete migrations (`alembic heads ≠ alembic current`) at cycle start and skips the cycle with signal `FITNESS_SKIPPED_MIGRATION_PENDING`. Findings from a post-migration run are isolated as a separate cycle-type and reviewed under a staleness lens.

## 4. Named design principles

### 4.1 Deterministic Centre, Agentic Edges

> The DSL is the deterministic source of truth for the app. All difficult agentic cognition happens BEFORE the DSL (analysing a messy spec) and AFTER the DSL (exploring a built app in a near-human behavioural mode). The DSL → running app pipeline stays mechanical.

Consequence: Pass 1 (story walk) uses scripted Playwright runs, not LLM-as-agent. LLM-as-agent cognition is reserved for Pass 2 (spec cross-check + free-roam exploration) where judgment is actually required. This reduces token burn and removes non-determinism from the parts of the pipeline that should be reliable.

### 4.2 Agent-Ergonomic Tooling

> Tools that are too cognitively expensive for human developers can be the right tools for agents. Invest in agent-first infrastructure that leverages this asymmetry — WAL inspection, trigger-based change logs, structured protocol traces, content-addressable change streams. Agents pay no memory cost for complexity; they pay a verification cost for ambiguity. Trade one for the other wherever possible.

Consequence: the `FitnessLedger` target architecture (v1.2) treats the PostgreSQL logical decoding stream (WAL) as the authoritative observation substrate. Humans rarely use WAL directly because of parsing overhead; agents don't care.

### 4.3 Ask for Recognition, Not Generation

> Founders can recognize when their intent is misrepresented, even when they can't write the correct representation themselves. Design founder-facing loops around what they CAN do (recognize, correct paraphrases, react) rather than what they can't (write specs, author stories, disambiguate upfront). The agent generates; the founder recognizes.

**Consequence 1:** DSL stories are generated by /bootstrap (founder never writes them). An adversarial re-reader audits them every cycle. When feedback is needed, an agent paraphrases the story back to the founder in plain English.

**Consequence 2 (new in v2):** *Spec revisions follow the same Recognition pattern.* When the fitness engine detects `spec_stale` findings, the corrector does NOT ask the founder "update your spec". Instead it paraphrases: "Based on how you're using the app, it looks like you actually want X. Your spec currently says Y. Should I update the spec to reflect X?" Founder confirms → corrector edits `spec.md`. The spec becomes revisable by the same mechanism the rest of the system uses — no framework vocabulary required at any step.

## 5. Architecture

### 5.1 Data flow

```
spec.md ─────────────────┐
                         │
                         ▼
                  ┌──────────────┐
                  │  /bootstrap  │  (existing — opinionated resolver)
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │     DSL      │  (entities, personas, stories, process
                  │              │   WITH lifecycle evidence predicates)
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ running app  │
                  └──────┬───────┘
                         │
          ┌──────────────┴──────────────────────┐
          │                                      │
          ▼                                      ▼
  ┌──────────────┐                      ┌─────────────────┐
  │  Pass 1      │                      │  Pass 2         │
  │  walker      │                      │  (2a + 2b)      │
  │  (scripted)  │                      │  (agentic)      │
  └──────┬───────┘                      └────────┬────────┘
         │                                       │
         │  ┌───────────────────────────────┐    │
         │  │  spec_extractor → spec.md     │    │
         │  │  cross_check                  │    │
         │  │  adversary → stories ONLY     │ ◄──┘
         │  │  independence_correlation     │
         │  │  proxy (EXPECT/ACTION/OBSERVE │
         │  │          with hard interlock) │
         │  └──────────────┬────────────────┘
         │                 │
         └────────┬────────┘
                  │
                  ▼
         ┌──────────────┐
         │ FitnessLedger │  (v1 snapshot → v1.1 SAVEPOINT → v1.2 WAL)
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │  FitnessDiff  │  (EXPECT-preserving triples + LSN ordering)
         └──────┬───────┘
                │
                ▼
         ┌──────────────────┐
         │ progress_evaluator │  (lifecycle-based motion-vs-work check)
         └──────┬───────────┘
                │
                ▼
         ┌──────────────┐
         │  extractor    │  (narrative → structured findings)
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐   ┌────────────────┐
         │fitness-      │◄──┤fitness_n       │
         │backlog.md    │   │  vs            │
         │+ embedded    │   │fitness_{n-1}   │
         │  evidence    │   │ (regression    │
         │              │   │  comparator)   │
         └──────┬───────┘   └────────────────┘
                │
                ▼
         ┌──────────────┐
         │  corrector    │
         │              │
         │  two-gate:    │
         │  1. maturity  │
         │  2. generated │
         │     alt?     │
         └──────┬───────┘
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
    hard mode       soft mode (incl. spec_stale → paraphrase)
```

### 5.2 Component tree

```
src/dazzle/fitness/
├── __init__.py
├── engine.py                 # Orchestrator: runs all passes + regression check
├── ledger.py                 # FitnessLedger + FitnessDiff + implementations
├── ledger_snapshot.py        # v1
├── ledger_savepoint.py       # v1.1
├── ledger_wal.py             # v1.2
├── spec_extractor.py         # Pass 2a-A: capabilities from spec.md
├── cross_check.py            # Pass 2a-B: spec ↔ stories reconciliation
├── adversary.py              # Pass 2a-C: STRUCTURAL independence (reads stories ONLY)
├── independence.py           # NEW: measures correlation between sensors, emits guardrail
├── interlock.py              # NEW: EXPECT-before-ACTION framework enforcement (v1)
├── walker.py                 # Pass 1: story walker (deterministic)
├── proxy.py                  # Pass 2b: human-proxy with EXPECT/ACTION/OBSERVE
├── progress_evaluator.py     # Lifecycle-progress check (motion vs work)
├── extractor.py              # Transcript → structured findings
│                             # + evidence_embedded for self-contained findings
├── paraphrase.py             # Story paraphrase-confirm loop + spec_stale loop
├── backlog.py                # fitness-backlog.md reader/writer
├── corrector.py              # Two-gate router; generates fix + alternative
├── comparator.py             # FitnessDiff_n vs FitnessDiff_{n-1}, regression detect
├── budget.py                 # NEW: token budget + degradation ladder
├── maturity.py               # Reads [dazzle.maturity].level from TOML
└── missions/
    ├── story_walk.py
    └── free_roam.py
```

### 5.3 Storage layout

| Path | Purpose | Git-tracked |
|---|---|---|
| `pyproject.toml` (or `app.toml`) `[dazzle.maturity].level` | Maturity flag (mvp/beta/stable) | yes |
| `pyproject.toml` `[dazzle.fitness]` | Per-cycle token budget, independence threshold, TTLs | yes |
| `.dazzle/fitness-runs/YYYY-MM-DD-<persona>-<run-id>.jsonl` | Per-run transcripts (EXPECT/ACTION/OBSERVE stream). **TTL = 30 days** | no (`.gitignore`) |
| `.dazzle/fitness-ledger/<run-id>.jsonl` | Per-run ledger records (before/after/diff). **TTL = 30 days** | no |
| `dev_docs/fitness-backlog.md` | Durable findings (self-contained via `evidence_embedded`) | yes |
| `dev_docs/fitness-log.md` | Append-only run log | yes |

**Evidence-embedding rule:** every `Finding` embeds enough context (expected/observed/delta/transcript excerpt ±3 steps) to be evaluable after the underlying ledger has expired. Findings are durable; ledgers are ephemeral evidence. See §8.

## 6. The three passes

### 6.1 Pass 1 — Story Walker (deterministic verification)

**Inputs:** DSL stories, running app, persona credentials, expected-state manifest (derived from each story's postconditions using the DSL's `evidence_predicate` for lifecycle transitions).

**Behaviour:** For each story belonging to persona P:
1. Authenticate as P
2. Run the scripted Playwright sequence derived from the story's action steps
3. Record observed DOM + HTTP responses
4. At mission end, diff ledger against story-derived expectation
5. Run `progress_evaluator` over the entities touched — did they advance through their declared lifecycle with valid evidence?
6. Emit Pass-1 findings for any mismatch

**Cognition profile:** zero LLM calls. Deterministic script execution. Runs every cycle at minimum.

### 6.2 Pass 2a — Spec Cross-check (agentic validation with structural independence)

**Three sub-steps, run serially:**

**Sub-step A — `spec_extractor`:**
- Reads ONLY `spec.md` (no access to DSL)
- Prompt: "extract the list of jobs-to-be-done implied by this spec; for each job, note the persona"
- Output: capability list C_spec

**Sub-step B — `cross_check`:**
- Takes C_spec (from sub-step A) and the DSL story list
- Emits coverage findings for capabilities with no matching story
- Emits over-implementation findings for stories with no matching capability

**Sub-step C — `adversary` (STRUCTURAL independence):**
- Reads ONLY the DSL story list (**NO access to spec.md**)
- Prompt: "synthesize a plausible capability list from these stories alone; what is this app trying to do?"
- Output: capability list C_stories
- **Mechanism:** the adversary reads a different document entirely. There is no prompt overlap with sub-step A — the independence is structural, not prompt-surface.
- **Optional strengthening:** configure `adversary.py` to use a different model family from the `spec_extractor` (e.g., one uses Claude, the other uses GPT) via the `[dazzle.fitness.independence_mechanism]` config: `{prompt_only | model_family | model_family_and_seed}`.

**Sub-step D — `independence` (empirical guardrail):**
- Computes the symmetric difference of C_spec (from A) and C_stories (from C)
- Measures Jaccard similarity and capability-wise disagreement rate
- If similarity > threshold T (default 0.85), emits `INDEPENDENCE_DEGRADED` signal — the sensors are too correlated and the Kalman assumption is broken
- When degraded, current cycle's validation findings are marked `low_confidence=true`
- The metric is logged per-cycle in `fitness-log.md` so drift is visible

**Cognition profile:** 2-4 LLM calls per cycle. No Playwright. Cheap compared to Pass 2b.

### 6.3 Pass 2b — Human Proxy (agentic verification, behavioural, hard-interlocked)

**Inputs:** running app, persona assignment, high-level intent, step budget from `budget.py`.

**Behaviour:** Agent drives the app via Playwright using the **EXPECT/ACTION/OBSERVE protocol**. Every tool call is wrapped by `interlock.py`:

```python
def interlocked_tool_call(tool, args):
    last_step = ledger.current_step()
    if last_step.expect is None or last_step.expect.strip() == "":
        raise InterlockError(
            "Tool call rejected: no EXPECT recorded for this step. "
            "Emit `expect: <what you think will happen>` before calling tools."
        )
    result = tool(**args)
    ledger.record_observation(step=last_step, observed=result)
    return result
```

**Why hard interlock in v1, not v2:** prompt discipline for structured protocol output is famously unreliable across long agent runs. By step 30 of 50, the agent will drift. The interlock is ~30 lines of code and eliminates an entire failure class at minimal cost.

**v2 goes further:** replaces the "reject with error" pattern with a "synthesize EXPECT via second LLM call, then execute" pattern. That's more expensive but never blocks progress. v1's rejection pattern is the cheaper v0.9 version.

**Cognition profile:** full-budget agent mission (30-50 steps), shortened under budget pressure (see §12).

## 7. FitnessLedger contract

### 7.1 Abstraction surface

```python
class FitnessLedger:
    def open(self, run_id: str) -> None: ...
    def record_intent(self, step: int, expect: str, action_desc: str) -> None: ...
    def record_observation(self, step: int, observed: Any) -> None: ...
    def current_step(self) -> LedgerStep: ...
    def summarize(self) -> FitnessDiff: ...
    def close(self, rollback: bool = False) -> None: ...
```

### 7.2 `FitnessDiff` schema

```python
@dataclass(frozen=True)
class FitnessDiff:
    run_id: str
    steps: list[LedgerStep]  # Total-ordered per-run (step_no ascending; v1.2 also LSN)
    created: list[RowChange]
    updated: list[RowChange]
    deleted: list[RowChange]
    progress: list[ProgressRecord]
    semantic_repr_config: dict

@dataclass(frozen=True)
class LedgerStep:
    step_no: int                     # Dense per-run counter (1, 2, 3…). Definitive total order.
    txn_id: str | None               # Populated from v1.1+ (SAVEPOINT); LSN-grouped in v1.2
    expected: str                    # EXPECT field — MANDATORY (interlock enforces)
    action_summary: str
    observed_ui: str
    observed_changes: list[RowChange]
    delta: Delta                     # EXPECTED − OBSERVED (the fitness signal)

@dataclass(frozen=True)
class RowChange:
    table: str
    row_id: str
    kind: Literal["insert", "update", "delete"]
    semantic_repr: str               # Compact projection using DSL `fitness.repr_fields`
    field_deltas: dict[str, tuple]
```

### 7.3 `fitness.repr_fields` — MANDATORY per entity (closed from §15 open question)

Every entity that participates in fitness evaluation MUST declare a `fitness.repr_fields` list in the DSL:

```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  status: enum[new, assigned, in_progress, resolved, closed] required
  assignee_id: ref User
  created_at: datetime
  updated_at: datetime
  resolution_notes: text

  fitness:
    repr_fields: [title, status, assignee_id, updated_at]
```

**Why mandatory:** defaulting to `list_columns` is the path of least resistance but would silently weaken every conformance finding. `list_columns` is UI-optimised (what users see in lists); `repr_fields` is domain-optimised (what matters for semantic correctness — status transitions, FK links, lifecycle timestamps).

**Enforcement:** `dazzle validate` emits a lint error if any entity lacks `fitness.repr_fields`. The error is NON-FATAL for v1 (warn, don't fail) but becomes FATAL in v1.1 once adoption is normalized.

### 7.4 Implementation roadmap

| Version | Strategy | Isolation | Ordering | Fidelity |
|---|---|---|---|---|
| **v1** | Snapshot diff | None (shared pool) | Dense step_no counter | Covers INSERT/UPDATE/DELETE on polled tables |
| **v1.1** | SAVEPOINT wrapping | Full transactional | step_no + txn_id | No pollution; one connection required |
| **v1.2** | Logical replication slot | None | step_no + LSN-grouped | Exact fidelity, captures async workers, agent-ergonomic |

## 8. Finding schema

```
Finding:
  id:                  FIND-NNN
  created:             ISO timestamp
  run_id:              FK to fitness run (ephemeral, may be expired)
  cycle:               FK to /ux-cycle or N/A
  axis:                coverage | conformance
  locus:               implementation | story_drift | spec_stale | lifecycle
  severity:            critical | high | medium | low
  persona:
  capability_ref:      spec clause OR story ID
  expected:
  observed:
  evidence_embedded:   ← NEW (self-contained when ledger expires)
    expected_ledger_step: { expect, action, observed, delta }
    diff_summary: [top 3 row changes]
    transcript_excerpt: [±3 steps around the step that produced the finding]
  disambiguation:      bool
  low_confidence:      bool  ← NEW (set when INDEPENDENCE_DEGRADED was emitted this cycle)
  status:              PROPOSED | ACCEPTED | IN_PROGRESS | FIXED | VERIFIED | REJECTED
  route:               hard | soft
  fix_commit:          git SHA when fixed
  alternative_fix:     ← NEW (corrector-emitted plausible alternative — drives disambiguation)
```

**Axis × locus matrix:**

| axis \ locus | implementation | story_drift | spec_stale | lifecycle |
|---|---|---|---|---|
| **coverage** | rare | common | common | rare |
| **conformance** | common | common | rare | common |

**`low_confidence` handling:** findings produced during a cycle where `INDEPENDENCE_DEGRADED` fired are flagged. Hard correction is disabled for low-confidence findings regardless of maturity — they all route to soft mode until independence is re-established.

## 9. Corrector

### 9.1 Two-gate routing

```python
def route_finding(finding: Finding, maturity: str) -> Route:
    # Gate 0: low-confidence findings ALWAYS go soft
    if finding.low_confidence:
        return Route.SOFT

    # Gate 1: maturity kill-switch
    if maturity == "stable":
        return Route.SOFT

    # Gate 2: mechanical disambiguation check
    if finding.disambiguation:
        return Route.SOFT

    return Route.HARD
```

### 9.2 Mechanical disambiguation (new in v2)

Replaces self-reported uncertainty with a generate-alternative check:

```python
def generate_fix(finding: Finding) -> tuple[Fix, Fix | None]:
    # Generate BOTH a chosen fix and at least one plausible alternative
    primary = llm.generate_fix(finding, variant="best")
    alternative = llm.generate_fix(finding, variant="different_approach")

    # Compare
    if alternative and not materially_same(primary, alternative):
        finding.disambiguation = True
        finding.alternative_fix = alternative
    else:
        finding.disambiguation = False

    return primary, alternative
```

`materially_same()` is a heuristic over the fix's touched files and semantic intent. Two fixes that edit the same file with the same resulting diff are "same"; two fixes that touch different layers (template vs route vs DSL) or change semantics are "different".

The corrector no longer asks itself "did you feel uncertain?" — that's known to under-report. Instead it is REQUIRED to generate an alternative, and the alternative's existence (when materially different) mechanically flags disambiguation.

### 9.3 `spec_stale` routing

When a finding has `locus=spec_stale`, the corrector routes it through `paraphrase.py`:

```python
if finding.locus == "spec_stale":
    return paraphrase_spec_revision(finding)
    # Produces a human-readable "should I update your spec?" prompt
    # Founder confirms/rejects/corrects
    # On confirm → corrector edits spec.md and commits
```

Recognition-not-Generation applied to spec revisions.

## 10. Regression detection (non-monotonic fitness)

Comparator step runs every cycle:

```python
def compare_runs(current: FitnessDiff, previous: FitnessDiff) -> RegressionReport:
    new_findings = current.findings - previous.findings
    fixed_findings = previous.findings - current.findings
    persistent_findings = current.findings & previous.findings

    if new_findings and previous_cycle_had_hard_correction:
        escalate_or_revert()   # the correction introduced regression

    return RegressionReport(new=new_findings, fixed=fixed_findings,
                            persistent=persistent_findings)
```

**Policy:**
- Hard correction + new findings = regression. Convert the original finding to a PR OR auto-revert.
- Same finding persists N consecutive cycles = mark `BLOCKED` (corrector can't fix).
- Oscillating findings = mark `REGRESSION` class (unstable corrector strategy).

## 11. Paraphrase-confirm loop

On-demand (not per-cycle). Flow:

1. Agent selects a batch of stories (default: all `status=provisional` stories)
2. LLM generates plain-English paraphrases with NO framework vocabulary
3. Paraphrases presented to the founder (via MCP tool response or `/review-stories` for dazzle-team)
4. Founder responds per paraphrase: `confirm | correct: <text> | unclear`
5. Confirmations mark the story `audited=true`; corrections become `story_drift` findings.

### 11.1 Graduation criterion

- `N = 3` consecutive paraphrase cycles with zero corrections on a specific story → graduate from `provisional` to `confirmed`
- A single correction resets the counter to `0` (not decrement). Confirmation loss is sharp, not gradual.
- `confirmed` stories unlock tighter adversary auditing — the independence threshold rises for them.
- `confirmed` stories can revert to `provisional` if a correction arrives later.

### 11.2 Spec-stale via paraphrase

`spec_stale` findings feed into the same paraphrase pipeline but with a different prompt template: "Based on how you're using the app, it looks like you actually want X. Your spec currently says Y. Should I update the spec to reflect X?"

Founder confirmation triggers a `spec.md` edit commit.

## 12. Integration surfaces + budget

### 12.1 Per-cycle token budget and degradation order

```toml
[dazzle.fitness]
max_tokens_per_cycle = 100_000
max_wall_time_minutes = 10
independence_threshold_jaccard = 0.85
ledger_ttl_days = 30
transcript_ttl_days = 30
paraphrase_graduation_rounds = 3

[dazzle.fitness.independence_mechanism]
primary = "prompt_plus_model_family"   # prompt_only | prompt_plus_model_family | prompt_plus_model_and_seed
```

**Degradation ladder** (when budget is tight):

1. First shed: Pass 2b free-roam mission shortened (50 → 20 steps)
2. Then: Pass 2a adversary sub-step skipped (spec_extractor still runs, independence metric emits `INSUFFICIENT_DATA`)
3. Then: Pass 2b dropped entirely (Pass 1 + spec_extractor only)
4. Pass 1 walker is NEVER shortened or dropped — it's the cheapest and the most reliable signal.

Degraded cycles emit `FITNESS_DEGRADED` signal so downstream consumers know the run was budget-constrained. Findings from degraded cycles inherit `low_confidence=true` for any pass that was shortened or skipped.

### 12.2 /ux-cycle strategy (Dazzle team)

New enum value `Strategy.FITNESS`. Integration at the existing cycle level:

- Acquires `.dazzle/ux-cycle.lock`
- Picks a rotating example app
- Starts the example's runtime
- Runs `fitness.engine.run(example_app)` with the configured budget
- Writes findings to `examples/<app>/dev_docs/fitness-backlog.md`
- Commits per cycle discipline
- Releases the lock

Rotates alongside `MISSING_CONTRACTS` and `EDGE_CASES`.

### 12.3 `mcp__dazzle__fitness` (users)

MCP tool with subcommands:

```
mcp__dazzle__fitness.run()                # full cycle
mcp__dazzle__fitness.status()             # findings summary
mcp__dazzle__fitness.findings(axis=)
mcp__dazzle__fitness.findings(locus=)
mcp__dazzle__fitness.confirm_stories()    # paraphrase-confirm loop
mcp__dazzle__fitness.review(finding_id)
mcp__dazzle__fitness.independence()       # current independence metric + trend
```

### 12.4 External aggregation (Dazzle team only, weekly)

Weekly aggregator job reads `fitness-backlog.md` across example apps, groups findings thematically, produces GitHub issues with `fitness-report` labels. Marketing/community signal, not internal tracking.

## 13. File layout summary

```
src/dazzle/fitness/
  engine.py
  ledger.py
  ledger_snapshot.py
  ledger_savepoint.py
  ledger_wal.py
  spec_extractor.py
  cross_check.py
  adversary.py
  independence.py        ← NEW
  interlock.py           ← NEW
  walker.py
  proxy.py
  progress_evaluator.py  (depends on lifecycle ADR)
  extractor.py
  paraphrase.py
  backlog.py
  corrector.py           (with alt-generation)
  comparator.py
  budget.py              ← NEW
  maturity.py
  missions/
    story_walk.py
    free_roam.py

tests/unit/fitness/
tests/e2e/fitness/

src/dazzle/mcp/server/handlers/fitness.py
src/dazzle/cli/runtime_impl/fitness_strategy.py

dev_docs/fitness-backlog.md        # self-contained findings
dev_docs/fitness-log.md            # per-cycle append log (incl. independence metric)
.dazzle/fitness-runs/              # TTL 30d, gitignored
.dazzle/fitness-ledger/            # TTL 30d, gitignored

docs/reference/fitness-methodology.md
docs/adr/NNNN-lifecycle-evidence-predicates.md  ← PREREQUISITE ADR
```

## 14. Implementation roadmap

### Prerequisite — ADR micro-plan (blocking v1)

- Extend the `process` DSL construct with `evidence_predicate` per transition and `progress_order` on states
- Make it mandatory for entities that participate in fitness progress evaluation
- `dazzle validate` warns (v1) / errors (v1.1) if missing
- This ADR lands FIRST. Fitness v1's `progress_evaluator.py` depends on it.

### v1 — Ship the skeleton

- `FitnessLedger` with v1 snapshot implementation
- Pass 1 walker against DSL stories (requires lifecycle ADR)
- Pass 2a three sub-steps + `independence.py` metric
- Pass 2b proxy with EXPECT/ACTION/OBSERVE + **hard interlock in v1**
- Structural-independence adversary (stories-only) as default
- `progress_evaluator.py` for lifecycle-declared entities
- `extractor.py` producing self-contained findings
- `backlog.py`
- Corrector with **alternative-generation** (not self-reported uncertainty)
- Hard-mode correction; `spec_stale` still goes soft via paraphrase
- `budget.py` with degradation ladder
- /ux-cycle `Strategy.FITNESS` integration
- `fitness.repr_fields` lint warning (not error)
- Unit tests + E2E test against `support_tickets`

**v1 success criteria:**
1. Cycle runs end-to-end against `support_tickets` without human intervention
2. Surfaces at least one conformance finding
3. No false positives on silent data changes
4. `independence_correlation` metric is published in `fitness-log.md` every cycle
5. At least one intentionally-buggy correction is caught by the regression comparator (self-validation)

### v1.1 — Harden for user apps

- `FitnessLedger` v1.1 SAVEPOINT implementation
- Soft-mode corrector (PR generation)
- `mcp__dazzle__fitness` MCP tool full surface
- Paraphrase-confirm loop full implementation (v1 ships `paraphrase.py` interface but UX wiring is v1.1)
- `fitness.repr_fields` becomes fatal lint error
- User-facing docs
- Independence mechanism config defaults to `model_family` if API keys for both providers are present

### v1.2 — WAL substrate (target architecture)

- `FitnessLedger` v1.2 WAL subscriber
- Transaction grouping in `FitnessDiff`
- Background-worker coverage
- Regression comparator tightens to "fitness strictly non-increasing across hard corrections"

### v2 — Tool-call introspection wrapper

- Replace interlock's "reject" pattern with "synthesize EXPECT via second LLM call"
- Full EXPECT+OBSERVE framework generation (no prompt discipline required)
- Adversarial mutation testing (inject known failures, verify the engine catches them)

### v2.1 — Aggregation + public reporting

- Weekly aggregator job, GitHub Issue generation, community signal

## 15. Open questions

1. **Persona coordination:** sequential (v1) vs parallel (v1.2). Decision deferred to v1.1.
2. **Mission budget empirical validation:** first cycles may reveal that 30-50 steps is wrong. Budget tuning is part of the v1 validation criteria.
3. **Independence threshold T:** default 0.85, but empirical validation should adjust this. If all early cycles emit `INDEPENDENCE_DEGRADED`, T is too strict; if none ever do, T is too loose.
4. **Adversary model family:** does the v1 default use the same model as spec_extractor with just different prompts, or start with model-family diversity? Cost question — model diversity requires two provider API keys.
5. **Cycle cadence inside /ux-cycle:** how often does FITNESS rotate in? TBD, tune based on signal-to-noise.
6. **`--success` / `--warning` design tokens:** independent concern, referenced throughout the UX cycle. Should land in `design-system.css` regardless.

## 16. Success criteria (v1)

1. Detects a real conformance finding that `/ux-cycle` wouldn't catch (proof of differentiated value)
2. Localises at least one finding correctly across disagreement-locus axes (proof of triangulation value)
3. Hard-mode corrector produces a committable fix for at least one finding without manual editing
4. Regression comparator catches at least one induced regression (self-validation)
5. Runs to completion in under 10 minutes per example app
6. `independence_correlation` metric published every cycle (proof of empirical independence guardrail)

## 17. Appendix: cognitive framing (Kalman filter metaphor)

The methodology is a **Kalman filter over system correctness**. Three noisy sensors measure the same latent variable ("is the system right?"):

- `spec.md` — what the founder intended
- DSL stories — what /bootstrap thought the founder meant (mediated by LLM)
- Observed behaviour — what the running app actually does

`FitnessDiff` is the **innovation** (predicted − observed). The corrector is the **update step**.

Kalman filters work because sensors have **independent noise**. If corners share a common origin, the whole thing degrades. That's why:

- The adversary reads ONLY stories (no spec.md overlap) — structural independence
- An optional second independence mechanism is different model families or seeds — mechanical independence
- `independence_correlation` is measured every cycle — empirical guardrail
- `low_confidence=true` is set when independence degrades — findings from a "noisy-sensor" cycle are prevented from auto-committing

Guarding corner independence is the design discipline. It's the most important thing in the document.

---

**End of design document. Ready for review (v2, post-feedback).**
