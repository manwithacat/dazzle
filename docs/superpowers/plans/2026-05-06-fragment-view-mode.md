# Fragment VIEW Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `unsupported_mode=VIEW` (the audit's third-largest blocker, 15 surface occurrences across the five example apps). Extend the FragmentSurfaceAdapter to handle `mode: view` so any surface that displays a single entity record can be flipped to `render: fragment`. Adds the second mode beyond LIST. Supersedes Plan 6's earlier "detail mode" draft, with framing updated for audit-driven prioritisation.

**Architecture:** A detail surface renders one row's fields as a series of (label, value) pairs inside a Region of `kind="detail"`. The Fragment composition uses Stack-of-Row to express the definition-list shape (Heading-level-4 for the label, Text for the value), keeping to the existing primitive vocabulary — no new primitive type. CSS rules under `.dz-region--kind-detail` shape the layout. The full rich-detail features (state-machine transitions, related groups, edit-in-place, audit history panels) stay on Jinja for surfaces with `render: fragment` until later plans extend the adapter.

**Tech Stack:** Python 3.12+, the typed Fragment substrate from Plans 1–5, Plan 7's `dazzle fragment-audit` for verification.

**Reference:** `docs/superpowers/plans/migration-roadmap.md` § Plan 8. Audit on `examples/simple_task` (and four siblings) reports VIEW as the third-largest blocker after CREATE/EDIT. Closing it unblocks 12 single-blocker VIEW surfaces; 3 surfaces remain blocked on `related_groups` (their double-blocker — to be closed in Plan 10).

**Predecessor (superseded):** `docs/superpowers/plans/2026-05-06-fragment-detail-mode.md` — Plan 6 draft; design ideas absorbed here, framing updated.

**Out of scope:** state-machine transitions, related_groups (Plan 10), edit-in-place via InlineEdit, audit history panels, persona-conditional field display. Detail surfaces with those features stay on Jinja until later plans.

---

## Stop condition

> **`dazzle fragment-audit` reports zero `unsupported_mode=VIEW` blockers across all five example apps.** 12 surfaces previously blocked solely on VIEW are now ready to flip; 3 surfaces remain blocked on `related_groups` (to be closed in Plan 10). Cumulative example coverage rises from 29/78 (37%) to 41/78 (53%).
>
> **Verification:** run the audit on each example after Plan 8 ships and compare ready-counts against the roadmap's predicted 53%.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle_http/runtime/renderers/fragment_adapter.py` | Modify | Add `_build_view(surface, ctx)` method; route SurfaceMode.VIEW to it |
| `src/dazzle_page/runtime/template_renderer.py` | Modify | Extend `render_surface(surface, ctx) -> str` to handle SurfaceMode.VIEW |
| `src/dazzle_page/runtime/page_routes.py` | Modify | `_build_dispatch_ctx` populates the right ctx shape for VIEW surfaces |
| `src/dazzle_page/runtime/static/css/components/fragment-primitives.css` | Modify | Add `.dz-region--kind-detail` definition-list-shaped rules |
| `src/dazzle_page/runtime/static/dist/dazzle.min.css` | Modify | Rebuilt bundle including new rules |
| `src/dazzle/render/fragment/coverage.py` | Modify | Remove `"view"` if added optimistically; otherwise no change — the audit re-detects automatically once the adapter accepts VIEW (single-source-of-truth: `_SUPPORTED_MODES`) |
| `tests/unit/runtime/test_fragment_surface_adapter.py` | Modify | Append tests for `_build_view` |
| `tests/unit/runtime/test_jinja_renderer_adapter.py` | Modify | Append a test confirming render_surface handles VIEW |
| `tests/unit/test_fragment_primitive_css.py` | Modify | Append `dz-region--kind-detail` to `_REQUIRED_CLASSES` |
| `tests/integration/test_simple_task_render_fragment.py` | Modify | Append a parity test for task_detail |
| `tests/unit/render/fragment/test_coverage.py` | Modify | Update `test_audit_marks_view_mode_as_blocked` semantics — VIEW is no longer blocked once Plan 8 ships |
| `examples/simple_task/dsl/app.dsl` | Modify | Add `render: fragment` to `task_detail` (the proving surface) |
| `CHANGELOG.md` | Modify | Note VIEW-mode closure |

13 files. ~7 tasks.

---

## Conventions

