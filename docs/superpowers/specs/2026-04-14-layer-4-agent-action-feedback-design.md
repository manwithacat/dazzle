# Layer 4 — Agent Action Feedback and Persona Fan-Out

**Status:** Draft (cycle 197)
**Author:** Claude (via `/ux-cycle` harness evaluation session, 2026-04-14)
**Driving goal:** make `/ux-cycle` Step 6 EXPLORE reliably produce non-empty PROP-NNN / EX-NNN findings across the 5 `examples/` Dazzle apps, so the UX backlog replenishes itself as a normal consequence of the harness running.

## Context

After cycle 195's DazzleAgent builtin-action-as-tool fix (v0.55.2), the `/ux-cycle` explore driver can boot an example app, log a persona in, and run 8 real agent steps via native tool use. The mechanical pieces work. But cycle 196 — the first real production-driver EXPLORE run — produced 0 proposals because the agent click-looped on `a:has-text("Contacts")` against contact_manager as the admin persona. The click was firing at Playwright level, the page wasn't changing, and the LLM had no signal that its actions were no-ops, so it kept issuing the same action for 8 steps until stagnation fired.

Cycle 195's log identified this as a new harness layer:

> **Layer 4 — Agent click-loop on non-navigating actions.** Previously hidden behind the cycle 195 step-1 early exit. Now visible: the agent takes real actions but has no feedback about whether they accomplished anything, and will spend tokens looping on dead-end selectors until stagnation terminates the run.

This spec addresses Layer 4 with four concrete changes, plus a persona-selection refactor that unblocks multi-app coverage (D2 — "non-empty runs against all 5 `examples/`"). The longer-term goal the harness is building toward: **autonomous agent activity that detects incongruence between the running app and the DSL contract, and produces actionable findings from that incongruence**. This spec establishes the foundations (action→consequence linkage, persona fan-out, cognition-signal foothold) that later cycles will build on.

## Success criterion

**D2** — Cycle 197 delivery bar:

