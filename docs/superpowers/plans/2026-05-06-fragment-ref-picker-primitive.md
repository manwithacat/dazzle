# Plan 14 — RefPicker Primitive: Close the REF Field Adapter Gap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a typed `RefPicker` primitive to the Fragment substrate, route REF fields to it from the adapter's form path, and remove `ref` from the audit's unsupported-types set. Closes Phase 2A — brings honest example coverage from 50/78 to 78/78.

**Architecture:** Add a frozen `RefPicker` dataclass (parallel to Combobox in shape, distinct in semantics) carrying `name`, `label`, `ref_api: URL`, `initial_value`, `initial_label`, `required`. The Fragment renderer emits a `<select>` with `data-ref-api` + `data-selected-value` attributes and an `x-init="dz.filterRefSelect($el)"` hook — re-using the existing client-side machinery that already powers Jinja-path ref filters (see `dz-alpine.js:2196`). The adapter's `_field_to_primitive` routes REF fields to RefPicker; the form-ctx builder threads `ref_api` from `FieldContext` into the field dict. No backend round-trip at render time — options arrive client-side, same as the legacy path.

**Tech Stack:** Python 3.12 (dataclasses), Fragment substrate, FastAPI, Alpine.js (`dz.filterRefSelect`).

**Pre-flight numbers** (from Plan 13's audit): 28 surfaces blocked on `unsupported_field_type=ref`, all single-class. Closing this brings honest cumulative coverage from 50/78 (64%) to 78/78 (100%).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/dazzle/render/fragment/primitives/forms.py` (modify) | Add `RefPicker` frozen dataclass next to Combobox |
| `src/dazzle/render/fragment/primitives/_base.py` (modify) | Add `RefPicker` to the `Fragment` union |
| `src/dazzle/render/fragment/renderer.py` (modify) | Add render branch for `RefPicker` |
| `src/dazzle_page/runtime/static/css/components/fragment-primitives.css` (modify) | `.dz-ref-picker` rules (parallel to `.dz-combobox`) |
| `src/dazzle_http/runtime/renderers/fragment_adapter.py` (modify) | `_field_to_primitive` routes REF → RefPicker |
| `src/dazzle_page/runtime/page_routes.py` (modify) | `_build_dispatch_ctx` threads `ref_api` from FieldContext into field dict |
| `src/dazzle/render/fragment/coverage.py` (modify) | Remove `"ref"` from `_UNSUPPORTED_FIELD_TYPES` |
| `tests/unit/test_fragment_primitive_css.py` (modify) | Add `dz-ref-picker` to `_REQUIRED_CLASSES` |
| `tests/integration/test_examples_fragment_http.py` (modify) | Add HTTP test asserting REF form renders RefPicker chrome |
| `docs/superpowers/plans/migration-roadmap.md` (modify) | Status table + post-Plan-14 coverage matrix |
| `CHANGELOG.md` (modify) | Changed (audit closes ref) + Added (RefPicker primitive) + Agent Guidance |

---

## Task 1: RefPicker primitive (frozen dataclass)

**Files:**
- Modify: `src/dazzle/render/fragment/primitives/forms.py`

- [ ] **Step 1: Read the current Combobox dataclass for shape parity**

```bash
sed -n '55,70p' src/dazzle/render/fragment/primitives/forms.py
```

Note its frozen + slots config and the `__post_init__` validation pattern.

- [ ] **Step 2: Add the RefPicker dataclass after Combobox**

Append to `src/dazzle/render/fragment/primitives/forms.py`, right after the Combobox class:

```python
@dataclass(frozen=True, slots=True)
class RefPicker:
    """Reference-field picker — selectable list of related entity rows.

    Distinct from Combobox: where Combobox carries a static option tuple
    (sufficient for enum), RefPicker carries a `ref_api` URL pointing
    at the related entity's list endpoint. Options are populated
    client-side at render time by the existing dz.filterRefSelect
    machinery (`src/dazzle_page/runtime/static/js/dz-alpine.js:2196`).

    `initial_label` lets EDIT forms display the currently-selected
    record's display field without an extra round-trip on render —
    the form-ctx builder fills it from the persisted row.
    """

    name: str
    label: str
    ref_api: URL
    required: bool = False
    initial_value: str = ""
    initial_label: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RefPicker requires a non-empty name")
        if not self.label:
            raise ValueError("RefPicker requires a non-empty label")
```

- [ ] **Step 3: Add a unit test for the new primitive**

Create `tests/unit/render/fragment/primitives/test_ref_picker.py`:

```python
"""RefPicker primitive — Phase 2A's typed REF-field building block."""

import pytest

from dazzle.render.fragment import URL
from dazzle.render.fragment.primitives.forms import RefPicker


def test_ref_picker_minimal_construction() -> None:
    rp = RefPicker(name="assigned_to", label="Assigned", ref_api=URL("/user"))
    assert rp.name == "assigned_to"
    assert rp.label == "Assigned"
    assert rp.ref_api.value == "/user"
    assert rp.required is False
    assert rp.initial_value == ""
    assert rp.initial_label == ""


def test_ref_picker_with_initial_selection() -> None:
    rp = RefPicker(
        name="assigned_to",
        label="Assigned",
        ref_api=URL("/user"),
        required=True,
        initial_value="00000000-0000-0000-0000-000000000001",
        initial_label="Alice",
    )
    assert rp.required is True
    assert rp.initial_label == "Alice"


def test_ref_picker_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="non-empty name"):
        RefPicker(name="", label="X", ref_api=URL("/a"))


def test_ref_picker_rejects_empty_label() -> None:
    with pytest.raises(ValueError, match="non-empty label"):
        RefPicker(name="x", label="", ref_api=URL("/a"))


def test_ref_picker_is_frozen() -> None:
    rp = RefPicker(name="x", label="X", ref_api=URL("/a"))
    with pytest.raises((AttributeError, TypeError)):
        rp.name = "y"  # type: ignore[misc]
```

- [ ] **Step 4: Run the tests**

```bash
pytest tests/unit/render/fragment/primitives/test_ref_picker.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/forms.py tests/unit/render/fragment/primitives/test_ref_picker.py
git commit -m "feat(fragment): add RefPicker primitive (Plan 14 T1)

Frozen dataclass paralleling Combobox in shape but carrying ref_api as
a typed URL instead of static options. Distinct primitive because the
two have different semantics — Combobox is for enum (static), RefPicker
is for REF (dynamic, lazy-fetched client-side).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Add RefPicker to the Fragment union

**Files:**
- Modify: `src/dazzle/render/fragment/primitives/_base.py`

- [ ] **Step 1: Find the union type alias**

```bash
grep -n "^Fragment = \|^Fragment: \|Fragment =" src/dazzle/render/fragment/primitives/_base.py
```

It's a `Fragment` type alias listing every primitive in a `Union[...]`.

- [ ] **Step 2: Add RefPicker to the union**

In the same file, find the line that imports `Combobox`. Add `RefPicker` next to it. Then in the `Fragment` union, add `| RefPicker` next to `| Combobox`. Match the existing alphabetical-or-grouping convention.

- [ ] **Step 3: Re-export from the package**

```bash
grep -n "Combobox" src/dazzle/render/fragment/__init__.py
```

Wherever Combobox appears in `__init__.py` exports, add RefPicker on the next line. Match the alphabetical sort order if there is one.

- [ ] **Step 4: Verify imports work**

```bash
python -c "from dazzle.render.fragment import RefPicker, URL; r = RefPicker(name='x', label='X', ref_api=URL('/a')); print(r)"
```

Expected: prints the RefPicker dataclass. If ImportError, the `__init__.py` export is in the wrong section.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/_base.py src/dazzle/render/fragment/__init__.py
git commit -m "feat(fragment): add RefPicker to the Fragment union + package exports (Plan 14 T2)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Renderer dispatch for RefPicker

**Files:**
- Modify: `src/dazzle/render/fragment/renderer.py`

- [ ] **Step 1: Find the Combobox render branch**

```bash
grep -n "Combobox\|elif isinstance(node, Combobox)" src/dazzle/render/fragment/renderer.py | head -5
```

The match-dispatch in the FragmentRenderer covers each primitive. Combobox is the closest analogue; RefPicker's branch goes adjacent.

- [ ] **Step 2: Write the failing test first**

Create `tests/unit/render/fragment/test_renderer_ref_picker.py`:

```python
"""RefPicker → HTML rendering."""

from dazzle.render.fragment import URL, RefPicker
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


def test_ref_picker_renders_select_with_data_ref_api() -> None:
    """RefPicker emits a <select> with data-ref-api carrying the URL,
    so dz.filterRefSelect can lazy-fetch options at render time."""
    html = _render(
        RefPicker(name="assigned_to", label="Assigned", ref_api=URL("/user"))
    )
    assert "<select" in html
    assert 'name="assigned_to"' in html
    assert 'data-ref-api="/user"' in html
    assert "Assigned" in html  # label text


def test_ref_picker_renders_initial_selection_as_placeholder_option() -> None:
    """When initial_value is set, render an <option> with that value
    and the initial_label as visible text — so EDIT forms show the
    current selection before the lazy fetch resolves."""
    html = _render(
        RefPicker(
            name="assigned_to",
            label="Assigned",
            ref_api=URL("/user"),
            initial_value="abc-123",
            initial_label="Alice",
        )
    )
    assert 'value="abc-123"' in html
    assert "Alice" in html


def test_ref_picker_required_emits_required_attr() -> None:
    html = _render(
        RefPicker(name="x", label="X", ref_api=URL("/a"), required=True)
    )
    assert "required" in html


def test_ref_picker_emits_alpine_init_hook() -> None:
    """The select must carry x-init="dz.filterRefSelect($el)" so the
    existing client-side fetch machinery picks it up."""
    html = _render(RefPicker(name="x", label="X", ref_api=URL("/a")))
    assert "dz.filterRefSelect" in html


def test_ref_picker_emits_dz_ref_picker_class() -> None:
    """CSS hook for styling — parallels .dz-combobox."""
    html = _render(RefPicker(name="x", label="X", ref_api=URL("/a")))
    assert "dz-ref-picker" in html
```

- [ ] **Step 3: Run the failing test**

```bash
pytest tests/unit/render/fragment/test_renderer_ref_picker.py -v
```

Expected: all 5 fail — the renderer has no RefPicker branch yet.

- [ ] **Step 4: Implement the renderer branch**

In `src/dazzle/render/fragment/renderer.py`, add a case for RefPicker. The exact form depends on the existing dispatch shape (match-statement vs isinstance ladder); follow the prevailing style. The branch produces:

```python
case RefPicker(
    name=name,
    label=label,
    ref_api=ref_api,
    required=required,
    initial_value=initial_value,
    initial_label=initial_label,
):
    from dazzle.render.fragment.escape import escape_attr, escape_text

    label_html = (
        f'<label class="dz-ref-picker__label" for="{escape_attr(name)}">'
        f"{escape_text(label)}</label>"
    )
    required_attr = " required" if required else ""
    initial_option = ""
    if initial_value:
        initial_option = (
            f'<option value="{escape_attr(initial_value)}" selected>'
            f"{escape_text(initial_label or initial_value)}</option>"
        )
    select_html = (
        f'<select class="dz-ref-picker__select" '
        f'id="{escape_attr(name)}" '
        f'name="{escape_attr(name)}" '
        f'data-ref-api="{escape_attr(ref_api.value)}" '
        f'data-selected-value="{escape_attr(initial_value)}" '
        f'x-init="dz.filterRefSelect($el)"'
        f"{required_attr}>"
        f"{initial_option}"
        f"</select>"
    )
    return f'<div class="dz-ref-picker">{label_html}{select_html}</div>'
```

(Adapt to match the existing dispatch shape — if the renderer uses a `_render_node` method on a class, put this in there; if it uses a top-level function with `match`, put it there. Read `renderer.py` to confirm.)

- [ ] **Step 5: Run the test**

```bash
pytest tests/unit/render/fragment/test_renderer_ref_picker.py -v
```

Expected: all 5 pass.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/render/fragment/renderer.py tests/unit/render/fragment/test_renderer_ref_picker.py
git commit -m "feat(fragment): renderer emits RefPicker as <select> with data-ref-api hook (Plan 14 T3)

Re-uses the existing dz.filterRefSelect Alpine machinery from
dz-alpine.js:2196 — no new client-side code needed.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: CSS for RefPicker

**Files:**
- Modify: `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`
- Modify: `tests/unit/test_fragment_primitive_css.py`

- [ ] **Step 1: Add RefPicker CSS rules**

Append to the form-section of `fragment-primitives.css` (right after the `.dz-combobox` block, line ~260):

```css
  /* Plan 14: RefPicker — REF field selector. Parallels .dz-combobox in
     visual treatment; the data-ref-api attribute drives client-side
     option population (see dz-alpine.js:2196). */
  .dz-ref-picker {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
  }

  .dz-ref-picker__label {
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    color: var(--colour-text);
  }

  .dz-ref-picker__select {
    padding: var(--space-sm) var(--space-md);
    font-size: var(--text-base);
    color: var(--colour-text);
    background: var(--colour-surface);
    border: 1px solid var(--colour-border);
    border-radius: var(--radius-sm);
  }
```

- [ ] **Step 2: Add the new classes to the CSS-presence test**

In `tests/unit/test_fragment_primitive_css.py`, append to `_REQUIRED_CLASSES`:

```python
    # Plan 14 — RefPicker (REF field selector)
    "dz-ref-picker",
    "dz-ref-picker__label",
    "dz-ref-picker__select",
```

- [ ] **Step 3: Run the CSS-presence test**

```bash
pytest tests/unit/test_fragment_primitive_css.py -v
```

Expected: all parametrised cases pass, including the three new classes.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_page/runtime/static/css/components/fragment-primitives.css tests/unit/test_fragment_primitive_css.py
git commit -m "style(fragment): CSS for RefPicker (Plan 14 T4)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Adapter routes REF → RefPicker

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/fragment_adapter.py`

- [ ] **Step 1: Read the current `_field_to_primitive`**

```bash
grep -n "_field_to_primitive\|kind == \"enum\"\|kind == \"ref\"" src/dazzle_http/runtime/renderers/fragment_adapter.py
```

The function has an `if kind == "enum"` branch returning Combobox, then a generic `Field` fallthrough. REF currently falls through.

- [ ] **Step 2: Write the failing adapter test**

Add to `tests/integration/test_simple_task_render_fragment.py` (or create a new unit test file `tests/unit/test_fragment_adapter_ref.py`):

```python
"""Adapter: REF fields map to RefPicker (Plan 14)."""

from dazzle.render.fragment.primitives.forms import RefPicker
from dazzle_http.runtime.renderers.fragment_adapter import _field_to_primitive


def test_ref_field_with_ref_api_produces_refpicker() -> None:
    """A field_dict with kind='ref' and a ref_api string produces a
    RefPicker — the adapter's typed REF branch."""
    primitive = _field_to_primitive({
        "name": "assigned_to",
        "label": "Assigned",
        "kind": "ref",
        "ref_api": "/user",
        "required": True,
        "value": "abc-123",
        "initial_label": "Alice",
    })
    assert isinstance(primitive, RefPicker)
    assert primitive.name == "assigned_to"
    assert primitive.ref_api.value == "/user"
    assert primitive.required is True
    assert primitive.initial_value == "abc-123"
    assert primitive.initial_label == "Alice"


def test_ref_field_without_ref_api_falls_back_to_text_field() -> None:
    """A REF field where ref_api wasn't threaded through (e.g. older
    runtime path) falls back to a plain text Field — graceful, not
    an exception. The audit's job is to flag this gap; the adapter
    keeps rendering."""
    from dazzle.render.fragment.primitives.forms import Field

    primitive = _field_to_primitive({
        "name": "assigned_to",
        "label": "Assigned",
        "kind": "ref",
        # No ref_api key.
    })
    assert isinstance(primitive, Field)
```

- [ ] **Step 3: Run the failing test**

```bash
pytest tests/unit/test_fragment_adapter_ref.py -v
```

Expected: both fail — `_field_to_primitive` has no REF branch.

- [ ] **Step 4: Implement the REF branch**

In `_field_to_primitive`, add a REF branch after the enum branch (and before the generic field_kind_map fallthrough). The exact placement depends on the existing function shape — read it once and insert appropriately:

```python
    if kind == "ref":
        ref_api = str(field_dict.get("ref_api", "")).strip()
        if ref_api:
            from dazzle.render.fragment import URL, RefPicker

            return RefPicker(
                name=name,
                label=label,
                ref_api=URL(ref_api),
                required=required,
                initial_value=initial_value,
                initial_label=str(field_dict.get("initial_label", "") or ""),
            )
        # No ref_api → fall through to text Field (graceful).
```

Make sure the imports are at module top, not inline, if that matches the file's style. Otherwise inline is fine.

- [ ] **Step 5: Run the tests**

```bash
pytest tests/unit/test_fragment_adapter_ref.py -v
```

Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_http/runtime/renderers/fragment_adapter.py tests/unit/test_fragment_adapter_ref.py
git commit -m "feat(adapter): route REF fields to RefPicker (Plan 14 T5)

REF fields with a ref_api in the field dict now produce a RefPicker
primitive instead of falling through to text Field. REF fields
without ref_api still fall through gracefully (audit catches this
as unsupported).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Page route ctx threads ref_api

**Files:**
- Modify: `src/dazzle_page/runtime/page_routes.py`

The form-ctx builder at `_build_dispatch_ctx` line ~1092 already iterates `form.fields`. For each field, it copies a few attributes into a dict for the adapter. Add `ref_api` and `initial_label` to the copy.

- [ ] **Step 1: Read the form ctx loop**

```bash
sed -n '1090,1125p' src/dazzle_page/runtime/page_routes.py
```

Note the existing pattern: `getattr(field, "options", None)` then conditionally added to the entry dict. We mirror that for `ref_api`.

- [ ] **Step 2: Add ref_api + initial_label to the field-dict construction**

After the `options` block (line ~1107-1113), add:

```python
            ref_api = str(getattr(field, "ref_api", "") or "")
            if ref_api:
                entry["ref_api"] = ref_api
            initial_label_value = str(getattr(field, "initial_label", "") or "")
            if initial_label_value:
                entry["initial_label"] = initial_label_value
```

The adapter (Task 5) reads both keys; if absent, it falls back gracefully.

- [ ] **Step 3: Verify the existing FieldContext exposes these attributes**

```bash
grep -n "ref_api\|initial_label" src/dazzle_page/runtime/template_context.py
```

`ref_api` exists (`template_context.py:82`). `initial_label` may not. If absent, this iteration ships with `initial_label=""` and EDIT forms show the FK value in the placeholder until the lazy fetch resolves — not ideal, but acceptable for Plan 14. Adding `initial_label` to FieldContext is a separate concern.

- [ ] **Step 4: Run the relevant test suite**

```bash
pytest tests/integration/test_examples_fragment_http.py -v
```

Expected: still 7 pass — the existing tests don't yet assert RefPicker chrome.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_page/runtime/page_routes.py
git commit -m "feat(page-routes): thread ref_api into Fragment form dispatch ctx (Plan 14 T6)

The Fragment adapter's RefPicker branch (Plan 14 T5) reads
field_dict[\"ref_api\"]; the page route's _build_dispatch_ctx now
populates it from FieldContext.ref_api so the typed Fragment path
gets the same lazy-fetch URL the Jinja path has always used.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Remove `ref` from unsupported + HTTP test + audit re-run

**Files:**
- Modify: `src/dazzle/render/fragment/coverage.py`
- Modify: `tests/integration/test_examples_fragment_http.py`

- [ ] **Step 1: Remove `"ref"` from `_UNSUPPORTED_FIELD_TYPES`**

```bash
grep -n "_UNSUPPORTED_FIELD_TYPES" src/dazzle/render/fragment/coverage.py
```

Edit the frozenset literal to remove `"ref"`. The other three (`uuid`, `json`, `file`) stay — they don't have adapter coverage yet.

- [ ] **Step 2: Add an HTTP test asserting REF form renders RefPicker chrome**

In `tests/integration/test_examples_fragment_http.py`, append:

```python
def test_simple_task_create_form_has_ref_picker_for_assigned_to() -> None:
    """The CREATE form for Task includes a RefPicker for `assigned_to:
    ref User`. This pins the Plan 14 closure end-to-end: REF field in
    DSL → adapter produces RefPicker → renderer emits dz-ref-picker
    chrome → response body contains it."""
    client = _client_for("simple_task")
    resp = client.get("/task/create")
    assert resp.status_code == 200
    body = resp.text
    # Plan 14's chrome: a dz-ref-picker container with a select
    # carrying data-ref-api pointed at the User list endpoint.
    assert "dz-ref-picker" in body, (
        f"simple_task /task/create missing RefPicker chrome. "
        f"body[:500]={body[:500]!r}"
    )
    assert 'data-ref-api="/user"' in body or 'data-ref-api="/users"' in body, (
        f"simple_task /task/create RefPicker missing data-ref-api. "
        f"body[:500]={body[:500]!r}"
    )
```

- [ ] **Step 3: Run the failing test**

```bash
pytest tests/integration/test_examples_fragment_http.py::test_simple_task_create_form_has_ref_picker_for_assigned_to -v
```

Possible outcomes:

- **Pass:** the page route's existing `FieldContext.ref_api` is being populated correctly for simple_task's `assigned_to`, and Tasks 5+6 plumbed it through. Move on.
- **Fail with "missing RefPicker chrome":** the form ctx isn't passing `ref_api` through. Investigate `_build_dispatch_ctx` and confirm `FieldContext.ref_api` is non-empty for `assigned_to`. If FieldContext has it but `_build_dispatch_ctx` doesn't copy it, that's a Task 6 bug — fix.
- **Fail with "missing data-ref-api":** chrome is there but the URL isn't. Check the URL escape path in the renderer.
- **Fail with both URL options not matching:** the runtime's REF API URL convention is different. Run a quick probe to find what URL is actually used (check FieldContext.ref_api for assigned_to in simple_task) and update the test assertion.

- [ ] **Step 4: Run the audit on every example**

```bash
for app in simple_task contact_manager support_tickets ops_dashboard fieldtest_hub; do
  echo "=== $app ==="
  python -m dazzle.cli fragment-audit "examples/$app" --json | python -c "
import json, sys
d = json.load(sys.stdin)
print(f'  ready: {d[\"ready_count\"]}/{d[\"total\"]}, blocked: {d[\"blocked_count\"]}')
for ab in d['aggregated_blockers']:
    print(f'  {ab[\"count\"]:>3d}  {ab[\"kind\"]}={ab[\"detail\"]}')"
done
```

Expected: every example reports `ready: N/N, blocked: 0` (since REF was the only blocker class). Record the numbers — they go into Task 8.

- [ ] **Step 5: Run the full unit + integration suite**

```bash
pytest tests/ -m "not e2e" -q
```

Expected: green. The relaxed Plan 13 assertions (`audit_runs_cleanly`, `--fail-on-blocked` accepting both 0 and 1) keep passing — they accept the new state automatically.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/render/fragment/coverage.py tests/integration/test_examples_fragment_http.py
git commit -m "feat(audit): remove ref from unsupported field types (Plan 14 T7)

The adapter now routes REF fields to RefPicker (Plan 14 T1-T6). The
audit reflects this — REF is no longer flagged as unsupported.
Examples report 0 blockers (simple_task: 11→17, support_tickets:
12→19, ops_dashboard: 7→10, fieldtest_hub: 14→26 — all to ready=total).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Roadmap, CHANGELOG, bump, ship

**Files:**
- Modify: `docs/superpowers/plans/migration-roadmap.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update the roadmap**

In `docs/superpowers/plans/migration-roadmap.md`:

1. Add Plan 14 to the status table:

```markdown
| 14 | RefPicker primitive (Phase 2A) | ✓ Shipped | Typed REF-field primitive; adapter REF branch; page route ref_api threading; audit closes ref blocker — examples back to 78/78 honest |
```

2. Update the coverage matrix to reflect the new state (use the numbers captured in Task 7 Step 4). If every app is now 100% ready, the matrix becomes:

```markdown
| App | Surfaces | Flipped (DSL) | Ready | Blocked |
|---|---|---|---|---|
| simple_task | 17 | 12 / 12 ✓ | 17/17 | 0 |
| ...
| **Total** | **78** | **60 / 60 ✓** | **78/78** | **0** |
```

3. Remove "Phase 2A" from "Where we're going" (it's now shipped). The next planned section is Phase 2B — AegisMark.

4. Add a Plan 14 note to "Lessons learned":

```markdown
### Plan 14 — typed primitives are cheap; client integration is the load-bearing piece

Adding RefPicker as a new dataclass + renderer branch + adapter branch was three small commits. The integration work was threading `ref_api` from `FieldContext` through `_build_dispatch_ctx` into the field dict — one line of plumbing in page_routes.py. The expensive thing was the design call: extend Combobox vs. add a new primitive. New primitive won (clean separation between static-options and lazy-fetched-options semantics) — and the substrate stayed cheap to extend.
```

- [ ] **Step 2: CHANGELOG entry**

Add to `## [Unreleased]` in `CHANGELOG.md`:

```markdown
### Added
- **`RefPicker` Fragment primitive (Plan 14).** Frozen dataclass for REF-typed form fields, parallel in shape to `Combobox` but carrying `ref_api: URL` instead of static options. Renders as a `<select>` with `data-ref-api` + `x-init="dz.filterRefSelect($el)"`, re-using the existing client-side fetch machinery from the Jinja path. Closes the cross-app `unsupported_field_type=ref` blocker (28 surfaces).
- Adapter `_field_to_primitive` now routes `kind="ref"` with a `ref_api` to RefPicker; the page route's `_build_dispatch_ctx` threads `ref_api` (and `initial_label` if available) from `FieldContext` into the field dict.

### Changed
- Honest example coverage rises from 50/78 to 78/78. Every example app now reports zero audit blockers — Phase 2A complete.
- `_UNSUPPORTED_FIELD_TYPES` in `coverage.py` no longer contains `"ref"`. The remaining three (`uuid`, `json`, `file`) stay flagged; they're rare in audit-flippable surfaces and Phase 2B will scope them against AegisMark.

### Agent Guidance
- When the substrate gains a new primitive: (1) frozen dataclass in `primitives/<group>.py`, (2) add to the `Fragment` union in `primitives/_base.py`, (3) re-export from `__init__.py`, (4) renderer branch, (5) CSS rules + presence test entry. The pattern is mechanical; the design call is whether the new primitive is genuinely distinct from existing ones or whether an existing one should be widened. RefPicker chose distinctness because Combobox + ref_api would conflate static-options and lazy-fetch semantics.
```

- [ ] **Step 3: Run the full pre-ship gate**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject'
mypy src/dazzle_http/ --ignore-missing-imports
pytest tests/ -m "not e2e" -q
```

Expected: all green.

- [ ] **Step 4: Commit roadmap + CHANGELOG**

```bash
git add docs/superpowers/plans/migration-roadmap.md CHANGELOG.md
git commit -m "docs: Plan 14 closure — RefPicker shipped, examples 78/78 honest

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Bump and ship**

```
/bump patch
/ship
```

---

## Self-Review

**Spec coverage:** "Add RefPicker primitive" → Task 1. "Route REF fields to it" → Task 5. "Thread ref_api from page routes" → Task 6. "Remove ref from unsupported" → Task 7. Each separately committable. ✓

**Placeholder scan:** No "TBD". The "Possible outcomes" branching in Task 7 Step 3 is intentional — diagnostic guidance, not unfilled work. The discovery accommodation is structural: this plan touches a primitive, a renderer, an adapter, and a page route, in that order; if any of them surfaces an integration problem, the plan tells you where to look. ✓

**Type consistency:** `RefPicker` (Task 1) is referenced by Tasks 2, 3, 5, 7. Same name throughout. `URL` is the existing wrapper type from `dazzle.render.fragment` — RefPicker takes `ref_api: URL` (Task 1), the adapter constructs `URL(ref_api_str)` (Task 5), and the renderer reads `ref_api.value` (Task 3). Unbroken chain. ✓

**Async-fetching design call:** documented in the plan header — RefPicker carries `ref_api` and renders with the Alpine hook; options arrive client-side at render time, not during the server round-trip. This is consistent with the existing Jinja path. The design alternative (server-side pre-fetch) would have forced a backend round-trip per REF field on every form render — slower, harder to test with TestClient, and with no UX benefit since the Alpine path is already proven. ✓
