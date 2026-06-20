# Fragment Detail Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the FragmentSurfaceAdapter to handle `mode: view` (detail surfaces), so any surface that displays a single entity record (`task_detail`, `comment_detail`, `user_detail`, etc.) can be flipped to `render: fragment`. Flip `simple_task.task_detail` as the first detail-mode proving case. Adds a second mode beyond LIST to the typed Fragment substrate.

**Architecture:** A detail surface renders one row's fields as a series of (label, value) pairs inside a Region of `kind="detail"`. The Fragment composition uses Stack-of-Row to express the definition-list shape (Heading-level-4 for the label, Text for the value), keeping to the existing primitive vocabulary — no new primitive type introduced. CSS rules under `.dz-region--kind-detail` shape the layout. Plan 7+ can introduce a dedicated `DefinitionList` primitive when richer detail features (related groups, transitions, edit-in-place) land.

**Tech Stack:** Python 3.12+, the typed Fragment substrate from Plans 1-5.

**Reference:** Plan 5's carry-forward #2 ("convert another surface mode"). The spec's Phase 6 is the broader migration arc; this plan covers the detail-mode adapter portion of that arc.

**Out of scope:** state-machine transitions (Edit/Delete/Approve buttons), related groups, edit-in-place via InlineEdit, audit history panels, persona-conditional field display. Detail surfaces with those features stay on the Jinja path until later plans extend the adapter.

---

## Stop condition

> **`simple_task.task_detail` renders end-to-end via FragmentRenderer with parity to the Jinja path on the happy path.** A surface with `mode: view` and `render: fragment` produces a Fragment tree containing the title heading and the labelled fields. CSS rules style the detail region. Both renderers produce structurally-equivalent HTML for the same IR + ctx (parity test).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle_http/runtime/renderers/fragment_adapter.py` | Modify | Add `_build_view(surface, ctx)` method; route SurfaceMode.VIEW to it |
| `src/dazzle_page/runtime/template_renderer.py` | Modify | Extend `render_surface(surface, ctx) -> str` to handle SurfaceMode.VIEW (currently raises NotImplementedError for non-LIST) |
| `src/dazzle_page/runtime/page_routes.py` | Modify | `_build_dispatch_ctx` populates the right ctx shape for detail surfaces |
| `src/dazzle_page/runtime/static/css/components/fragment-primitives.css` | Modify | Add `.dz-region--kind-detail` rules (definition-list styling) |
| `examples/simple_task/dsl/app.dsl` | Modify | Add `render: fragment` to the `task_detail` surface |
| `tests/unit/runtime/test_fragment_surface_adapter.py` | Modify | Append tests for `_build_view` |
| `tests/unit/runtime/test_jinja_renderer_adapter.py` | Modify | Append a test confirming render_surface handles VIEW |
| `tests/unit/test_fragment_primitive_css.py` | Modify | Append `dz-region--kind-detail` to `_REQUIRED_CLASSES` |
| `tests/integration/test_simple_task_render_fragment.py` | Modify | Append a parity test for task_detail |
| `CHANGELOG.md` | Modify | Note detail-mode support |

10 files. 6-7 tasks.

---

## Conventions

- **TDD throughout.** Failing test → minimal implementation → commit.
- **Lint after each task:** `ruff check src/ tests/ --fix && ruff format src/ tests/`
- **Type check:** `mypy src/dazzle/render --strict` and `mypy src/dazzle_http --ignore-missing-imports` clean.
- **Commit messages:** `feat(render): <subject>` for adapter + DSL flip; `feat(ui): <subject>` for CSS; `test: <subject>` for tests.

---

## Task 1: FragmentSurfaceAdapter handles VIEW mode

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/fragment_adapter.py`
- Modify: `tests/unit/runtime/test_fragment_surface_adapter.py`

The current adapter raises `NotImplementedError` for VIEW. Add a `_build_view` method that produces a Surface with header + Region(kind="detail") containing a Stack of (label, value) Rows.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/runtime/test_fragment_surface_adapter.py`:

```python
from dazzle.render.fragment import Heading, Region, Row, Stack, Surface, Text


