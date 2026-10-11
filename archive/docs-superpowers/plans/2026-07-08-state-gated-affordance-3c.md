# State-Gated Affordance (3c → L4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show only the state-machine transitions valid from a record's current state — on the detail (VIEW) surface and on regular list rows.

**Architecture:** Preserve `from_state` through the compile-time transition build (the keystone), add one shared `gated_row_transitions` helper, then consume it in a request-time detail filter and a list-row actions-cell render. Guards stay enforced on click; queue untouched; byte-identical when no state machine.

**Tech Stack:** Python 3.12, Pydantic render-context models, pytest.

## Global Constraints

- **Guards enforced on click, not at render** — a guard-failed transition still renders; HTTP validation 422s it.
- **Queue region untouched** — it already gates; convergence onto the shared helper is a noted follow-up, not this work.
- **No new DSL** — pure render inference from the existing `state:`/`transitions:`.
- **Byte-identical when the entity has no state machine** — every branch gates on `entity.state_machine` / non-empty `state_transitions`.
- **Gate semantics:** a transition is valid from `current_state` iff `from_state == current_state or from_state == "*"` (mirrors `StateMachineSpec.get_transitions_from`).
- **venv python:** `/Volumes/SSD/Dazzle/.venv/bin/python`. Tests: `… -m pytest <path> -p no:cacheprovider`.
- **Meta-gates:** any new gate-family test file (`*drift*`, `test_no_*`, `*ratchet*`) needs `pytestmark = pytest.mark.gate`; no `except Exception: pass` in production (`with suppress(...)`); run `pytest -m gate` + `-k "no_bare_except or gate_marker or deferred_imports"` before ship (the v0.96.5 lesson).

Verified seams:
- `render/context.py:244` `TransitionContext(to_state, label, api_url)` — add `from_state`.
- `page/converters/template_compiler.py:1134-1147` — the compile build (dedups by `to_state`, drops `from_state`).
- `page/runtime/... DetailContext` carries `transitions` + `status_field`.
- `http/runtime/page_routes.py:~1357-1377` (`req_detail.transitions`) + `~1868` flatten; the fetched record dict is in scope in the detail render path.
- `render/fragment/primitives/data.py` `DataTable` (~110), `QueueRegion` (~797, the template: `transitions`/`queue_status_field`/`queue_api_endpoint`, gated at `_render_tables.py:881`).
- `http/runtime/handlers/list_handlers.py:66 build_data_table(table_dict, items) -> DataTable`.
- `render/fragment/renderer/_data_row.py:94 assemble_list_row(..., actions_cell="")` + `_render_table_row(table, item)` (~283).
- `core/ir/state_machine.py` `StateMachineSpec.get_transitions_from`, `.status_field`, `StateTransition(from_state, to_state, guards)`.
- Example material: `support_tickets:Ticket` (open/in_progress/resolved/closed), `simple_task:Task`.

---

### Task 1: `TransitionContext.from_state` + preserve it through the build

**Files:**
- Modify: `src/dazzle/render/context.py:244` (`TransitionContext`)
- Modify: `src/dazzle/page/converters/template_compiler.py:1134-1147`
- Test: `tests/unit/test_transition_context_from_state.py`

**Interfaces:**
- Produces: `TransitionContext` gains `from_state: str = ""`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_transition_context_from_state.py
from dazzle.render.context import TransitionContext


def test_transition_context_carries_from_state():
    t = TransitionContext(from_state="open", to_state="in_progress", label="Start", api_url="/x")
    assert t.from_state == "open"


def test_from_state_defaults_empty():
    t = TransitionContext(to_state="done", label="Done")
    assert t.from_state == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_transition_context_from_state.py -q -p no:cacheprovider`
Expected: FAIL — `TransitionContext` has no `from_state` (unexpected kwarg).

- [ ] **Step 3: Add the field**

In `src/dazzle/render/context.py`, `TransitionContext`:

```python
class TransitionContext(BaseModel):
    """Context for a state machine transition button."""

    to_state: str
    label: str
    api_url: str = ""
    from_state: str = ""  # #1558 3c: source state for current-state gating ("*" = any)