- **TDD throughout.** Failing test → minimal implementation → commit.
- **Lint after each task:** `ruff check src/ tests/ --fix && ruff format src/ tests/`
- **Type check:** `mypy src/dazzle/render --strict` and `mypy src/dazzle_http --ignore-missing-imports` clean.
- **Verify after Task 7:** `python -m dazzle.cli fragment-audit examples/simple_task` shows the audit-derived coverage delta.

---

## Task 1: FragmentSurfaceAdapter handles VIEW mode

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/fragment_adapter.py`
- Modify: `tests/unit/runtime/test_fragment_surface_adapter.py`

The current adapter raises `NotImplementedError` for VIEW. Add a `_build_view` method that produces a Surface with header + Region(kind="detail") containing a Stack of (label, value) Rows.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/runtime/test_fragment_surface_adapter.py`:

```python
from dazzle.render.fragment import (
    EmptyState as _EmptyState,
    Heading as _Heading,
    Region as _Region,
    Row as _Row,
    Stack as _Stack,
    Surface as _Surface,
    Text as _Text,
)


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
    assert isinstance(fragment, _Surface)
    assert isinstance(fragment.header, _Heading)
    assert fragment.header.body == "Task Detail"
    assert isinstance(fragment.body, _Region)
    assert fragment.body.kind == "detail"
    assert isinstance(fragment.body.body, _Stack)
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
    assert isinstance(first_row, _Row)
    label, value = first_row.children
    assert isinstance(label, _Heading)
    assert label.body == "Title"
    assert isinstance(value, _Text)
    assert value.body == "Hello"


def test_view_mode_handles_no_fields_gracefully() -> None:
    """A detail surface with no fields renders an EmptyState rather than
    an empty Stack (which would violate the Stack invariant)."""
    surface = SurfaceSpec(
        name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task"
    )
    ctx = {"fields": [], "region_name": "x_main"}
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment.body.body, _EmptyState)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v 2>&1 | tail -10
```

Expected: 4 existing PASS, 3 new FAIL with NotImplementedError for VIEW mode.

The Plan 3 test `test_unsupported_mode_raises` may have referenced VIEW; if so it now needs updating. Search:

```bash
grep -n "test_unsupported_mode_raises\|SurfaceMode.VIEW\|SurfaceMode.CREATE" tests/unit/runtime/test_fragment_surface_adapter.py
```

If the unsupported-mode test references VIEW, change it to `SurfaceMode.CREATE` (still NotImplementedError after this task).

- [ ] **Step 3: Implement `_build_view`**

In `src/dazzle_http/runtime/renderers/fragment_adapter.py`:

a) Update the dispatch in `build`:

```python
    def build(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Fragment:
        if surface.mode == SurfaceMode.LIST:
            return self._build_list(surface, ctx)
        if surface.mode == SurfaceMode.VIEW:
            return self._build_view(surface, ctx)
        raise NotImplementedError(
            f"FragmentSurfaceAdapter does not yet support mode {surface.mode.name!r}; "
            f"Plans 3+8 cover LIST and VIEW. CREATE/EDIT/CUSTOM land in Plan 9+."
        )
```

b) Add `_build_view` (after `_build_list`):

```python
    def _build_view(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> "Surface":
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

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v
```