def test_view_mode_produces_surface_with_detail_region() -> None:
    """SurfaceMode.VIEW renders a single record's fields as a definition-
    list-shaped Region (kind=detail)."""
    surface = SurfaceSpec(
        name="task_detail",
        title="Task Detail",
        mode=SurfaceMode.VIEW,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"key": "title", "label": "Title", "value": "Buy milk"},
            {"key": "status", "label": "Status", "value": "open"},
        ],
        "region_name": "task_detail_main",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.header, Heading)
    assert fragment.header.body == "Task Detail"
    assert isinstance(fragment.body, Region)
    assert fragment.body.kind == "detail"
    # Body holds a Stack of Rows — one Row per field
    assert isinstance(fragment.body.body, Stack)
    assert len(fragment.body.body.children) == 2


def test_view_mode_field_row_shape() -> None:
    """Each field renders as a Row with a Heading (label) and Text (value)."""
    surface = SurfaceSpec(
        name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task"
    )
    ctx = {
        "fields": [{"key": "title", "label": "Title", "value": "Hello"}],
        "region_name": "x_main",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    stack = fragment.body.body
    first_row = stack.children[0]
    assert isinstance(first_row, Row)
    # First child is the label (Heading), second is the value (Text)
    label, value = first_row.children
    assert isinstance(label, Heading)
    assert label.body == "Title"
    assert isinstance(value, Text)
    assert value.body == "Hello"


def test_view_mode_handles_no_fields_gracefully() -> None:
    """A detail surface with no fields renders an EmptyState rather than
    an empty Stack (which would violate the Stack invariant)."""
    from dazzle.render.fragment import EmptyState

    surface = SurfaceSpec(
        name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task"
    )
    ctx = {"fields": [], "region_name": "x_main"}
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment.body.body, EmptyState)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v 2>&1 | tail -10
```

Expected: 4 existing PASS, 3 new FAIL (NotImplementedError for VIEW mode).

- [ ] **Step 3: Implement `_build_view`**

In `src/dazzle_http/runtime/renderers/fragment_adapter.py`, update the dispatch in `build` and add `_build_view`:

```python
# In `build`, change:
#   if surface.mode == SurfaceMode.LIST:
#       return self._build_list(surface, ctx)
#   raise NotImplementedError(...)
# to:
    def build(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Fragment:
        if surface.mode == SurfaceMode.LIST:
            return self._build_list(surface, ctx)
        if surface.mode == SurfaceMode.VIEW:
            return self._build_view(surface, ctx)
        raise NotImplementedError(
            f"FragmentSurfaceAdapter does not yet support mode {surface.mode.name!r}; "
            f"Plans 3-6 cover LIST and VIEW. CREATE/EDIT/CUSTOM land in later plans."
        )
```

Add `_build_view` (after `_build_list`):

```python
    def _build_view(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Surface:
        """Detail surface — single record's fields as a definition-list-shaped Region.

        Each field renders as a Row of (Heading-level-4 label, Text value).
        Stack groups them. The Region carries kind="detail" so CSS can
        target the layout (definition-list style with label-column +
        value-column).
        """
        from dazzle.render.fragment import (
            EmptyState,
            Heading,
            Region,
            Row,
            Stack,
            Surface,
            Text,
        )

        title = surface.title or surface.name.replace("_", " ").title()
        fields: list[dict[str, Any]] = ctx.get("fields", [])

        if not fields:
            body: Fragment = EmptyState(
                title="No data",
                description="This record has no displayable fields.",
            )
        else:
            rows = tuple(
                Row(
                    children=(
                        Heading(str(f.get("label", f.get("key", ""))), level=4),
                        Text(_format_cell(f.get("value"), str(f.get("kind", "text")))),
                    ),
                    align="start",
                )
                for f in fields
            )
            body = Stack(children=rows, gap="sm")

        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="detail", body=body),
        )
```

The imports inside `_build_view` are intentional — local imports avoid loading the full primitive set when only `_build_list` is used. Move them to the top of the file if mypy strict complains about deferred imports.

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v
```

Expected: 7 PASS (4 existing + 3 new). The unsupported-mode test from Plan 3 still passes because it now uses `SurfaceMode.CREATE` or another not-yet-supported mode — adjust if it referenced VIEW.