```

- [ ] **Step 4: Preserve from_state in the compile build**

In `src/dazzle/page/converters/template_compiler.py`, replace the transition-build loop (~1138-1147) so it keeps `from_state` and dedups by `(from_state, to_state)`:

```python
        seen: set[tuple[str, str]] = set()
        for t in sm.transitions:
            key = (t.from_state, t.to_state)
            if key not in seen:
                seen.add(key)
                transitions.append(
                    TransitionContext(
                        from_state=t.from_state,
                        to_state=t.to_state,
                        label=t.to_state.replace("_", " ").title(),
                        api_url=f"{api_endpoint}/{{id}}",
                    )
                )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_transition_context_from_state.py -q -p no:cacheprovider`
Expected: PASS (2 tests).

- [ ] **Step 6: Lint + type-check**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/render/context.py src/dazzle/page/converters/template_compiler.py tests/unit/test_transition_context_from_state.py --fix && /Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/render/context.py src/dazzle/page/converters/template_compiler.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(state): preserve from_state on TransitionContext through the compile build (#1558 3c)"
```

---

### Task 2: `gated_row_transitions` shared helper

**Files:**
- Create: `src/dazzle/render/fragment/state_affordance.py`
- Test: `tests/unit/test_state_affordance.py`

**Interfaces:**
- Consumes: `TransitionContext` (Task 1).
- Produces: `gated_row_transitions(transitions: list[TransitionContext], current_state: str) -> list[TransitionContext]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_state_affordance.py
from dazzle.render.context import TransitionContext
from dazzle.render.fragment.state_affordance import gated_row_transitions


def _t(frm, to):
    return TransitionContext(from_state=frm, to_state=to, label=to.title(), api_url="/x")


def test_only_transitions_from_current_state():
    ts = [_t("open", "in_progress"), _t("in_progress", "resolved")]
    out = gated_row_transitions(ts, "open")
    assert [t.to_state for t in out] == ["in_progress"]


def test_wildcard_from_any_state():
    ts = [_t("open", "in_progress"), _t("*", "open")]
    out = gated_row_transitions(ts, "resolved")
    assert [t.to_state for t in out] == ["open"]  # only the wildcard reopen


def test_empty_current_state_yields_nothing():
    ts = [_t("open", "in_progress")]
    assert gated_row_transitions(ts, "") == []


def test_unknown_state_yields_only_wildcards():
    ts = [_t("open", "in_progress"), _t("*", "archived")]
    assert [t.to_state for t in gated_row_transitions(ts, "weird")] == ["archived"]
```

- [ ] **Step 2: Run to verify failure**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_state_affordance.py -q -p no:cacheprovider`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# src/dazzle/render/fragment/state_affordance.py
"""#1558 (3c → L4): the single gating rule for state-machine transition
affordances — which transitions are valid from a record's current state.
Shared by the detail-view filter and the list-row render. Pure, no I/O."""

from dazzle.render.context import TransitionContext


def gated_row_transitions(
    transitions: list[TransitionContext], current_state: str
) -> list[TransitionContext]:
    """Transitions valid FROM ``current_state`` — ``from_state == current_state``
    or the ``"*"`` wildcard (mirrors ``StateMachineSpec.get_transitions_from``).
    An empty ``current_state`` yields no affordances."""
    if not current_state:
        return []
    return [t for t in transitions if t.from_state == current_state or t.from_state == "*"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_state_affordance.py -q -p no:cacheprovider`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + type-check + commit**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/render/fragment/state_affordance.py tests/unit/test_state_affordance.py --fix && /Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/render/fragment/state_affordance.py`

```bash
git add -A
git commit -m "feat(state): gated_row_transitions shared current-state gating helper (#1558 3c)"
```

---

### Task 3: Detail-view request-time filter

**Files:**
- Modify: `src/dazzle/http/runtime/page_routes.py` (detail render path, near the `req_detail.transitions` handling ~1357-1377 and the flatten ~1868)
- Test: `tests/unit/test_detail_state_gating.py`

**Interfaces:**
- Consumes: `gated_row_transitions` (Task 2); `DetailContext.transitions` (now with `from_state`), `DetailContext.status_field`, the fetched record dict.

- [ ] **Step 1: Read the detail render path**

Run: `sed -n '1340,1380p;1860,1880p' src/dazzle/http/runtime/page_routes.py`
Identify: the variable holding the fetched record dict (the one whose `[status_field]` is the current state) in the same scope as `req_detail`. It is the record returned by the in-process detail read (search upward for the `record`/`item`/`data` dict passed to the detail context).

- [ ] **Step 2: Write the failing test**

Test the filter behaviorally via a small helper. Add a module-level function in `page_routes.py` and unit-test it (keeps the test off the full request stack):

```python
# tests/unit/test_detail_state_gating.py
from dazzle.render.context import TransitionContext
from dazzle.http.runtime.page_routes import gate_detail_transitions