- `run_explore_strategy` with `strategy=Strategy.MISSING_CONTRACTS` and default `personas=None` produces `outcome.degraded is False` against all 5 apps in `examples/` (simple_task, contact_manager, support_tickets, ops_dashboard, fieldtest_hub)
- At least 3 of the 5 apps produce `len(outcome.proposals) >= 1`
- At least one persona-cycle across the full sweep demonstrates the bail-nudge firing AND a state-changing action subsequently occurring (proof that the nudge isn't inert)

**Not in scope this cycle:**

- Proposal *quality* / curation (D3+)
- EDGE_CASES strategy verification (D3)
- `fixtures/` coverage (D4)
- Cross-cycle dedup (deferred to backlog-ingestion layer)
- Richer cognition fields beyond `console_errors_during_action` (deferred; field layout designed to accept them additively later)

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    run_explore_strategy                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  pick_explore_personas(app_spec, override=None)            │  │
│  │   ├─ override is None → auto-pick business personas        │  │
│  │   └─ override is list → lookup + passthrough               │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  pick_start_path(persona_spec, app_spec)                   │  │
│  │   └─ delegates to compute_persona_default_routes           │  │
│  └────────────────────────────────────────────────────────────┘  │
│  for each picked persona: DazzleAgent(use_tool_calls=True)       │
│  after all runs: dedup proposals by (example_app, component)     │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                       DazzleAgent                                │
│  observe → decide → execute → record                             │
│                                                                  │
│  _build_messages:                                                │
│   - history lines render state_changed + URL transitions +       │
│     console_errors                                               │
│   - bail-nudge appended when last 3 steps all state_changed=False│
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    PlaywrightExecutor                            │
│  __init__: attach page.on("console") listener                    │
│  execute(action):                                                │
│    before = (page.url, dom_hash, console_buffer_len)             │
│    <perform action>                                              │
│    after  = (page.url, dom_hash, console_buffer_len)             │
│    return ActionResult(..., from_url, to_url, state_changed,     │
│                        console_errors_during_action)             │
└──────────────────────────────────────────────────────────────────┘
```

Four separable changes across four code boundaries. Each ships as its own commit. None change the public API of any module outside its own file.

## Components

### 1. `ActionResult` shape extension

**File:** `src/dazzle/agent/models.py`

Add four optional fields, all defaulting to `None` or empty list:

```python
@dataclass
class ActionResult:
    message: str
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    # Cycle 197 — L1 action feedback
    from_url: str | None = None      # Page URL before the action
    to_url: str | None = None        # Page URL after the action
    state_changed: bool | None = None  # True if URL or DOM hash changed
    # Cycle 197 — cognition foothold
    console_errors_during_action: list[str] = field(default_factory=list)
```

Rationale:

- **Additive and backward-compatible.** Every existing `ActionResult(...)` construction continues to work unchanged. `HttpExecutor`, `_execute_tool`, fitness engine, test helpers — none of them need to change.
- **`state_changed: bool | None`** — `None` means "undefined" (tool actions, HTTP path, anonymous paths), `False` means "action happened but state didn't change" (the loop-breaker signal), `True` means "something moved". This three-state distinction matters for prompt rendering.
- **`from_url` and `to_url`** are kept alongside `state_changed` because they let the history line say "still at /app" or "navigated /a → /b", which is a more informative signal than a naked boolean.
- **`console_errors_during_action`** is the cognition foothold. It's one of several action-linked signals worth capturing (others listed under "Future cognition fields" below); it ships first because it's cheapest to capture and most likely to fire during explore.

Per-action-type population table for `PlaywrightExecutor`:

| Action | `from_url` | `to_url` | `state_changed` | Notes |
|---|---|---|---|---|
| click | captured | captured | hash-compared | Primary case. |
| type | captured | captured | hash-compared | Validation/autocomplete often changes DOM. |
| navigate | captured | captured | usually True | Same-URL navigate is suspicious but valid. |
| select | captured | captured | hash-compared | Same as type. |
| scroll | captured | captured | **True** (optimistic) | Skip hash; scroll is cheap and usually productive. |
| wait | captured | captured | hash-compared | Async loads produce new content legitimately. |
| assert | captured | captured | **False** (optimistic) | Asserts never change state by definition. |
| done | — | — | `None` | Terminal. |
| tool | — | — | `None` | Tool actions don't touch the page. |

**DOM hash algorithm:**
```python
def _dom_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
```

### 2. `PlaywrightExecutor` enrichment

**File:** `src/dazzle/agent/executor.py`

Two additions:

1. **Console listener attached in `__init__`:**

```python
def __init__(self, page):
    self._page = page
    self._console_errors_buffer: list[str] = []
    page.on("console", self._on_console)

def _on_console(self, msg):
    if msg.type == "error":
        self._console_errors_buffer.append(msg.text)
```

2. **State capture around every action in `execute`:**

```python
async def execute(self, action: AgentAction) -> ActionResult:
    # State capture fields - populated for page actions, None for tool/done
    capture_state = action.type not in (ActionType.TOOL, ActionType.DONE)
    from_url = self._page.url if capture_state else None
    from_hash = _dom_hash(await self._page.content()) if capture_state else None
    console_before = len(self._console_errors_buffer)
    try:
        # ... existing action dispatch unchanged ...
        base_result = ActionResult(message=f"...")
    except Exception as e:
        return ActionResult(
            error=str(e),
            from_url=from_url,
            to_url=self._page.url if capture_state else None,
            state_changed=None,  # exception path — state undefined
            console_errors_during_action=list(
                self._console_errors_buffer[console_before:]
            ),
        )
    # Populate new fields on the result
    if capture_state:
        to_url = self._page.url
        to_hash = _dom_hash(await self._page.content())
        base_result.from_url = from_url
        base_result.to_url = to_url
        if action.type == ActionType.SCROLL:
            base_result.state_changed = True  # optimistic
        elif action.type == ActionType.ASSERT:
            base_result.state_changed = False  # optimistic
        else:
            base_result.state_changed = (from_url != to_url) or (from_hash != to_hash)
    base_result.console_errors_during_action = list(
        self._console_errors_buffer[console_before:]
    )
    return base_result
```

**Blast radius:** `PlaywrightExecutor` is used by fitness_strategy AND explore_strategy. Fitness engine doesn't inspect the new fields, so its behaviour is unchanged. `test_fitness_strategy_integration.py`'s 23 tests must still pass after this change.

### 3. `DazzleAgent` history rendering + bail-nudge

**File:** `src/dazzle/agent/core.py`

Two additions to `_build_messages`:

**3a. History line augmentation** — read the new `ActionResult` fields and render them in the compressed history block. Pseudocode:

```python
def _format_history_line(step: Step) -> str:
    s = f"{step.step_number}. {step.action.type.value}"
    if step.action.target:
        s += f": {step.action.target[:40]}"
    r = step.result
    if r.error:
        s += f" (ERROR: {r.error[:60]})"
    elif r.state_changed is False:
        loc = f"still at {r.to_url}" if r.to_url else "no state change"
        s += f" -> NO state change ({loc})"
    elif r.state_changed is True and r.from_url and r.to_url and r.from_url != r.to_url:
        s += f" -> navigated {r.from_url} → {r.to_url}"
    elif r.state_changed is True:
        s += " -> state changed"
    elif r.message:
        # state_changed is None — legacy path for tool/HTTP/anonymous
        s += f" -> {r.message[:60]}"
    if r.console_errors_during_action:
        n = len(r.console_errors_during_action)
        first = r.console_errors_during_action[0][:60]
        suffix = "s" if n > 1 else ""
        s += f" [+{n} console error{suffix}: {first}]"
    return s
```

Design choices:

- **"NO state change" is capitalised and explicit** — LLMs respond to emphasis in prompts; the loop-breaker signal needs to be unmissable.
- **URL transitions are shown when state changed** — "navigated /app → /app/contacts/1" is a concrete signal that the action accomplished something, far more informative than "Clicked X".
- **Console errors appended inline** — lets the LLM see "clicked, navigated, and by the way there's a TypeError on this page" as one coherent event rather than scraping ambient `PageState` for a linkage that may or may not exist.

**3b. Bail-nudge** — check whether the last 3 history steps all have `state_changed is False`, and if so append a nudge block to the history text:

```python
def _is_stuck(history: list[Step], window: int = 3) -> bool:
    if len(history) < window:
        return False
    recent = history[-window:]
    return all(s.result.state_changed is False for s in recent)

# In _build_messages, after rendering history_text:
if _is_stuck(self._history, window=3):
    history_text += (
        "\n## ⚠️ You appear to be stuck\n"
        "Your last 3 actions produced NO state change. The page hasn't "
        "moved and the selectors aren't firing anything useful. STOP "
        "repeating the same action. Try one of:\n"
        "- navigate to a different URL\n"
        "- click a different kind of element (button, link in a "
        "different section)\n"
        "- if you cannot find any new way to make progress, call the "
        "`done` tool so we can stop wasting steps\n"
    )
```

Design choices:

- **Window=3, not window=8.** The stagnation-completion criterion uses 8 and that's the "give up" threshold. The bail-nudge is a "try harder" signal and fires earlier — long enough that 3 no-ops isn't a fluke, short enough to intervene before the LLM has committed fully to the dead path.
- **Fires continuously once triggered.** If the LLM ignores the nudge once, it sees it again immediately. Cost is a few extra prompt lines; benefit is that it's harder to tune out.
- **Explicit escape to `done`.** A stuck LLM might keep trying out of misguided persistence; giving it an out means the cycle can bail cleanly instead of burning to the max-steps limit.
- **Experimental.** Success criterion for the nudge in the verification run: it fires on at least one persona-cycle AND that cycle produces at least one state-changing action after the nudge. If the nudge fires but never changes behaviour, it's inert and cycle 198 investigates stronger interventions (structural forced-action, different wording, shorter window).

### 4. `explore_strategy` persona picker + fan-out + dedup

**File:** `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py`

**4a. `pick_explore_personas`:**

```python
def pick_explore_personas(
    app_spec: AppSpec,
    override: list[str] | None = None,
) -> list[PersonaSpec]:
    """Pick persona(s) for an explore run.

    Auto-pick (override is None): return ALL personas whose default_workspace
    is not framework-scoped (doesn't start with underscore), sorted
    alphabetically by id for determinism.

    Override (list of ids): return those personas in caller order. Raises
    ValueError if any id is unknown.

    Returns [] if no business personas exist (pathological DSL); caller
    falls back to anonymous.
    """
```

**Filter rule:** a persona is "framework-scoped" iff
`persona.default_workspace is not None and persona.default_workspace.startswith("_")`.

The `_platform_admin` convention is consistent across all 5 `examples/` apps. Framework-scoped workspaces land on Dazzle's built-in admin UI, not the business app — wrong target for MISSING_CONTRACTS exploration.

Verified mapping at spec-write time:

| Example | Business personas (auto-picked) | Framework-scoped (excluded) |
|---|---|---|
| simple_task | admin, manager, user | — |
| contact_manager | user | admin (`_platform_admin`) |
| support_tickets | agent, customer, manager | admin (`_platform_admin`) |
| ops_dashboard | ops_engineer | admin (`_platform_admin`) |
| fieldtest_hub | engineer, manager, tester | admin (`_platform_admin`) |

Totals: **11 persona-cycles** per full sweep vs 5 under a "pick one" rule. Every example has at least one business persona.

**Sort is alphabetical by id**, for determinism. If a specific example keeps picking a bad persona we'll see that in verification and refine in cycle 198; alphabetical is a placeholder signal that's good enough for D2.

**Caller modes for `run_explore_strategy`:**

| Caller passes | Meaning | Use case |
|---|---|---|
| `personas=None` | Auto-pick business personas | D2 default |
| `personas=[]` | Anonymous, no login | Public / auth surface exploration |
| `personas=["admin"]` | Explicit override, single persona | Deliberate platform-persona run |
| `personas=["customer", "admin"]` | Explicit multi-persona | RBAC probing, adversarial runs, D3 edge-case hooks |

The mode-switch on a single parameter is deliberate: all four modes are reachable without adding parameter flags. Anonymous becomes an explicit escape hatch rather than a silent default.

**4b. `pick_start_path`:**

```python
def pick_start_path(persona_spec: PersonaSpec, app_spec: AppSpec) -> str:
    """Compute the start URL path for exploring as persona_spec.

    Delegates to dazzle_ui.converters.workspace_converter.
    compute_persona_default_routes, falling back to '/app' if the
    helper returns no route (pathological DSL with no workspaces).
    """
```

Thin wrapper around the existing 5-step resolution chain in `compute_persona_default_routes` (`src/dazzle_ui/converters/workspace_converter.py:467`). No logic duplication — the FastAPI login flow and the persona switcher already converge on this helper, so explore uses it too.

**Cross-package import note:** `explore_strategy` lives under `src/dazzle/cli/` and imports from `src/dazzle_ui/converters/`. `fitness_strategy.py` already imports from `dazzle_back.runtime.pg_backend` so cross-package imports from `cli/runtime_impl/` are an established pattern, not a new layering violation.

**4c. Fan-out and dedup in `run_explore_strategy`:**

Signature evolution (additive):

```python
async def run_explore_strategy(
    connection: AppConnection,
    *,
    example_root: Path,
    strategy: Strategy,
    personas: list[str] | None = None,  # None = auto-pick business personas
    start_path: str | None = None,       # None = auto-pick per persona
) -> ExploreOutcome:
```

**Behaviour change:** `personas=None` now means auto-pick instead of anonymous. Old anonymous path is still reachable via `personas=[]`. One existing non-test caller (`/tmp/ux_cycle_196_real.py`) will be deleted after cycle 197 since it's replaced by the formal verification test.

**Proposal dedup rule:** key on `(example_app, component_name.lower())`. Keep the first-seen proposal's description; add a `contributing_personas: list[str]` field listing every persona who proposed it. First-seen ordering is deterministic because `pick_explore_personas` sorts alphabetically.

**`ExploreOutcome` shape update:**

```python
@dataclass
class ExploreOutcome:
    strategy: str
    summary: str
    degraded: bool
    proposals: list[dict[str, Any]] = field(default_factory=list)  # deduped
    findings: list[dict[str, Any]] = field(default_factory=list)   # deduped
    blocked_personas: list[tuple[str | None, str]] = field(default_factory=list)
    steps_run: int = 0
    tokens_used: int = 0
    # Cycle 197 addition
    raw_proposals_by_persona: dict[str, int] = field(default_factory=dict)
```

**Logging:** one log line per cycle explaining picks and stats:

```
[explore] contact_manager: auto-picked 1 persona: user
[explore] support_tickets: auto-picked 3 personas: agent, customer, manager
[explore] cycle complete: 11 persona-runs across 5 apps, 17 raw proposals,
          9 unique after dedup, steps=94 tokens=293k
```

Makes debugging trivial when a specific persona gets stuck or a specific example produces surprises.

## Testing

Five test files, four layers of coverage. All unit tests run in CI; the e2e verification test is local-only (`@pytest.mark.e2e`).

### Unit tests

| File | New/Modified | Tests | Approx lines |
|---|---|---|---|
| `tests/unit/test_action_result.py` | new | 3 — default construction, explicit values, backward compat | ~30 |
| `tests/unit/test_playwright_executor_enrichment.py` | new | 11 — URL capture, DOM-hash compare, console buffer diff, per-action-type population, error path preservation | ~250 |
| `tests/unit/test_agent_history_rendering.py` | new | 8 — history line variants, bail-nudge trigger conditions, bail-nudge wording | ~150 |
| `tests/unit/test_explore_strategy.py` | modified | +11 — persona picker filter, sort, override, unknown-id raise, fan-out, dedup | +250 |

**Total unit coverage: 33 new tests, ~680 lines.**

Existing test files MUST still pass unchanged:

- `tests/unit/test_agent_tool_use.py` (23 tests) — tool-use path, unaffected
- `tests/unit/fitness/test_fitness_strategy_integration.py` (23 tests) — fitness strategy, unaffected by ActionResult additions
- `tests/integration/test_agent_investigator_tool_use.py` (2 tests) — investigator, unaffected

### E2E verification test

**File:** `tests/e2e/test_explore_strategy_e2e.py` (new)
**Marker:** `@pytest.mark.e2e` — excluded from default pytest runs
**Invocation:** `pytest tests/e2e/test_explore_strategy_e2e.py -m e2e` (manual, local only)

One parametrised test over the 5 examples. For each:

1. `ModeRunner(mode_spec=get_mode("a"), project_root=<example>, personas=<all_business>, db_policy="preserve")`
2. `run_explore_strategy(conn, example_root=<example>, strategy=Strategy.MISSING_CONTRACTS, personas=None)`
3. Assert `outcome.degraded is False`
4. Record outcome to a structured artefact under `dev_docs/cycle_197_verification/<example>.json`
5. Assert `len(outcome.proposals) >= 1` for at least 3 of the 5 examples (not all 5 — some may be fully contracted)

**Bail-nudge assertion** (separate, over the full sweep): grep the aggregated transcripts for "You appear to be stuck" AND verify at least one such cycle subsequently contains at least one `state_changed is True` action. If this assertion fails, the nudge is either not firing or inert — which is itself a useful signal for cycle 198.

**Environment requirements (local):**

- PostgreSQL reachable (`DATABASE_URL` per-example `.env`)
- Redis reachable (`REDIS_URL` per-example `.env`)
- `ANTHROPIC_API_KEY` in environment

Not wired into CI. Promoted to CI only if/when CI gains DB + Redis + API-key infrastructure.

## Implementation order

Each step ships as its own commit. Five commits for implementation, one for version bump + changelog at the end.

1. **ActionResult shape extension** — 4 new optional fields + unit tests. Pure additive; no other behaviour change.
2. **PlaywrightExecutor enrichment** — state capture, console listener, per-action-type population + unit tests. Existing fitness tests unchanged.
3. **DazzleAgent `_build_messages` history + bail-nudge** — render new fields, trigger nudge + unit tests.
4. **explore_strategy persona picker + fan-out + dedup** — new helpers, signature change, `ExploreOutcome` additions + unit tests.
5. **E2E verification test** — parametrised `tests/e2e/test_explore_strategy_e2e.py`, manual run.
6. **Verification run + log entry + bump + push** — run step 5 against local env, capture the resulting JSON artefacts to `dev_docs/cycle_197_verification/` (local-only — `dev_docs/` is gitignored generally; these artefacts should NOT be force-added unlike `ux-log.md` / `ux-backlog.md`), write cycle 197 log entry, `/bump patch`, ship. One commit containing: log entry, bump, and any CHANGELOG/runbook edits. Verification artefacts themselves stay untracked.

## D3 extension hooks

Cycle 197 ships D2. The following hooks exist so D3 (EDGE_CASES strategy producing findings) can layer on without refactoring:

- **`ActionResult.console_errors_during_action`** — already populated; EDGE_CASES consumes immediately via `record_edge_case`.
- **`pick_explore_personas`** signature leaves room for a `mode=` kwarg or a sibling `pick_edge_case_personas` helper that doesn't filter platform personas.
- **`ExploreOutcome.findings`** — already exists from cycle 193, populated by the `record_edge_case` tool handler. No new shape needed.
- **Bail-nudge fires strategy-agnostically** — EDGE_CASES benefits automatically since the nudge lives in `DazzleAgent._build_messages`.
- **Future cognition fields on `ActionResult`** — `http_status_observed`, `network_errors_during_action`, `selector_match_count`. All pure additive changes with safe defaults. Cycle 198+ can add them one at a time as specific needs emerge.

## Known open questions (explicitly deferred)

- **Proposal ranking across cycles.** Cross-cycle dedup is the backlog ingestion layer's concern, not the strategy's.
- **Accessibility-tree hash vs content hash.** If content hash produces too many false positives (CSS animations, time displays), swap to an accessibility-tree hash. Not switching preemptively — verification run decides.
- **Bail-nudge calibration.** Window=3, continuous-fire, explicit-done escape. All tunable from verification data.
- **Whether `run_explore_strategy` auto-writes PROP-NNN rows.** Not in this cycle. Strategy stays pure; backlog writing is the caller's responsibility.

## Glossary

- **D2** — the delivery scope this spec targets: non-empty MISSING_CONTRACTS runs across all 5 `examples/` apps.
- **D3** — follow-up scope: EDGE_CASES also producing findings. Not this cycle.
- **L1 action feedback** — state-change and URL signals captured at the executor layer (the only layer with ground truth about action→consequence).
- **Bail-nudge** — prompt-level intervention that fires when the LLM has produced 3 consecutive no-op actions, instructing it to try something different or call `done`.
- **Cognition foothold** — the first action-linked signal beyond pure loop-breaking (`console_errors_during_action`). Establishes the `ActionResult` pattern for future cognition fields without committing to the full set up-front.