Verify by reading the test:

```bash
grep -n "test_unsupported_mode_raises\|SurfaceMode\." tests/unit/runtime/test_fragment_surface_adapter.py
```

If the unsupported-mode test referenced `SurfaceMode.VIEW`, change it to `SurfaceMode.CREATE` or `SurfaceMode.EDIT` (still NotImplementedError after this task).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/renderers/fragment_adapter.py tests/unit/runtime/test_fragment_surface_adapter.py
git commit -m "feat(render): FragmentSurfaceAdapter handles SurfaceMode.VIEW"
```

---

## Task 2: render_surface (Jinja adapter) handles VIEW mode

The minimal `render_surface(surface, ctx) -> str` in `template_renderer.py` (added in Plan 3 Task 1) currently only handles LIST. The parity test needs both renderers to produce HTML for the same VIEW-shape ctx.

**Files:**
- Modify: `src/dazzle_page/runtime/template_renderer.py`
- Modify: `tests/unit/runtime/test_jinja_renderer_adapter.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/runtime/test_jinja_renderer_adapter.py`:

```python
def test_jinja_renderer_renders_a_minimal_view_surface() -> None:
    """The minimal render_surface path supports VIEW mode (Plan 6)."""
    surface = SurfaceSpec(
        name="task_detail",
        title="Task Detail",
        mode=SurfaceMode.VIEW,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"key": "title", "label": "Title", "value": "Buy milk"},
            {"key": "status", "label": "Status", "value": "open"},
        ],
        "region_name": "task_detail_main",
    }
    renderer = JinjaRenderer()
    html = renderer.render(surface, ctx)
    assert isinstance(html, str)
    assert "Title" in html
    assert "Buy milk" in html
    assert "Status" in html
    assert "open" in html
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_jinja_renderer_adapter.py::test_jinja_renderer_renders_a_minimal_view_surface -v
```

Expected: FAIL with `NotImplementedError` from `render_surface`.

- [ ] **Step 3: Extend render_surface**

In `src/dazzle_page/runtime/template_renderer.py`, find `render_surface`:

```bash
grep -n "def render_surface\|SurfaceMode.LIST\|NotImplementedError" src/dazzle_page/runtime/template_renderer.py | head -10
```

Locate the LIST-only branch and add a VIEW branch alongside. The minimal path produces a definition-list-shaped HTML directly (no PageContext, no full request path — just enough for parity testing). Keep the production request path unchanged.

The actual render-surface implementation is plan-specific to Dazzle's existing template machinery. The simplest minimal VIEW render: emit a `<div class="dz-detail">` with header + a `<dl>` of `(dt, dd)` pairs. This matches the structural shape Fragment produces, so parity assertions will hold:

```python
# Inside render_surface(surface, ctx):
#   ... existing LIST branch ...
    if surface.mode == SurfaceMode.VIEW:
        title = surface.title or surface.name.replace("_", " ").title()
        fields = ctx.get("fields", [])
        if not fields:
            body_html = "<p>No data.</p>"
        else:
            items = "".join(
                f"<dt>{f['label']}</dt><dd>{f['value']}</dd>"
                for f in fields
            )
            body_html = f"<dl class='dz-list-table'>{items}</dl>"
        return (
            f'<section class="dz-surface">'
            f'<header class="dz-surface__header"><h1>{title}</h1></header>'
            f'<div class="dz-surface__body">'
            f'<section class="dz-region dz-region--kind-detail">{body_html}</section>'
            f'</div></section>'
        )
```

(Adjust to match the exact existing structure of `render_surface` — it might use Jinja template lookup rather than f-strings. Whatever the existing pattern is, follow it for VIEW.)

The test asserts string content: "Title", "Buy milk", etc. The exact HTML shape doesn't have to match Fragment's byte-for-byte — both just need to *contain* the data.

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_jinja_renderer_adapter.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_page/runtime/template_renderer.py tests/unit/runtime/test_jinja_renderer_adapter.py
git commit -m "feat(render): render_surface handles VIEW mode for parity testing"
```

---

## Task 3: page_routes builds the right ctx for VIEW surfaces