def _t(frm, to):
    return TransitionContext(from_state=frm, to_state=to, label=to, api_url="/x")


def test_detail_transitions_gated_to_current_state():
    ts = [_t("open", "in_progress"), _t("in_progress", "resolved"), _t("*", "open")]
    out = gate_detail_transitions(ts, {"status": "resolved"}, "status")
    assert [t.to_state for t in out] == ["open"]  # only wildcard reopen from resolved


def test_detail_missing_status_field_yields_nothing():
    ts = [_t("open", "in_progress")]
    assert gate_detail_transitions(ts, {}, "status") == []
```

- [ ] **Step 3: Run to verify failure**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_detail_state_gating.py -q -p no:cacheprovider`
Expected: FAIL — `gate_detail_transitions` does not exist.

- [ ] **Step 4: Implement the helper + wire it**

Add to `page_routes.py` (module level, near the other detail helpers):

```python
def gate_detail_transitions(
    transitions: list[TransitionContext], record: dict[str, Any], status_field: str
) -> list[TransitionContext]:
    """#1558 3c: keep only transitions valid from the record's current state."""
    from dazzle.render.fragment.state_affordance import gated_row_transitions

    current = str(record.get(status_field, "") or "")
    return gated_row_transitions(transitions, current)
```

Then, in the detail render path (after the record is fetched and `req_detail`
is built, before the transitions are flattened for the fragment), assign:

```python
req_detail.transitions = gate_detail_transitions(
    req_detail.transitions, <record_dict>, req_detail.status_field
)
```