Expected: 7 PASS (4 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/renderers/fragment_adapter.py tests/unit/runtime/test_fragment_surface_adapter.py
git commit -m "feat(render): FragmentSurfaceAdapter handles SurfaceMode.VIEW"
```

---

## Task 2: render_surface (Jinja adapter) handles VIEW mode

The minimal `render_surface(surface, ctx) -> str` in `template_renderer.py` (added in Plan 3 Task 1) currently only handles LIST. The parity test (Task 6) needs both renderers to produce HTML for the same VIEW-shape ctx.

**Files:**
- Modify: `src/dazzle_page/runtime/template_renderer.py`
- Modify: `tests/unit/runtime/test_jinja_renderer_adapter.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/runtime/test_jinja_renderer_adapter.py`:

```python
def test_jinja_renderer_renders_a_minimal_view_surface() -> None:
    """The minimal render_surface path supports VIEW mode."""
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

Expected: FAIL with NotImplementedError from `render_surface`.

- [ ] **Step 3: Extend render_surface**

In `src/dazzle_page/runtime/template_renderer.py`, find `render_surface`:

```bash
grep -n "def render_surface\|SurfaceMode.LIST\|NotImplementedError" src/dazzle_page/runtime/template_renderer.py | head -10
```

Locate the LIST-only branch and add a VIEW branch. The minimal path emits a `<dl>`-shaped HTML directly — just enough for parity testing. Production VIEW request paths stay on the legacy detail_view template.

Patch shape (adapt to the actual existing function structure):

```python
# Inside render_surface(surface, ctx):
#   ... existing LIST branch ...
    if surface.mode == SurfaceMode.VIEW:
        from html import escape as _escape

        title = surface.title or surface.name.replace("_", " ").title()
        fields = ctx.get("fields", [])
        if not fields:
            body_html = "<p>No data.</p>"
        else:
            items = "".join(
                f"<dt>{_escape(f['label'])}</dt><dd>{_escape(str(f['value']))}</dd>"
                for f in fields
            )
            body_html = f"<dl class='dz-detail-list'>{items}</dl>"
        return (
            f'<section class="dz-surface">'
            f'<header class="dz-surface__header"><h1>{_escape(title)}</h1></header>'
            f'<div class="dz-surface__body">'
            f'<section class="dz-region dz-region--kind-detail">{body_html}</section>'
            f'</div></section>'
        )
```

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
```

- [ ] **Step 2: Add VIEW shape extraction**

The Jinja path for VIEW receives a `detail` object (per the `detail_view.html` template) with structured fields. Extract those into a flat `[{key, label, value}, ...]` list.

The exact attribute names depend on the existing render-context shape. If the production-path `render_ctx` doesn't have a clean field-list shape because the detail page composes from many sources (audit history, related groups, transitions), keep the default-deny behaviour: return `None` and let the legacy path handle production VIEW for now. The Plan 8 stop condition only requires `simple_task.task_detail` (+ structurally similar surfaces) to flip — which is a simple field list.

Concrete shape to add inside `_build_dispatch_ctx` (or wherever the dispatch ctx is built):

```python
if surface.mode == SurfaceMode.VIEW:
    detail = render_ctx.get("detail")
    if detail is None:
        return None  # default-deny
    fields = []
    for section in getattr(detail, "sections", []):
        for f in getattr(section, "fields", []):
            fields.append({
                "key": getattr(f, "key", "") or getattr(f, "name", ""),
                "label": getattr(f, "label", "") or getattr(f, "key", ""),
                "value": getattr(f, "value", "") or "",
                "kind": getattr(f, "type", "text"),
            })
    if not fields:
        return None  # default-deny — nothing to render
    return {"fields": fields, "region_name": surface.name + "_main"}
```

- [ ] **Step 3: Run the integration smoke**

```bash
pytest tests/integration/test_simple_task_render_fragment.py -v 2>&1 | tail -10
```

Expected: existing tests pass. Parity test for VIEW comes in Task 6.

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
- Modify: `src/dazzle_page/runtime/static/dist/dazzle.min.css` (regenerated)

- [ ] **Step 1: Add the new class to the presence test**

Append `"dz-region--kind-detail"` to `_REQUIRED_CLASSES` in `tests/unit/test_fragment_primitive_css.py`:

```python
_REQUIRED_CLASSES: tuple[str, ...] = (
    # ... existing entries ...
    "dz-region--kind-detail",
)
```

```bash
pytest tests/unit/test_fragment_primitive_css.py -v 2>&1 | tail -5
```

Expected: previous PASS, new `dz-region--kind-detail` case FAILS.

- [ ] **Step 2: Add CSS rules**

In `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`, after the `.dz-region--kind-list` block, add:

```css
  /* Detail kind — definition-list-shaped layout. Each child Row
     renders as label (Heading level 4) + value (Text). The Stack
     wrapper provides the row separation; this rule provides the
     intra-row layout. */

  .dz-region--kind-detail {
    overflow-x: auto;
  }

  .dz-region--kind-detail .dz-stack {
    gap: var(--space-md);
  }

  .dz-region--kind-detail .dz-row {
    display: grid;
    grid-template-columns: minmax(8rem, 12rem) 1fr;
    gap: var(--space-md);
    align-items: baseline;
  }

  .dz-region--kind-detail .dz-row > .dz-heading {
    color: var(--colour-text-muted);
    font-weight: var(--weight-medium);
    text-align: end;
  }

  .dz-region--kind-detail .dz-row > .dz-text {
    color: var(--colour-text);
  }
```

- [ ] **Step 3: Verify presence test passes**

```bash
pytest tests/unit/test_fragment_primitive_css.py -v
```

Expected: all PASS.

- [ ] **Step 4: Rebuild dist**

```bash
python scripts/build_dist.py 2>&1 | tail -5
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

In `examples/simple_task/dsl/app.dsl` find `task_detail` (around line 275):

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

- [ ] **Step 3: Run the full unit suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add examples/simple_task/dsl/app.dsl
git commit -m "feat(simple_task): flip task_detail to render: fragment"
```

---

## Task 6: Parity test for VIEW mode

**Files:**
- Modify: `tests/integration/test_simple_task_render_fragment.py`

- [ ] **Step 1: Append the parity test**

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
    """VIEW mode: both renderers must include every field's label and value."""
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

- [ ] **Step 2: Run**

```bash
pytest tests/integration/test_simple_task_render_fragment.py -v
```

Expected: 5 PASS (3 existing list + 2 new detail).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_simple_task_render_fragment.py
git commit -m "test(render): parity test for VIEW mode (Jinja vs Fragment task_detail)"
```

---

## Task 7: Update audit capability + rerun + CHANGELOG

**Files:**
- Modify: `src/dazzle/render/fragment/coverage.py`
- Modify: `tests/unit/render/fragment/test_coverage.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update the audit capability matrix**

In `src/dazzle/render/fragment/coverage.py`, change `_SUPPORTED_MODES`:

```python
# Was:  _SUPPORTED_MODES: frozenset[str] = frozenset({"list"})
# Becomes:
_SUPPORTED_MODES: frozenset[str] = frozenset({"list", "view"})
```

- [ ] **Step 2: Update the coverage test that asserts VIEW is blocked**

In `tests/unit/render/fragment/test_coverage.py`, the test `test_audit_marks_view_mode_as_blocked` is now wrong — VIEW is supported. Either:
- (a) Rename to `test_audit_marks_create_mode_as_blocked` and assert on `SurfaceMode.CREATE` (still unsupported); or
- (b) Delete the test entirely (the audit's behaviour for unsupported modes is covered by `test_audit_aggregates_across_surfaces` which uses VIEW — also needs updating).

Pick (a). Rename and switch from `SurfaceMode.VIEW` to `SurfaceMode.CREATE`.

For `test_audit_aggregates_across_surfaces`, replace VIEW with CREATE in the assertion (still unsupported).

```bash
pytest tests/unit/render/fragment/test_coverage.py -v
```

Expected: all PASS.

- [ ] **Step 3: Re-run the audit on examples and verify the closure**

```bash
for app in simple_task contact_manager support_tickets ops_dashboard fieldtest_hub; do
  echo "=== $app ==="
  python -m dazzle.cli fragment-audit "examples/$app" 2>&1 | grep -E "Coverage:|Aggregated" | head -2
done
```

Expected: ready-counts increase. Cross-app aggregated `unsupported_mode=VIEW` should drop from 15 to 0. Three surfaces remain blocked on `unsupported_feature=related_groups` (their VIEW blocker is now cleared but related_groups isn't — to be closed in Plan 10).

Cumulative ready: should be ≥ 41 / 78.

- [ ] **Step 4: Run the full suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 5: Update CHANGELOG**

In `CHANGELOG.md`, add to `## [Unreleased]` under `### Added`:

```markdown
- **VIEW mode for FragmentSurfaceAdapter (Plan 8).** `mode: view`
  surfaces now flip cleanly to `render: fragment`. The adapter produces
  a Surface with a Region(kind="detail") containing a Stack of
  (Heading-label, Text-value) Rows. CSS rules under
  `.dz-region--kind-detail` lay out the definition-list-shaped pairs.
  `simple_task.task_detail` flipped as the proving surface. The
  `dazzle fragment-audit` capability matrix now lists `view` alongside
  `list` as a supported mode; cumulative example coverage rises from
  37% to ~53%.
```

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/render/fragment/coverage.py tests/unit/render/fragment/test_coverage.py CHANGELOG.md
git commit -m "feat(render): VIEW mode supported in audit; coverage 37% → 53%"
```

---

## Plan completion checklist

- [ ] `pytest tests/unit/runtime/ tests/integration/test_simple_task_render_fragment.py tests/unit/test_fragment_primitive_css.py tests/unit/render/fragment/test_coverage.py -v` — all pass.
- [ ] `pytest tests/ -m "not e2e"` — no regressions.
- [ ] `mypy src/dazzle/render --strict` — clean.
- [ ] `dazzle fragment-audit examples/simple_task` shows zero `unsupported_mode=VIEW` blockers.
- [ ] Cumulative example coverage at 41/78 = 53% (or close — within ±1 surface).
- [ ] `git status` clean.
- [ ] **Stop condition met:** Audit reports zero VIEW blockers across the five examples; 12 single-blocker surfaces are now ready; 3 surfaces still blocked on `related_groups` (Plan 10).
