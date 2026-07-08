# State-Gated Affordance (3c → L4) Design

**Issue:** #1558 (criterion 3c). **Date:** 2026-07-08.

**Goal:** Take UX-maturity criterion **3c (state-gated affordance)** from L3 to L4
by showing only the state-machine transitions **valid from a record's current
state** — on the **detail (VIEW) surface** (the documented gap) and on **regular
list rows** (which surface no transitions today).

**One-line:** The state graph is the single source of truth for which affordances
appear; no affordance may contradict the record's current state.
`negative_space` — don't show what can't be done.

---

## Background — current state (L3)

An entity declares a `state:` machine with `transitions:` (e.g.
`open -> in_progress`, `in_progress -> resolved`, `* -> open`). `StateMachineSpec`
provides the correct gate — `get_transitions_from(state)` returns transitions
whose `from_state ∈ {state, "*"}`.

**What gates correctly today:** the **queue** region
(`render/fragment/renderer/_render_tables.py:881`) filters per-row transitions,
and **kanban** gates by drag target.

**The gaps (this work):**

1. **Detail (VIEW) surface — shows ALL transitions regardless of state.** The
   compile-time build in `page/converters/template_compiler.py:1134-1147` iterates
   the whole state machine, **dedups by `to_state`**, and builds
   `TransitionContext(to_state, label, api_url)` — **dropping `from_state`**. So
   the detail view forwards every reachable target state; a `resolved` ticket
   still shows an `in_progress` button. Because `from_state` is discarded at
   compile time, nothing downstream *can* gate.
2. **Regular list rows — no transitions at all.** Only `QueueRegion` /
   kanban carry per-row transitions; a plain `mode: list` surface of a
   state-machine entity offers no state affordances.

The `_probe_3c` is trivial (`hasattr(state_machine, "StateMachineSpec")`).

---

## Architecture

Five pieces. The keystone is **preserving `from_state`** through the compile-time
build so any consumer can gate; then one shared gating helper feeds both the
detail filter and the list-row render.

### Component 1 — preserve `from_state` (the keystone)

- **`render/context.py:244` `TransitionContext`** gains `from_state: str = ""`.
- **`template_compiler.py:1134`** build: populate `from_state=t.from_state` and
  **dedup by `(from_state, to_state)`** instead of `to_state` alone (two
  transitions to the same target from different sources are distinct affordances).
  The compile-time list now carries every declared transition with its source.

This is compile-time (per-surface, not per-record), so it cannot filter by the
record's state — it only *preserves the data* the request-time filter needs.

### Component 2 — the shared gating helper

A pure render-layer helper (new, e.g. `render/fragment/state_affordance.py`):

```python
def gated_row_transitions(
    transitions: list[TransitionContext], current_state: str
) -> list[TransitionContext]:
    """Transitions valid FROM current_state — from_state == current_state or '*'
    (mirrors StateMachineSpec.get_transitions_from). Empty current_state → []."""
```

One rule, shared by detail + list rows (and available for a later queue
convergence). Uses the same `from_state ∈ {state, "*"}` semantics as
`get_transitions_from`.

### Component 3 — detail view: request-time filter

At request time the record (hence its `status_field` value = current state) is
known. `page_routes.py` already holds `req_detail` (with `.transitions` and
`.status_field`) and the fetched record. Before the flatten at
`page_routes.py:~1868`, filter:

```python
current = str(record.get(req_detail.status_field, "") or "")
req_detail.transitions = gated_row_transitions(req_detail.transitions, current)
```

The existing flatten + `fragment_adapter._build_detail_actions` then render only
the gated set. A `resolved` record shows only `* -> open` (reopen); an `open`
record shows only `open -> in_progress`.

### Component 4 — regular list rows: state-gated affordances

Mirror the queue mechanism on the converged list-render path:

- Thread onto the `DataTable` primitive (`render/fragment/primitives/data.py`)
  three list-level fields: `state_transitions: tuple[TransitionContext, ...]`
  (with `from_state`), `status_field: str`, `transition_endpoint: str` — analogous
  to `QueueRegion`'s `transitions`/`queue_status_field`/`queue_api_endpoint`.