The existing `_build_dispatch_ctx` builds the LIST shape (`items`, `columns`, `endpoint`, etc.). For VIEW surfaces, the shape is `fields` (list of `{key, label, value}` dicts).

**Files:**
- Modify: `src/dazzle_page/runtime/page_routes.py`

- [ ] **Step 1: Locate and inspect the current ctx-builder**

```bash
grep -n "_build_dispatch_ctx\|_maybe_dispatch_inner_html" src/dazzle_page/runtime/page_routes.py | head -10
sed -n '1080,1140p' src/dazzle_page/runtime/page_routes.py
```

Read the function. Identify how it currently extracts the LIST shape from the request's render context. Look for `table` or similar.

- [ ] **Step 2: Add VIEW shape extraction**

The Jinja path for VIEW receives a `detail` object (per the detail_view.html template) with structured fields. Extract those into a flat `[{key, label, value}, ...]` list.

Concretely, the ctx-builder should:

```python
# Inside _build_dispatch_ctx (or wherever the dispatch ctx is built):
if surface.mode == SurfaceMode.VIEW:
    detail = render_ctx.get("detail")
    if detail is None:
        return None  # default-deny — production VIEW path lacks fields → legacy
    fields = []
    for section in getattr(detail, "sections", []):
        for f in getattr(section, "fields", []):
            fields.append({
                "key": getattr(f, "key", "") or getattr(f, "name", ""),
                "label": getattr(f, "label", "") or getattr(f, "key", ""),
                "value": getattr(f, "value", "") or "",
                "kind": getattr(f, "type", "text"),
            })
    return {"fields": fields, "region_name": surface.name + "_main"}
```

The exact attribute names depend on the existing render-context shape. Read the Jinja `detail_view.html` template and the code that populates `detail` — search:

```bash
grep -rn "detail = \|detail.sections\|detail.fields" src/dazzle_page/runtime/ 2>/dev/null | head -10
```

If the existing path stores fields differently (e.g. flat `dt/dd` pairs already, or per-section nested structure), adapt the extraction accordingly. The goal is: feed `_build_view` exactly the `fields` list it expects.

If the production-path `render_ctx` doesn't have a clean field-list shape because the detail page composes from many sources (audit history, related groups, transitions), keep the default-deny behaviour: return None and let the legacy path handle production VIEW for now. The Plan 6 stop condition only requires `simple_task.task_detail` to flip — which is a simple field list.

- [ ] **Step 3: Run the integration smoke**

```bash
pytest tests/integration/test_simple_task_render_fragment.py -v 2>&1 | tail -10
```

Expected: existing tests pass. New parity test (Task 6) hasn't been added yet.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_page/runtime/page_routes.py
git commit -m "feat(runtime): _build_dispatch_ctx handles VIEW surfaces"
```

---

## Task 4: CSS for dz-region--kind-detail

**Files:**
- Modify: `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`
- Modify: `tests/unit/test_fragment_primitive_css.py`

- [ ] **Step 1: Add the new class to the presence test**

In `tests/unit/test_fragment_primitive_css.py`, append `"dz-region--kind-detail"` to `_REQUIRED_CLASSES`:

```python
_REQUIRED_CLASSES: tuple[str, ...] = (
    # ... existing entries ...
    # Plan 6 — detail-mode region
    "dz-region--kind-detail",
)
```

Run the test:

```bash
pytest tests/unit/test_fragment_primitive_css.py -v 2>&1 | tail -5
```

Expected: previous cases PASS, new `dz-region--kind-detail` case FAILS.

- [ ] **Step 2: Add CSS rules**

In `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`, after the `.dz-region--kind-list` block, add:

```css
  /* Detail kind — definition-list-shaped layout. Each child Row
     renders as label (Heading level 4) + value (Text). The Stack
     wrapper provides the row separation; this rule provides the
     intra-row layout. */

  .dz-region--kind-detail {
    /* Detail content cascades down from .dz-stack inside; only the
       region-level overflow guard is region-specific. */
  }

  .dz-region--kind-detail .dz-stack {
    gap: var(--space-md);
  }

  .dz-region--kind-detail .dz-row {
    /* Two-column label/value layout: fixed-width label column,
       remaining width for value. Container queries make this
       responsive without media queries. */
    display: grid;
    grid-template-columns: minmax(8rem, 12rem) 1fr;
    gap: var(--space-md);
    align-items: baseline;
  }

  .dz-region--kind-detail .dz-row > .dz-heading {
    /* Label column — muted weight, smaller size, right-aligned. */
    color: var(--colour-text-muted);
    font-weight: var(--weight-medium);
    text-align: end;
  }

  .dz-region--kind-detail .dz-row > .dz-text {
    /* Value column — default body text. */
    color: var(--colour-text);
  }
