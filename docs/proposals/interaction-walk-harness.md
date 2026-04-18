# INTERACTION_WALK Harness — Design Proposal

**Status**: draft, awaiting review
**Source issue**: [#800](https://github.com/manwithacat/dazzle/issues/800)
**Originating observation**: AegisMark's #797/#798/#799 all shipped after passing every static gate
**Author**: autonomous improvement loop (cycle 68, 2026-04-18)

## Problem

The shape-nesting (INV-1), duplicate-title (INV-2), hidden-primary-action
(INV-9), and composite-fetch gates all test the *rendered output*. They
don't exercise *interactions*: the DOM AegisMark's three bugs rendered
was fine on paper. The bugs only manifest under a real gesture — a
drag, a click on "Add Card", a keyboard Tab sequence. That class of
regression is the next blind spot.

## Proposal (from #800)

Add `dazzle ux verify --interactions`: a Playwright-mode harness that
runs scripted gestures against live example workspaces and asserts
state diffs.

Three canonical v1 interactions:

| Interaction | Gate | Catches |
|---|---|---|
| `card_drag` | pointerdown + move ≥200px + pointerup → bbox delta > 5px | #797 |
| `card_add` | click "Add Card" → pick entry → body text > threshold AND region XHR fired | #798 |
| `card_remove_reachable` | Tab to the remove button → opacity > 0 | #799 |

## Design questions + proposed answers

### 1. Server fixture

**Question**: Does the harness spin up `dazzle serve --local` per run,
or assume a server is already running?

**Proposal**: Session-scoped pytest fixture that spins up the example
app in a subprocess, waits for the health endpoint, yields the base URL,
tears down at session end. Reuse the already-working pattern from
`tests/e2e/conftest.py` if one exists there. Cold-start cost is ~15–20s
once per pytest session (not per test), amortised across N walks.

Implementation sketch:

```python
# src/dazzle/testing/ux/fixtures.py
@pytest.fixture(scope="session")
def interaction_server() -> Iterator[str]:
    """Start a local dazzle serve against examples/support_tickets,
    yield its base URL, tear down at session end.
    """
    proc = subprocess.Popen(
        ["python", "-m", "dazzle", "serve", "--local", "--port", "0"],
        cwd=REPO_ROOT / "examples" / "support_tickets",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    # Parse "Listening on http://..." from stderr, return URL
    url = _wait_for_health(proc)
    try:
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=5)
```

Alternative rejected: class-scoped fixture. Too expensive — every
`Test<thing>` class would restart the server. Session scope strikes
the right balance.

### 2. Interaction abstraction

**Question**: How do we shape interactions so v1's three aren't
load-bearing forever? New walks (resize, slide-over, keyboard-nav)
should drop in without touching the core.

**Proposal**: A `Protocol` with a single `execute(page) -> Result`
method. Each walk is a dataclass that holds its own inputs (card_id,
region_name, etc.) and returns a typed `Result`. Composition is just a
list of walks executed in sequence.

```python
# src/dazzle/testing/ux/interactions/base.py
class Interaction(Protocol):
    name: str
    def execute(self, page: Page) -> InteractionResult: ...

@dataclass
class InteractionResult:
    name: str
    passed: bool
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
```

v1 walks go in `src/dazzle/testing/ux/interactions/`:
- `card_drag.py` → `CardDragInteraction`
- `card_add.py` → `CardAddInteraction`
- `card_remove_reachable.py` → `CardRemoveReachableInteraction`

A `Walk` is just `list[Interaction]`. No registry, no magic — new
walks land as new files.

### 3. Selector stability

**Question**: `page.get_by_text('Add Card')` breaks if we rename the
button. How do we keep selectors durable?

**Proposal**: Add `data-test-id` attributes to the workspace template's
key affordances — `<button data-test-id="dz-add-card-trigger">`,
`<button data-test-id="dz-remove-card" aria-label="Remove card">`, the
drag handle on each card, etc. The harness targets these. User-facing
labels stay flexible; test selectors are an ABI.

Cost: ~5 new `data-test-id` attributes on `workspace/_content.html`.
Benefit: the harness is decoupled from copy changes forever.

This couples the proposal to a template edit, but it's a small one.

### 4. Flakiness policy

**Question**: Playwright over HTMX is flaky. What's the policy?

**Proposal**: **Non-blocking in CI for the first N weeks.** Run the
walks as a separate job that posts results but doesn't fail the build.
After 2–3 weeks of signal, ratchet to blocking. This matches the
Playwright community's conventional approach and gives us data to
calibrate before locking in.

Concrete implementation:
- New workflow job `interaction-walks` in `.github/workflows/ci.yml`
- `continue-on-error: true` for the first ratchet window
- Retries: `pytest-rerunfailures` with `--reruns 2` per walk
- After the ratchet window: flip `continue-on-error` off

### 5. Fixture app

**Question**: Which example app does the harness target?

**Proposal**: `examples/support_tickets` — it has the richest workspace
(`ticket_queue` + `agent_dashboard`), a variety of region types (kanban,
bar_chart, funnel, metrics), and stable persona config (`agent`,
`manager`). `ops_dashboard` is a close second and we can extend the
walks to it later. `simple_task` / `contact_manager` are too minimal
to cover drag/add/remove meaningfully.

Persona for the session: `agent`. All three v1 walks work from the
agent's default workspace.

### 6. CLI integration

**Question**: Peer of `--browser`? Separate command?

**Proposal**: **Peer flag**. `dazzle ux verify --interactions` runs
the walks; `--browser` is unchanged. Default `dazzle ux verify` stays
contracts-only (cheap + fast). Adding a new flag rather than a new
subcommand keeps the mental model consistent with how contracts and
browser mode already compose.

Exit codes:
- 0: all walks passed
- 1: one or more walks failed (regression)
- 2: server/fixture setup failed (distinguish from real failures)

## Implementation plan

| Step | Cost | Deliverable |
|---|---|---|
| 1. Add `data-test-id` attrs | 1 cycle | Template edits + composite snapshot updates |
| 2. Build `Interaction` protocol + `InteractionResult` | 1 cycle | `src/dazzle/testing/ux/interactions/base.py` + unit tests |
| 3. Session-scoped server fixture | 1 cycle | `src/dazzle/testing/ux/fixtures.py::interaction_server` |
| 4. Implement v1 walks | 2 cycles | One file per walk + 1 pytest per walk |
| 5. CLI wiring | 1 cycle | `--interactions` flag in `src/dazzle/cli/ux.py` |
| 6. CI job (non-blocking) | 0.5 cycle | `.github/workflows/ci.yml` edit |
| 7. Ratchet to blocking | 0.5 cycle (after N weeks) | Flip `continue-on-error: false` |

Total: ~7 cycles to v1. Each step is committable on its own.

## Risks + open questions

1. **Subprocess server on CI**: GitHub Actions runners have Docker
   available but pinning port 0 (dynamic) + parsing stderr is the
   fragile path. Alternative: fixed port + `lsof` check. Subprocess
   orchestration is the single biggest source of flake risk here.
2. **Playwright on HTMX**: HTMX navigations sometimes race with
   `page.wait_for_load_state()`. Using `wait_for_selector()` against
   a specific `data-test-id` is more robust.
3. **One app hardcoded**: Proposal is to run against `support_tickets`.
   If that app's UI rearranges, walks break. Mitigation: `data-test-id`
   attributes and the deliberately conservative "which app" decision
   above.
4. **What counts as "passed"?**: `card_drag` asserts `dy > 5px`.
   That's a smoke assertion — the drag moved *something*. A more
   rigorous check would verify the card landed in a new array index
   via the layout JSON. Defer to v2.

## Rejected alternatives

- **Use Playwright trace/video**: too slow, produces artifacts too
  big to store per-run.
- **Pure headless DOM simulation** (jsdom): can't fire real pointer
  events through Alpine + HTMX coordinated bindings.
- **Test every example app**: combinatorial explosion. Walks test the
  *framework template* via one app; if the framework regresses, every
  app regresses.

## What I'd like from the Dazzle team

Agreement (or principled disagreement) on the 6 design answers above.
If all 6 land, the implementation plan executes in sequence over the
next ~7 cycles. If any is wrong, the rework cost is bounded to its
step.

This proposal lives in `docs/proposals/` — not auto-ingested. A
follow-up PR will accept/reject it and either move forward with the
plan or file revisions.