- In the row renderer (`render/fragment/renderer/_data_row.py`), when
  `state_transitions` is present, compute the row's `current_state =
  item[status_field]`, call `gated_row_transitions`, and render the valid
  transitions as buttons in the **existing `actions_cell`** seam — `hx-put` to
  `transition_endpoint/{row_id}` with `hx-vals '{"<status_field>":"<to_state>"}'`,
  wrapped so the click `stopPropagation()`s (does not trigger row drill). Byte-
  identical when the entity has no state machine (`state_transitions` empty →
  nothing added).
- The list build (the surface→DataTable converter) populates these fields from
  `entity.state_machine` when present — same source as the detail build.

### Component 5 — the maturity probe (the L4 gate)

`_probe_3c` becomes real: synthesize a `StateMachineSpec` + `TransitionContext`
list and assert, via `gated_row_transitions`, that (a) an `open` record offers
`open -> in_progress` but not `in_progress -> resolved`; (b) a `resolved` record
offers the `* -> open` wildcard reopen; (c) an empty/unknown state yields no
affordances. Bump the `"3c"` criterion `declared` 3 → 4 and update its evidence.

---

## Data flow

```
compile time (template_compiler): entity.state_machine.transitions
  -> TransitionContext(from_state, to_state, label, api_url)   [dedup (from,to)]
  -> DetailContext.transitions            (detail)
  -> DataTable.state_transitions          (list)

request time — DETAIL (page_routes):
  record[status_field] = current  ->  gated_row_transitions(...)  ->  flatten -> render

render time — LIST ROW (_data_row):
  item[status_field] = current  ->  gated_row_transitions(...)  ->  actions_cell buttons
```

## Scope guardrails (YAGNI)

- **Guards enforced on click, not at render** (per the scope decision): a
  transition whose `guards` (field/role/expr) fail still renders but HTTP
  validation 422s it. Render-time guard evaluation is out of scope.
- **Queue left untouched** — it already gates (via its own `to_state !=
  current_status` heuristic). A later convergence onto `gated_row_transitions`
  (which also upgrades the queue to the stricter `from_state` gate) is noted as a
  follow-up, not done here, to avoid risking a working surface.
- **No new DSL** — pure render inference from the existing `state:`/`transitions:`.
- **Cold-start / no-state-machine = byte-identical** — every branch is gated on
  the entity having a state machine.

## Error handling

Pure functions; `gated_row_transitions` never raises (empty state → `[]`). A
record missing the status field → `current = ""` → no affordances (safe). No new
runtime failure modes.

## Testing

- **Unit — `gated_row_transitions`:** from_state match; wildcard `*`; excludes
  invalid; empty current_state → `[]`; dedup `(from,to)` preserved.
- **Unit — compile build:** `TransitionContext.from_state` populated; two
  transitions to the same target from different sources both survive.
- **Unit — detail filter:** a record in state X yields only X-valid transitions
  (synthetic `DetailContext` + record).
- **Unit — list row:** a `DataTable` with `state_transitions` renders gated
  buttons per row's current state in the actions cell; no state machine → no
  buttons (byte-identical).
- **Probe:** `_probe_3c` green at L4; `ux_maturity` index ticks (12/13 → 13/13).
- **Integration/e2e (light):** the existing detail/list render tests still pass;
  the list-render path change is the higher-risk piece → adversarial review
  before ship (per the 2a Task-2 precedent).

## Model-Driven Failure Modes note

Adds *inference* (transitions appear/disappear by state). Mitigations: the state
graph is author-declared and is the single source of truth; the same
`get_transitions_from` semantics gate render AND HTTP validation (no divergence);
a competent engineer traces any affordance to a declared `transitions:` edge.
Detector is **live in the normal workflow** — every detail view and list of a
state-machine entity exercises it (unlike a rarely-authored signal).
