# UX Cycle — Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Related:** ux-architect skill, QA mode (#768), AegisMark `/bdd-cycle` pattern

## Goal

Build a `/ux-cycle` slash command that iteratively brings Dazzle's UX layer under ux-architect governance and validates quality via agent-led QA against real example apps. Close the loop between top-down specification (ux-architect contracts) and bottom-up observation (agent QA exploration).

## Motivation

We now have three aligned pieces:

1. **ux-architect skill** — defines what good UX looks like via frozen token sheets, component contracts, interaction primitives, and stack adapters
2. **QA mode** — turns example apps into agent-drivable test beds via dev persona magic links (#768)
3. **DazzleAgent framework** — drives Playwright as any persona, runs missions with tool calls, tracks observations

What's missing is a loop that drives these toward improvement. Manually picking one component at a time (dashboard, data-table) has proven viable — now we automate the cycle.

## Non-goals

- Rewriting the existing `/improve` or `/ux-converge` loops (they handle different work)
- Vision-based visual quality checks (deferred to v2 — requires vision model integration)
- Multi-repo or cross-project support (Dazzle-specific for v1)
- Replacing human QA entirely — this loop finds most regressions; a human still validates aesthetics and feel
- Auto-promoting PROPOSED exploration findings to PENDING without human gate (one-time human confirmation required)

## Decisions

### 1. Scope of backlog

**UX components as rows, one row per spec-governable UI concept.** Components like `dashboard-grid`, `data-table`, `card`, `form`, `modal`, `widget:combobox`, `filter-bar`, `pagination`.

Rejected alternatives:
- Interaction backlog (too fine-grained; interactions are derivable from contract quality gates)
- Component × example matrix (too many rows; canonical + sampled approach catches cross-app issues more efficiently)

### 2. QA strategy

**Two-phase: HTTP contracts first, then Playwright agent mission.**

- **Phase A (fast):** Run `dazzle ux verify --contracts` against the canonical example. Catches ~80% of regressions at structural level. Takes seconds.
- **Phase B (slow):** If Phase A passes AND the component contract defines interaction primitives, dispatch a `DazzleAgent` Playwright mission per persona to exercise the quality gates. Takes 1–3 minutes per persona.

Rejected alternatives:
- HTTP-only (misses interaction bugs like setPointerCapture from #770)
- Playwright-only (slow; wastes time on regressions HTTP could have caught)
- Playwright + vision model (deferred — vision cost and false positives need separate tuning)

### 3. Example app selection

**Canonical + sampled.** Each row declares a `canonical` example (always run) and an `applies` list. Each cycle runs QA against canonical + one rotating sample from `applies`. Over 3–5 cycles every applicable example is exercised; every cycle uses at most 2 apps.

Rejected alternatives:
- Single canonical (misses cross-app issues entirely)
- All applicable apps every cycle (too slow — 5 apps × 5 personas × 5 gates = 125 sessions)

### 4. EXPLORE mode

**Two strategies alternating when backlog is empty:**

- **Strategy A: Missing contracts** — agent explores the canonical example as a random persona looking for interactions that have no ux-architect contract. Produces `PROPOSED` rows that need human confirmation before becoming `PENDING`.
- **Strategy B: Edge cases on shipped components** — agent re-tests `DONE`/`VERIFIED` components with adversarial inputs (empty state, max content, keyboard shortcuts, etc.) looking for gate failures not covered by the 5-gate contract. Produces `EX-NNN` finding rows that feed back into the REFACTOR queue.

Strategy C (visual quality via vision model) deferred to v2.

**Stop conditions:**
- 30 explore cycles per session max
- 5 consecutive cycles with no new findings
- Whichever comes first

### 5. Placement and name

**Project-level slash command at `.claude/commands/ux-cycle.md`.** The loop is Dazzle-specific and version-controlled alongside the code it operates on.

### 6. Cycle budget

**One component per cycle, no time limit, per-phase stagnation check.** A phase is aborted and the row marked BLOCKED if no progress for 3 minutes. Concurrency lock at `.dazzle/ux-cycle.lock` with 45-minute age cap.

### 7. Scheduling

Default: `/loop 30m /ux-cycle` when running in a dev session — the **interval between cycles** is 30 minutes, not a per-cycle budget. A cycle that completes in 8 minutes means the next fires 22 minutes later. A cycle that takes 35 minutes means the next fires immediately after. Manual invocation `/ux-cycle` for focused work. Self-paced `/loop /ux-cycle` lets the model decide cadence based on work remaining.

## Architecture

### The 7-step cycle

```
Step 0a  — Preflight (lock check, stale-lock cleanup, signal check)
Step 0b  — Init (first run only: seed dev_docs/ux-backlog.md from skill + code scan)
Step 1   — OBSERVE (pick next row by priority; mark IN_PROGRESS)
Step 2   — SPECIFY (invoke ux-architect skill to write/refine contract if missing)
Step 3   — REFACTOR (apply contract to code — template + JS + backend)
Step 4   — QA (HTTP contracts → Playwright agent mission)
Step 5   — REPORT (update backlog, log, commit, emit signal)
Step 6   — EXPLORE (when no PENDING rows remain — see strategies above)
Step 7   — Complete (write last-run timestamp, release lock)
```

**Priority function for OBSERVE:**
1. REGRESSION rows first
2. PENDING rows with contract: MISSING and impl: PENDING
3. PENDING rows with contract: DRAFT
4. DONE rows with qa: PENDING
5. VERIFIED rows last

### Backlog format

**File:** `dev_docs/ux-backlog.md` — markdown table, committed to repo.

**Columns:**

| Column | Values |
|---|---|
| `id` | `UX-NNN` (components), `EX-NNN` (exploration findings), `PROP-NNN` (proposed components) |
| `component` | Kebab-case name matching `~/.claude/skills/ux-architect/components/<name>.md` |
| `status` | `PROPOSED` / `PENDING` / `IN_PROGRESS` / `DONE` / `VERIFIED` / `BLOCKED` / `REGRESSION` |
| `contract` | `MISSING` / `DRAFT` / `DONE` |
| `impl` | `PENDING` / `PARTIAL` / `DONE` |
| `qa` | `PENDING` / `PASS` / `FAIL` / `BLOCKED` |
| `canonical` | Example app name for QA |
| `applies` | Comma-separated list of example apps that use this component |
| `attempts` | Integer |
| `last_cycle` | ISO date |
| `notes` | Free-form |

**State machine:**

```
PROPOSED ──(human confirmation)──► PENDING ──► IN_PROGRESS ──► DONE ──(N clean cycles)──► VERIFIED
                                     ▲              │              │
                                     │              ▼              │
                                     └────── BLOCKED           REGRESSION ──┐
                                                                            │
                                                  ◄─────────────────────────┘
```

**Initial seed:**

First invocation walks `~/.claude/skills/ux-architect/components/` for existing contracts (dashboard-grid, card, data-table → `DONE` rows) and scans Dazzle's UI fragments/widgets (form, modal, filter-bar, search-input, pagination, widget:* → `PENDING` rows with `contract: MISSING`).

### QA mission — the new piece of the agent framework

**File:** `src/dazzle/agent/missions/ux_quality.py`

**Function:** `build_ux_quality_mission(component_contract: Path, persona: PersonaSpec, example_app: str) -> Mission`

**Behaviour:**

1. Parse the component contract markdown to extract:
   - `## Quality Gates` section (5 testable behaviours)
   - Component anatomy (named DOM parts) for locator hints
   - Interaction primitives listed under `Primitives invoked`

2. Build system prompt telling the agent:
   - Role: QA-test the `{component}` as persona `{persona.label}`
   - Spec location: `{component_contract_path}`
   - Quality gates to verify
   - Use `record_gate_result` tool to report pass/fail per gate

3. Start the agent with a Playwright observer. First action: log in via QA mode magic link endpoint (`POST /qa/magic-link`). Then navigate and drive the gates.

4. Complete when all gates are recorded, stagnation triggers, or budget exhausted.

**New agent tool:** `record_gate_result(gate_id: str, pass: bool, observation: str)` — records a structured result in a dict passed by reference from the mission builder.

**Stagnation criteria:** 5 consecutive steps with no `record_gate_result` tool call → completion with incomplete results (treated as BLOCKED).

**Output shape:**

```python
{
    "component": "data-table",
    "persona": "accountant",
    "example_app": "contact_manager",
    "gates": {
        "gate_id": {"pass": bool, "observation": str},
        ...
    },
    "steps_used": int,
    "tokens_used": int,
}
```

### Contract parser helper

**Added to:** `src/dazzle/agent/missions/_shared.py`

**Function:** `parse_component_contract(path: Path) -> ComponentContract`

```python
@dataclass
class ComponentContract:
    component_name: str
    quality_gates: list[QualityGate]
    anatomy: list[str]  # named DOM parts
    primitives: list[str]  # interaction primitive IDs
    tokens_consumed: list[str]  # for future vision checks

@dataclass
class QualityGate:
    id: str  # derived from gate description, e.g. "drag_threshold"
    description: str  # the full gate text from the contract
```

The parser reads the markdown, locates sections by their `##` headings, and extracts:
- Quality gates from the numbered list under `## Quality Gates`
- Anatomy from the bullet list under `## Anatomy`
- Primitives from `## Primitives invoked` (if present)

### Signal bus

**File:** `src/dazzle/cli/runtime_impl/ux_cycle_signals.py`

Ported from AegisMark's `pipeline/qa/signals.py` pattern — ~60 lines. Flat-file signals at `.dazzle/signals/*.json`.

**API:**
```python
def emit(source: str, kind: str, payload: dict) -> None: ...
def since_last_run(source: str) -> list[Signal]: ...
def mark_run(source: str) -> None: ...
```

**Signals emitted by `/ux-cycle`:**

| Signal | When |
|---|---|
| `ux-component-shipped` | Row moves to DONE with qa: PASS |
| `ux-regression` | VERIFIED row moves to REGRESSION |
| `ux-exploration-finding` | EXPLORE creates new EX-NNN or PROP-NNN row |

**Signals consumed by `/ux-cycle`:**

| Signal | Emitted by | Action |
|---|---|---|
| `dazzle-updated` | `/improve`, `/bdd-cycle` | Retry BLOCKED rows |
| `fix-deployed` | Any loop after commit | Re-verify affected component |
| `ci-failure` | CI monitor (future) | Pause EXPLORE mode |

### Concurrency lock

**File:** `.dazzle/ux-cycle.lock`

Contains PID and ISO timestamp. On startup:
1. No lock file → create with current PID + timestamp, proceed
2. Lock exists, timestamp < 45 minutes old → abort (another cycle running)
3. Lock exists, timestamp >= 45 minutes old → delete as stale, create fresh, proceed

On exit (success or failure), delete the lock.

### EXPLORE mission

**File:** `src/dazzle/agent/missions/ux_explore.py`

Two strategies, selected alternately per invocation:

**Strategy A: Missing contracts**
- Navigate the canonical example as a random persona
- Look for interactions that are notable but have no contract (drag, drop, inline edit, keyboard shortcuts, modals, etc.)
- Use `propose_component` tool to register findings — produces `PROP-NNN` rows

**Strategy B: Edge cases on shipped components**
- For each `DONE`/`VERIFIED` component, run the QA mission with adversarial inputs (empty state, max content, keyboard-only, rapid interactions)
- Use `record_edge_case` tool for failures outside the defined gates — produces `EX-NNN` rows

**Stop conditions:** 30 explore cycles per session OR 5 consecutive no-finding cycles.

## Files Changed

| File | Action | Purpose |
|---|---|---|
| `.claude/commands/ux-cycle.md` | Create | Slash command with the 7-step cycle prompt |
| `dev_docs/ux-backlog.md` | Create (first run) | Persistent backlog |
| `dev_docs/ux-log.md` | Create (first run) | Append-only cycle log |
| `src/dazzle/agent/missions/ux_quality.py` | Create | Contract-driven Playwright QA mission |
| `src/dazzle/agent/missions/ux_explore.py` | Create | Bottom-up gap discovery mission |
| `src/dazzle/agent/missions/_shared.py` | Modify | Add `parse_component_contract()` + `ComponentContract`/`QualityGate` dataclasses |
| `src/dazzle/cli/runtime_impl/ux_cycle_signals.py` | Create | Flat-file signal bus |
| `tests/unit/test_ux_quality_mission.py` | Create | Tests for QA mission builder and tool registration |
| `tests/unit/test_ux_explore_mission.py` | Create | Tests for EXPLORE strategies |
| `tests/unit/test_ux_cycle_signals.py` | Create | Signal bus tests |
| `tests/unit/test_parse_component_contract.py` | Create | Markdown parser tests |
| `.gitignore` | Modify | Ignore `.dazzle/signals/` and `.dazzle/ux-cycle.lock` |

## Testing Strategy

**Unit tests:**
- Contract parser: extracts quality gates, anatomy, primitives from sample markdown
- QA mission builder: constructs a mission with correct system prompt and tools
- `record_gate_result` tool handler writes to the shared results dict
- Signal bus: emit/read/mark_run round-trip
- Backlog row parsing: reads existing backlog, updates status, writes back

**Integration tests:**
- Run a QA mission end-to-end against the dashboard test harness (existing `test-dashboard.html`) — should pass all 5 gates against the spec-governed dashboard we shipped in v0.54.0
- Run against the data-table test harness similarly

**No end-to-end test of the full cycle** in v1 — testing the cycle itself requires a running example app with auth, which is expensive. Instead, the cycle is tested manually by invoking `/ux-cycle` on the dev branch and observing that it picks a row, does the work, and updates the backlog correctly.

## Quality Gates

1. **Seed reproducibility:** Running the first-time init on a clean clone produces the same backlog twice in a row (deterministic ordering)
2. **Idempotent state updates:** Running the loop on a backlog where all rows are DONE/VERIFIED produces no git diff (no spurious changes)
3. **QA mission gate extraction:** Given `components/data-table.md`, the parser returns exactly 5 quality gates with non-empty IDs and descriptions
4. **Signal round-trip:** Emit a signal, another process reads it, marks its run, does not read it again
5. **Lock safety:** Two simultaneous `/ux-cycle` invocations — second one aborts cleanly with a clear message

## Open Questions for v2

- **Visual quality check via vision model** — when to add, what budget, how to avoid false positives on rendering differences that don't matter (fonts on different machines, etc.)
- **Multi-tenant examples** — the dev tenant is singular in QA mode; some examples may have multi-tenant stories that need per-tenant QA runs
- **Cross-loop orchestration** — should there be an `/autonomous` command like AegisMark's that fires `/ux-cycle`, `/improve`, `/ux-converge` on separate schedules with signal-based coordination?
- **Contract versioning** — what happens when a component contract is updated but shipped code is on an older version? Need a "contract version" field on backlog rows
- **Rollback** — if a REFACTOR makes QA fail, the cycle currently leaves the code broken pending human review. Should it auto-rollback via git? (Probably not — the broken state is informative)

## Deferred Items

- Strategy C in EXPLORE (visual quality via vision model) — adds cost and complexity; v1 ships without
- Generalisation step (like `/babysit`'s "where else does this class of problem exist") — valuable but complex; add in v2 once the basic cycle is stable
- Auto-escalation to GitHub issues for BLOCKED rows — v1 just leaves them in the backlog with a note; manual escalation via `/issues`