```

- [ ] **Step 3: Verify presence test passes**

```bash
pytest tests/unit/test_fragment_primitive_css.py -v
```

Expected: all PASS (existing 10 + 1 new).

- [ ] **Step 4: Rebuild dist**

```bash
python scripts/build_dist.py 2>&1 | tail -5
```

Expected: success. Verify the new class is in the bundle:

```bash
grep -c "dz-region--kind-detail" src/dazzle_page/runtime/static/dist/dazzle.min.css
```

Expected: ≥ 1.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_page/runtime/static/css/components/fragment-primitives.css tests/unit/test_fragment_primitive_css.py src/dazzle_page/runtime/static/dist/
git commit -m "feat(ui): CSS for dz-region--kind-detail (definition-list layout)"
```

---

## Task 5: Flip simple_task.task_detail to render: fragment

**Files:**
- Modify: `examples/simple_task/dsl/app.dsl`

- [ ] **Step 1: Add the clause**

In `examples/simple_task/dsl/app.dsl`, find the `task_detail` surface declaration (around line 275):

```dsl
surface task_detail "Task Detail":
  uses entity Task
  mode: view
```

Add `render: fragment`:

```dsl
surface task_detail "Task Detail":
  uses entity Task
  mode: view
  render: fragment
```

- [ ] **Step 2: Validate**

```bash
cd examples/simple_task && dazzle validate 2>&1 | tail -5 ; cd -
```

Expected: success.

- [ ] **Step 3: Verify in-process**

```bash
python -c "
from pathlib import Path
from dazzle.core.dsl_parser_impl import parse_modules
from dazzle.core.linker import build_appspec
from dazzle_http.runtime.renderers.init import default_renderer_names

mods = parse_modules([Path('examples/simple_task').resolve()])
spec = build_appspec(mods, root_module_name='simple_task.core', known_renderers=default_renderer_names())
target = next(s for s in spec.surfaces if s.name == 'task_detail')
print(f'render={target.render!r}')
assert target.render == 'fragment'
print('OK — task_detail flipped to fragment')
"
```

Expected: `render='fragment'` and confirmation.

- [ ] **Step 4: Run the full unit suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add examples/simple_task/dsl/app.dsl
git commit -m "feat(simple_task): flip task_detail to render: fragment"
```

---

## Task 6: Parity test for detail mode

**Files:**
- Modify: `tests/integration/test_simple_task_render_fragment.py`

- [ ] **Step 1: Append the parity test**

Append to `tests/integration/test_simple_task_render_fragment.py`:

```python
def _detail_ctx() -> dict:
    """Deterministic detail-mode context."""
    return {
        "fields": [
            {"key": "title", "label": "Title", "value": "Buy milk"},
            {"key": "status", "label": "Status", "value": "open"},
            {"key": "priority", "label": "Priority", "value": "high"},
        ],
        "region_name": "task_detail_main",
    }


def test_jinja_and_fragment_both_render_detail_fields() -> None:
    """Detail mode: both renderers must include every field's label and value."""
    services = _make_services()

    jinja_surface = SurfaceSpec(
        name="task_detail", title="Task Detail", mode=SurfaceMode.VIEW, entity_ref="Task",
    )
    fragment_surface = SurfaceSpec(
        name="task_detail", title="Task Detail", mode=SurfaceMode.VIEW, entity_ref="Task",
        render="fragment",
    )

    jinja_html = dispatch_render(jinja_surface, ctx=_detail_ctx(), services=services)
    fragment_html = dispatch_render(fragment_surface, ctx=_detail_ctx(), services=services)

    for renderer_name, html in [("jinja", jinja_html), ("fragment", fragment_html)]:
        assert isinstance(html, str), f"{renderer_name}: not a string"
        for label in ("Title", "Status", "Priority"):
            assert label in html, f"{renderer_name}: missing label {label!r}"
        for value in ("Buy milk", "open", "high"):
            assert value in html, f"{renderer_name}: missing value {value!r}"