Use the record-dict variable identified in Step 1. Place this BEFORE the
`for _t in req_detail.transitions:` `{id}` substitution (~1375) so both the
substitution and the ~1868 flatten see the gated list. (Import
`TransitionContext` at the top of page_routes.py if not already present — check
first; if the file's convention is lazy imports for render types, keep the
`gated_row_transitions` import inside the helper as shown and only import
`TransitionContext` under `TYPE_CHECKING` for the annotation.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_detail_state_gating.py -q -p no:cacheprovider`
Expected: PASS (2 tests).

- [ ] **Step 6: Regression — existing detail render tests**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/ -q -p no:cacheprovider -k "detail or transition or page_route"`
Expected: PASS (fix any test that asserted the old all-transitions detail output — a record-less detail render now shows no transitions; update such a test to pass a record with a state, or assert the gated behaviour).

- [ ] **Step 7: Lint + type-check + commit**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/http/runtime/page_routes.py tests/unit/test_detail_state_gating.py --fix && /Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/http/runtime/page_routes.py`

```bash
git add -A
git commit -m "feat(state): gate detail-view transitions by the record's current state (#1558 3c)"
```

---

### Task 4: Regular list rows — state-gated transition affordances (HIGH-RISK)

**Files:**
- Modify: `src/dazzle/render/fragment/primitives/data.py` (`DataTable` — add 3 fields)
- Modify: `src/dazzle/http/runtime/handlers/list_handlers.py` (`build_data_table` — populate them)
- Modify: `src/dazzle/render/fragment/renderer/_data_row.py` (`_render_table_row` / actions_cell — render gated buttons)
- Modify: `src/dazzle/render/fragment/region/_builders_tables.py` (`_build_list` / `ListRegion` build — populate them) IF `ListRegion` rows do not already flow through the same `DataTable`
- Test: `tests/unit/test_list_row_state_affordance.py`

**Interfaces:**
- Consumes: `gated_row_transitions` (Task 2), `TransitionContext` (Task 1).
- Produces: `DataTable` gains `state_transitions: tuple[TransitionContext, ...] = ()`, `status_field: str = ""`, `transition_endpoint: str = ""`.

- [ ] **Step 1: Read the row-render + table-build seams**

Run: `sed -n '283,400p' src/dazzle/render/fragment/renderer/_data_row.py` (the `_render_table_row` body + how `actions_cell` is assembled — the view/edit/delete hover actions).
Run: `sed -n '66,120p' src/dazzle/http/runtime/handlers/list_handlers.py` (`build_data_table`).
Run: `grep -n "class DataTable" -A40 src/dazzle/render/fragment/primitives/data.py`.
Confirm whether `ListRegion` rows render through the same `DataTable`/`_render_table_row` core (per ADR-0048 they should) — if so, populating `DataTable` covers both paths and the `_builders_tables.py` edit is only about sourcing the fields.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_list_row_state_affordance.py
from dazzle.render.context import TransitionContext
from dazzle.render.fragment.renderer._data_row import _render_table_row


def _t(frm, to):
    return TransitionContext(from_state=frm, to_state=to, label=to.title(), api_url="/api/tickets/{id}")


def _table(**over):
    base = {
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "entity_name": "Ticket",
        "state_transitions": [_t("open", "in_progress"), _t("in_progress", "resolved")],
        "status_field": "status",
        "transition_endpoint": "/api/tickets",
    }
    base.update(over)
    return base


def test_row_shows_only_current_state_transitions():
    html = _render_table_row(_table(), {"id": "1", "title": "T", "status": "open"})
    assert "in_progress" in html  # open -> in_progress valid
    assert "resolved" not in html  # in_progress -> resolved NOT valid from open


def test_row_without_state_machine_has_no_transition_buttons():
    html = _render_table_row(
        {"columns": [{"key": "title", "label": "Title", "type": "text"}], "entity_name": "Ticket"},
        {"id": "1", "title": "T"},
    )
    assert "hx-put" not in html  # byte-identical: no state transitions rendered
```

(Adjust the `_table` dict keys in Step 3 to match the ACTUAL keys `_render_table_row` reads, discovered in Step 1 — the test asserts behaviour, not internal key names, so refine the fixture to the real contract.)

- [ ] **Step 3: Run to verify failure**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_list_row_state_affordance.py -q -p no:cacheprovider`
Expected: FAIL — no transition buttons rendered (feature absent).

- [ ] **Step 4: Add the `DataTable` fields**

In `src/dazzle/render/fragment/primitives/data.py`, `DataTable`:

```python
    # #1558 3c: state-gated transition affordances (mirrors QueueRegion).
    state_transitions: tuple[TransitionContext, ...] = ()
    status_field: str = ""
    transition_endpoint: str = ""
```

Import `TransitionContext` in that module if not present.

- [ ] **Step 5: Render gated buttons in the row actions cell**

In `_data_row.py::_render_table_row`, where `actions_cell` is assembled, when the
table carries `state_transitions`, compute the row's current state and append the
gated transition buttons (mirror the queue markup at `_render_tables.py:881-905`,
adapted to the `dz-tr-action` row-action style):

```python
from dazzle.render.fragment.state_affordance import gated_row_transitions

state_transitions = table.get("state_transitions") or ()
status_field = table.get("status_field") or ""
endpoint = table.get("transition_endpoint") or ""
transition_html = ""
if state_transitions and status_field and endpoint:
    current = str(item.get(status_field, "") or "")
    row_id = str(item.get("id", "") or "")
    valid = gated_row_transitions(list(state_transitions), current)
    if valid and row_id:
        buttons = "".join(
            f'<button type="button" class="dz-tr-action" '
            f'hx-put="{_esc_attr(endpoint)}/{_esc_attr(row_id)}" '
            f"hx-vals='{{\"{status_field}\": \"{t.to_state}\"}}' "
            f'onclick="event.stopPropagation()">{_esc(t.label)}</button>'
            for t in valid
        )
        transition_html = buttons
# fold transition_html into the existing actions_cell content
```

Use the module's existing escape helpers (`_esc`/`_esc_attr` or the `ctx.escape*`
equivalent — match what `_render_table_row` already uses). Byte-identical when
`state_transitions` is empty.

- [ ] **Step 6: Populate the fields in `build_data_table`**

In `list_handlers.py::build_data_table`, when the source `table_dict` carries the
entity's state machine (thread it in from the list handler that has the
`entity_spec`), set `state_transitions` (as `TransitionContext` with `from_state`,
from `entity.state_machine.transitions`), `status_field` (`sm.status_field`), and
`transition_endpoint` (the entity's REST collection URL). If `build_data_table`'s
`table_dict` does not currently carry the state machine, thread it from the
caller in `list_handlers.py` (the handler holds the `entity_spec`). Mirror how the
queue's `compute_queue` sources transitions (`workspace_region_computes.py:355`).

- [ ] **Step 7: `ListRegion` path (only if not already covered)**

If Step 1 confirmed `ListRegion` rows flow through the same `DataTable`/
`_render_table_row` core, no change is needed here beyond Step 6's sourcing. If
`ListRegion` has an independent row path, populate the same three fields in
`_builders_tables.py::_build_list` from `entity.state_machine`.

- [ ] **Step 8: Run tests + regression**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_list_row_state_affordance.py -q -p no:cacheprovider`
Expected: PASS.
Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/ -q -p no:cacheprovider -k "data_row or list_row or list_handler or data_table or render_table or queue or workspace_composite or card_safety"`
Expected: PASS (the list-render path is card-safety / composite gated — these must stay green).

- [ ] **Step 9: Lint + type-check + commit**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/render/fragment/primitives/data.py src/dazzle/http/runtime/handlers/list_handlers.py src/dazzle/render/fragment/renderer/_data_row.py tests/unit/test_list_row_state_affordance.py --fix && /Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/render/fragment/primitives/data.py src/dazzle/http/runtime/handlers/list_handlers.py src/dazzle/render/fragment/renderer/_data_row.py`

```bash
git add -A
git commit -m "feat(state): state-gated transition affordances on regular list rows (#1558 3c)"
```

---

### Task 5: `_probe_3c` L4 + criterion bump

**Files:**
- Modify: `src/dazzle/qa/ux_maturity.py` (`_probe_3c`; the `"3c"` `Criterion` — `declared` 3→4, evidence)
- Test: `tests/unit/test_ux_maturity_3c.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ux_maturity_3c.py
from dazzle.qa import ux_maturity as m


def _crit(cid):
    return next(c for c in m.CRITERIA if c.id == cid)


def test_3c_declared_l4():
    c = _crit("3c")
    assert c.declared == 4


def test_3c_probe_passes():
    c = _crit("3c")
    result = c.probe()
    assert result.ok, result.note
```

- [ ] **Step 2: Run to verify failure**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_ux_maturity_3c.py -q -p no:cacheprovider`
Expected: FAIL — `declared == 3`.

- [ ] **Step 3: Rewrite `_probe_3c` + bump the criterion**

Replace the trivial `_probe_3c` (add the `gated_row_transitions` import at MODULE TOP — the qa→render/page import convention, matching the other probes):

```python
def _probe_3c() -> ProbeResult:
    """State-gated affordances: only transitions valid from a record's current
    state are offered (detail view + list rows), via the shared
    gated_row_transitions gate (level 4, #1558)."""
    ts = [
        TransitionContext(from_state="open", to_state="in_progress", label="Start"),
        TransitionContext(from_state="in_progress", to_state="resolved", label="Resolve"),
        TransitionContext(from_state="*", to_state="open", label="Reopen"),
    ]
    from_open = [t.to_state for t in gated_row_transitions(ts, "open")]
    from_resolved = [t.to_state for t in gated_row_transitions(ts, "resolved")]
    open_ok = from_open == ["in_progress"]  # not resolved (not valid from open)
    resolved_reopen = from_resolved == ["open"]  # only the wildcard reopen
    empty_ok = gated_row_transitions(ts, "") == []
    ok = open_ok and resolved_reopen and empty_ok
    return ProbeResult(
        ok=ok,
        note=f"from_open={from_open} from_resolved={from_resolved} empty_gated={empty_ok}",
    )
```

Add at ux_maturity.py module top: `from dazzle.render.context import TransitionContext` and `from dazzle.render.fragment.state_affordance import gated_row_transitions`.

Bump the `"3c"` `Criterion`: `declared` 3 → 4, `probe` stays `_probe_3c`, and set evidence to:

```python
        "#1558 L3 + current-state gating L4 — state-machine transition affordances are "
        "filtered to those valid from the record's CURRENT state (from_state == current or "
        "'*', via the shared `gated_row_transitions`) on BOTH the detail view (request-time "
        "filter in page_routes) and regular list rows (per-row, in the row actions cell). "
        "The compile build preserves `from_state` (TransitionContext); guards remain enforced "
        "by HTTP validation on click; no state machine = byte-identical.",
```

- [ ] **Step 4: Run tests + maturity gate**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_ux_maturity_3c.py -q -p no:cacheprovider`
Expected: PASS.
Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/ -q -p no:cacheprovider -k "ux_maturity or maturity"`
Expected: PASS. Index moves 3.92 → 4.0 (13/13 at L4); update any test asserting the exact prior index/count (was 12/13).

- [ ] **Step 5: Lint + type-check + commit**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/qa/ux_maturity.py tests/unit/test_ux_maturity_3c.py --fix && /Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/qa/ux_maturity.py`

```bash
git add -A
git commit -m "feat(qa): 3c state-gated affordance to L4 with a real gating probe (#1558)"
```

---

## Final verification (before ship)

- [ ] Full type check: `/Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle` → `Success`.
- [ ] Meta-gates (the v0.96.5 lesson): `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/ -q -p no:cacheprovider -m gate` AND `-k "no_bare_except or gate_marker or deferred_imports"` → PASS.
- [ ] Broad suite across changed seams: `-k "transition or state_affordance or detail or data_row or list or queue or ux_maturity or card_safety or workspace_composite or template_compiler"` → PASS.
- [ ] Adversarial review of Task 4 (the list-render path) before ship — dead-affordance safety, card-safety invariants, byte-identical-without-state-machine.
- [ ] Ship: `/bump patch`, CHANGELOG under `### Added` + an `### Agent Guidance` note (state-machine entities now auto-gate transition affordances by current state on detail + list rows), push main BEFORE tag, monitor CI (incl the meta-gates).

## Self-review notes (author)

- **Spec coverage:** from_state preservation (T1) ✓; shared helper (T2) ✓; detail filter (T3) ✓; list-row affordances (T4) ✓; probe L3→L4 (T5) ✓; guards-on-click + queue-untouched + byte-identical (constraints) ✓.
- **Type consistency:** `gated_row_transitions(list[TransitionContext], str) -> list[TransitionContext]` used identically in T2/T3/T4/T5; `TransitionContext.from_state` added in T1 and consumed everywhere after.
- **YAGNI:** no guard eval; queue untouched; no new DSL.
- **Risk:** T4 touches the converged list-render path (card-safety/composite gated) — highest risk, adversarial-reviewed before ship.