def test_fragment_detail_path_uses_detail_region_kind() -> None:
    """The Fragment-rendered detail surface includes dz-region--kind-detail."""
    services = _make_services()
    fragment_html = dispatch_render(
        SurfaceSpec(
            name="task_detail", title="Task Detail", mode=SurfaceMode.VIEW,
            entity_ref="Task", render="fragment",
        ),
        ctx=_detail_ctx(), services=services,
    )
    assert "dz-region--kind-detail" in fragment_html
```

- [ ] **Step 2: Run the parity test**

```bash
pytest tests/integration/test_simple_task_render_fragment.py -v
```

Expected: all PASS (3 existing list-mode + 2 new detail-mode = 5 tests).

If a parity assertion fails, check the Jinja vs Fragment output side-by-side and adjust either the Jinja `render_surface` VIEW branch (Task 2) or the Fragment `_build_view` (Task 1) — typically a missing field, missing escape, or label/value swap.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_simple_task_render_fragment.py
git commit -m "test(render): parity test for VIEW mode (Jinja vs Fragment task_detail)"
```

---

## Task 7: CHANGELOG + final verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the full unit suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 2: Run mypy**

```bash
mypy src/dazzle/render --strict
mypy src/dazzle src/dazzle_http --ignore-missing-imports
```

Expected: clean (or no new errors over the pre-existing baseline).

- [ ] **Step 3: Update CHANGELOG**

In `CHANGELOG.md`, add to `## [Unreleased]` section under `### Added`:

```markdown
- **Detail mode for FragmentSurfaceAdapter (Plan 6).** `mode: view`
  surfaces (`task_detail`, etc.) can now flip to `render: fragment`. The
  adapter produces a Surface with a Region(kind="detail") containing a
  Stack of (Heading-label, Text-value) Rows. CSS rules under
  `.dz-region--kind-detail` lay out the definition-list-shaped pairs.
- `simple_task.task_detail` flipped to `render: fragment` as the first
  detail-mode proving case. Parity test in
  `tests/integration/test_simple_task_render_fragment.py` confirms
  Jinja and Fragment renderers produce structurally-equivalent output.
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note Plan 6 detail-mode support"
```

---

## Plan completion checklist

- [ ] `pytest tests/unit/runtime/ tests/integration/test_simple_task_render_fragment.py tests/unit/test_fragment_primitive_css.py -v` — all pass.
- [ ] `pytest tests/ -m "not e2e"` — no regressions.
- [ ] `mypy src/dazzle/render --strict` — clean.
- [ ] `git status` clean.
- [ ] **Stop condition met:** simple_task.task_detail renders end-to-end via Fragment with structural parity to Jinja. Detail-mode CSS is in place.

---

## Self-Review

**Spec coverage:**
- Plan 5 carry-forward #2 (convert another surface mode): closed by adding VIEW mode and flipping task_detail.
- Spec Phase 6 (data primitives + surface modes): partially advanced — VIEW added; CREATE/EDIT/CUSTOM still pending.

**Placeholder scan:**
- All file paths exact.
- Every code block is concrete.
- The "If the production-path render_ctx doesn't have a clean field-list shape" hedge in Task 3 is intentional — production VIEW context structure varies by entity. The hedge tells the engineer to default-deny in that case (consistent with Plan 3's containment), not to invent a shape.

**Type consistency:**
- `_build_view(surface, ctx) -> Surface` (Task 1) and `_build_list` share the same return type (Surface).
- `fields` ctx key is consistent across Tasks 1, 2, 3, 6.
- The new `.dz-region--kind-detail` class is consistent across Task 4's CSS and the integration parity test in Task 6.

**Scope check:**
- Plan covers detail-mode adapter + flip. 7 tasks. Out-of-scope detail features (transitions, related groups, edit-in-place) are explicitly listed.
