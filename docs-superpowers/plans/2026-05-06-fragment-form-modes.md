# Fragment Form Modes (CREATE + EDIT) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `unsupported_mode=CREATE` and `unsupported_mode=EDIT` together — the audit's largest single closure (34 surfaces). One bundled plan because CREATE and EDIT share ~80% of infrastructure: form scaffolding, field-type-to-widget mapping, Submit button, action URL, validation error display. Splitting into two plans wastes the shared work.

**Architecture:** Add `_build_form(surface, ctx, *, mode)` to FragmentSurfaceAdapter — handles both CREATE and EDIT, branching only on initial-value population (empty for CREATE, row data for EDIT) and Submit label / action URL semantics. Composition uses Plan 1's existing form primitives (`FormStack`, `Field`, `Combobox`, `Submit`) — no new typed primitive needed. Field-type-to-widget mapping translates IR `FieldTypeKind` (STR, TEXT, EMAIL, INT, DECIMAL, BOOL, DATE, DATETIME, ENUM) into the appropriate `Field.kind` or `Combobox` choice. Out-of-scope IR types (REF, UUID, JSON, FILE) become `unsupported_field_type` blockers in the audit, surfacing for a later closure.

**Tech Stack:** Python 3.12+, the typed Fragment substrate from Plans 1-5, Plan 7's `dazzle fragment-audit` for verification.

**Reference:** `docs/superpowers/plans/migration-roadmap.md` § Plan 9. Audit reports CREATE+EDIT each at 17 occurrences across the 5 example apps; closing both moves cumulative coverage from 41/78 (53%) to 75/78 (96%) — the largest single jump available.

**Out of scope:**
- Validation error display (Plan 1's primitives don't include an Error type yet — add a small primitive later if needed; for MVP, errors flow through the existing Jinja error-display path on form-post failure)
- REF field rendering (FK-aware Combobox loading via htmx — separate plan)
- File upload widgets (`FILE` field type — separate plan)
- Cancel buttons / confirm-before-leave (UX polish; later)
- Multi-step wizards (`layout: wizard` surfaces — out of scope; only `layout: single_page` flips this plan)

---

## Stop condition

> **`dazzle fragment-audit` reports zero `unsupported_mode=CREATE` and zero `unsupported_mode=EDIT` blockers across all five example apps.** Surfaces flipped to `render: fragment` for CREATE/EDIT modes render forms with type-aware widgets and submit to the right action URL. `simple_task.task_create` and `simple_task.task_edit` flipped as proving cases. Cumulative example coverage rises from 41/78 (53%) to 75/78 (96%).
>
> **Verification:** `dazzle fragment-audit` aggregated counts after Plan 9 should show: `0 CREATE + 0 EDIT + 3 related_groups` (Plan 10's remaining work). 3 surfaces blocked on `unsupported_field_type=ref` are an *expected* new finding — the audit will flag REF fields once CREATE/EDIT support exists, since the form path can't render REF without FK-aware widgets. Plan 11 closes that.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle_http/runtime/renderers/fragment_adapter.py` | Modify | Add `_build_form(surface, ctx, *, mode)`; route CREATE+EDIT to it; add `_field_to_primitive` helper for type→widget mapping |
| `src/dazzle_page/runtime/template_renderer.py` | Modify | Extend `render_surface` minimal path to handle CREATE/EDIT (HTML form for parity testing) |
| `src/dazzle_page/runtime/page_routes.py` | Modify | `_build_dispatch_ctx` extracts form ctx (fields, action URL, method, submit label) |
| `src/dazzle_page/runtime/static/css/components/fragment-primitives.css` | Modify | Add `.dz-region--kind-form` rules + `.dz-form-stack`, `.dz-field`, `.dz-combobox`, `.dz-submit` styling |
| `src/dazzle/render/fragment/coverage.py` | Modify | Capability matrix: add `create`, `edit` to `_SUPPORTED_MODES`; add `_UNSUPPORTED_FIELD_TYPES = {"ref", "uuid", "json", "file"}` |
| `tests/unit/runtime/test_fragment_surface_adapter.py` | Modify | Append CREATE + EDIT mode tests |
| `tests/unit/runtime/test_jinja_renderer_adapter.py` | Modify | Append CREATE + EDIT minimal-path tests |
| `tests/unit/test_fragment_primitive_css.py` | Modify | Append form-related classes to `_REQUIRED_CLASSES` |
| `tests/unit/render/fragment/test_coverage.py` | Modify | Update tests for new capability matrix |
| `tests/integration/test_simple_task_render_fragment.py` | Modify | Append CREATE/EDIT parity tests |
| `tests/integration/test_render_default_unchanged.py` | Modify | Update expected_flipped to include task_create + task_edit |
| `examples/simple_task/dsl/app.dsl` | Modify | Flip `task_create` + `task_edit` (and possibly `comment_create` + `comment_edit`) to `render: fragment` |
| `CHANGELOG.md` | Modify | Note CREATE+EDIT closure and the audit's new REF blocker |

13 files. ~7 tasks (combining adapter+helper, JS + CSS, etc.).

---

## Conventions

- **TDD throughout.** Failing test → minimal implementation → commit.
- **Lint after each task:** `ruff check src/ tests/ --fix && ruff format src/ tests/`
- **Type check:** `mypy src/dazzle/render --strict` and `mypy src/dazzle_http --ignore-missing-imports` clean.
- **Verify after Task 7:** `python -m dazzle.cli fragment-audit examples/simple_task` shows zero CREATE/EDIT blockers; cumulative coverage hit 96%.

---

## Task 1: FragmentSurfaceAdapter handles CREATE + EDIT

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/fragment_adapter.py`
- Modify: `tests/unit/runtime/test_fragment_surface_adapter.py`

The bundled adapter method handles both modes. Internally branches only on initial-value source and Submit label/action.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/runtime/test_fragment_surface_adapter.py`:

```python
def test_create_mode_produces_surface_with_form_region() -> None:
    """Plan 9 — CREATE mode renders an empty form."""
    from dazzle.render.fragment import (
        Field, FormStack, Heading, Region, Submit, Surface,
    )

    surface = SurfaceSpec(
        name="task_create",
        title="New Task",
        mode=SurfaceMode.CREATE,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"name": "title", "label": "Title", "kind": "str", "required": True, "value": ""},
            {"name": "status", "label": "Status", "kind": "enum", "required": True, "value": "",
             "options": [("open", "Open"), ("done", "Done")]},
        ],
        "action": "/api/Task",
        "method": "POST",
        "submit_label": "Create",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.header, Heading)
    assert fragment.header.body == "New Task"
    region = fragment.body
    assert isinstance(region, Region)
    assert region.kind == "form"
    form = region.body
    assert isinstance(form, FormStack)
    assert str(form.action) == "/api/Task"
    assert form.method == "POST"
    # First field is a typed Field; second is a Combobox (because kind=enum)
    assert isinstance(form.fields[0], Field)
    assert form.fields[0].name == "title"
    assert form.fields[0].required is True
    # Submit is part of the FormStack
    assert isinstance(form.submit, Submit)
    assert form.submit.label == "Create"


def test_edit_mode_pre_populates_field_values() -> None:
    """Plan 9 — EDIT mode populates initial_value from the row data."""
    surface = SurfaceSpec(
        name="task_edit",
        title="Edit Task",
        mode=SurfaceMode.EDIT,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"name": "title", "label": "Title", "kind": "str", "required": True,
             "value": "Buy milk"},
        ],
        "action": "/api/Task/42",
        "method": "POST",
        "submit_label": "Save",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    form = fragment.body.body
    assert form.fields[0].initial_value == "Buy milk"
    assert form.submit.label == "Save"


def test_form_field_type_mapping() -> None:
    """Plan 9 — IR FieldTypeKind values map to Field.kind / Combobox correctly."""
    from dazzle.render.fragment import Combobox, Field

    cases = [
        ({"name": "title", "kind": "str"}, Field, "text"),
        ({"name": "body", "kind": "text"}, Field, "textarea"),
        ({"name": "email", "kind": "email"}, Field, "email"),
        ({"name": "count", "kind": "int"}, Field, "number"),
        ({"name": "amount", "kind": "decimal"}, Field, "number"),
        ({"name": "active", "kind": "bool"}, Field, "checkbox"),
        ({"name": "due", "kind": "date"}, Field, "date"),
        ({"name": "at", "kind": "datetime"}, Field, "datetime-local"),
    ]
    for field_dict, expected_type, expected_kind in cases:
        full = {"label": field_dict["name"].title(), "required": False, "value": "", **field_dict}
        ctx = {
            "fields": [full],
            "action": "/x",
            "method": "POST",
            "submit_label": "Save",
        }
        surface = SurfaceSpec(name="x", mode=SurfaceMode.CREATE, entity_ref="X")
        fragment = FragmentSurfaceAdapter().build(surface, ctx)
        emitted = fragment.body.body.fields[0]
        assert isinstance(emitted, expected_type), (
            f"{field_dict['kind']!r} → expected {expected_type.__name__}, got {type(emitted).__name__}"
        )
        if expected_type is Field:
            assert emitted.kind == expected_kind


def test_enum_field_becomes_combobox() -> None:
    """Plan 9 — enum fields render as Combobox, not Field."""
    from dazzle.render.fragment import Combobox

    ctx = {
        "fields": [
            {"name": "status", "label": "Status", "kind": "enum", "required": True, "value": "",
             "options": [("open", "Open"), ("done", "Done")]},
        ],
        "action": "/x",
        "method": "POST",
        "submit_label": "Save",
    }
    surface = SurfaceSpec(name="x", mode=SurfaceMode.CREATE, entity_ref="X")
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    emitted = fragment.body.body.fields[0]
    assert isinstance(emitted, Combobox)
    assert emitted.options == (("open", "Open"), ("done", "Done"))
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v 2>&1 | tail -10
```

Expected: existing tests PASS; new tests FAIL (NotImplementedError for CREATE/EDIT). Also: `test_unsupported_mode_raises` may need updating again — change it to use `SurfaceMode.CUSTOM` since CREATE/EDIT are about to be supported.

- [ ] **Step 3: Implement `_build_form` + helper**

In `src/dazzle_http/runtime/renderers/fragment_adapter.py`, update imports and add the form path:

```python
# Update the imports to include FormStack/Field/Combobox/Submit:
from dazzle.render.fragment import (
    Combobox,
    EmptyState,
    Field,
    FormStack,
    Fragment,
    Heading,
    Region,
    Row,
    Stack,
    Submit,
    Surface,
    Table,
    Text,
    URL,
)
```

Update `build`:

```python
    def build(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Fragment:
        if surface.mode == SurfaceMode.LIST:
            return self._build_list(surface, ctx)
        if surface.mode == SurfaceMode.VIEW:
            return self._build_view(surface, ctx)
        if surface.mode in (SurfaceMode.CREATE, SurfaceMode.EDIT):
            return self._build_form(surface, ctx, mode=surface.mode)
        raise NotImplementedError(
            f"FragmentSurfaceAdapter does not yet support mode {surface.mode.name!r}; "
            f"Plans 3+8+9 cover LIST, VIEW, CREATE, EDIT. CUSTOM lands later."
        )
```

Add `_build_form` after `_build_view`:

```python
    def _build_form(
        self,
        surface: SurfaceSpec,
        ctx: dict[str, Any],
        *,
        mode: SurfaceMode,
    ) -> Surface:
        """CREATE/EDIT form surface — FormStack with type-aware widgets.

        Both modes share infrastructure; the only differences are:
        - initial_value (empty in CREATE, from row in EDIT — both come
          from ctx["fields"][i]["value"], so the adapter is uniform)
        - Submit label and action URL (carried via ctx["submit_label"]
          and ctx["action"])
        """
        title = surface.title or surface.name.replace("_", " ").title()
        fields_in: list[dict[str, Any]] = ctx.get("fields", [])
        action = ctx.get("action", "")
        method = ctx.get("method", "POST")
        submit_label = ctx.get("submit_label", "Save" if mode == SurfaceMode.EDIT else "Create")

        body: Fragment
        if not fields_in:
            body = EmptyState(
                title="No fields",
                description="This form has no inputs.",
            )
        else:
            primitives = tuple(_field_to_primitive(f) for f in fields_in)
            # Cast to FormStack only if we have at least one field
            form = FormStack(
                action=URL(action) if action else URL("/"),
                fields=primitives,
                method=method if method in ("GET", "POST") else "POST",
                submit=Submit(label=submit_label),
            )
            body = form

        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="form", body=body),
        )
```

Add `_field_to_primitive` at module level (after `_format_cell`):

```python
def _field_to_primitive(field_dict: dict[str, Any]) -> "Field | Combobox":
    """Map a field-shape dict to the right Fragment form primitive.

    Plan 9 covers: str, text, email, int, decimal, float, money, bool,
    date, datetime, enum. Out-of-scope kinds (ref, uuid, json, file)
    fall through to a plain text Field — the audit flags them as
    unsupported_field_type so callers see the gap.
    """
    name = str(field_dict.get("name", ""))
    label = str(field_dict.get("label", name))
    required = bool(field_dict.get("required", False))
    placeholder = str(field_dict.get("placeholder", ""))
    initial_value = str(field_dict.get("value", "") or "")
    kind = str(field_dict.get("kind", "str")).lower()

    if kind == "enum":
        options = tuple(
            (str(v), str(label_)) for v, label_ in field_dict.get("options", [])
        )
        if not options:
            options = (("", ""),)  # Combobox requires at least one option
        return Combobox(
            name=name,
            label=label,
            options=options,
            required=required,
            initial_value=initial_value,
        )

    # Map IR field-type-kind → Field.kind
    field_kind_map: dict[str, str] = {
        "str": "text",
        "text": "textarea",
        "email": "email",
        "int": "number",
        "decimal": "number",
        "float": "number",
        "money": "number",
        "bool": "checkbox",
        "date": "date",
        "datetime": "datetime-local",
        "url": "url",
    }
    field_kind = field_kind_map.get(kind, "text")
    return Field(
        name=name,
        label=label,
        kind=field_kind,  # type: ignore[arg-type]
        required=required,
        placeholder=placeholder,
        initial_value=initial_value,
    )
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v
```

Expected: all PASS. Update `test_unsupported_mode_raises` if it was using CREATE — change to `SurfaceMode.CUSTOM`.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/renderers/fragment_adapter.py tests/unit/runtime/test_fragment_surface_adapter.py
git commit -m "feat(render): FragmentSurfaceAdapter handles CREATE+EDIT (form modes)"
```

---

## Task 2: render_surface (Jinja adapter) handles CREATE + EDIT minimal path

**Files:**
- Modify: `src/dazzle_page/runtime/template_renderer.py`
- Modify: `tests/unit/runtime/test_jinja_renderer_adapter.py`

For parity testing only. Production CREATE/EDIT request paths stay on `form.html`.

- [ ] **Step 1: Write failing test**

Append to `tests/unit/runtime/test_jinja_renderer_adapter.py`:

```python
def test_jinja_renderer_renders_minimal_create_form() -> None:
    """Plan 9 — render_surface emits an HTML form for CREATE mode."""
    surface = SurfaceSpec(
        name="task_create",
        title="New Task",
        mode=SurfaceMode.CREATE,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"name": "title", "label": "Title", "kind": "str", "required": True, "value": ""},
        ],
        "action": "/api/Task",
        "method": "POST",
        "submit_label": "Create",
    }
    html = JinjaRenderer().render(surface, ctx)
    assert isinstance(html, str)
    assert "<form" in html
    assert 'action="/api/Task"' in html
    assert 'method="POST"' in html
    assert "Title" in html
    assert "Create" in html  # Submit label


def test_jinja_renderer_renders_minimal_edit_form() -> None:
    """Plan 9 — render_surface emits an HTML form for EDIT mode with values."""
    surface = SurfaceSpec(
        name="task_edit",
        title="Edit Task",
        mode=SurfaceMode.EDIT,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"name": "title", "label": "Title", "kind": "str", "required": True,
             "value": "Buy milk"},
        ],
        "action": "/api/Task/42",
        "method": "POST",
        "submit_label": "Save",
    }
    html = JinjaRenderer().render(surface, ctx)
    assert "Buy milk" in html
    assert 'action="/api/Task/42"' in html
    assert "Save" in html
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_jinja_renderer_adapter.py -v 2>&1 | tail -5
```

Expected: 2 new FAIL with NotImplementedError.

- [ ] **Step 3: Extend render_surface**

In `src/dazzle_page/runtime/template_renderer.py`, find the existing mode dispatch in `render_surface` and add CREATE/EDIT before the LIST-only fallback:

```python
    if mode in (SurfaceMode.CREATE, SurfaceMode.EDIT):
        from html import escape as _escape

        title = (
            getattr(surface, "title", None)
            or getattr(surface, "name", "").replace("_", " ").title()
        )
        fields = ctx.get("fields") or []
        action = ctx.get("action", "")
        method = ctx.get("method", "POST")
        submit_label = ctx.get(
            "submit_label",
            "Save" if mode == SurfaceMode.EDIT else "Create",
        )
        inputs = []
        for f in fields:
            name = _escape(str(f.get("name", "")))
            label = _escape(str(f.get("label", name)))
            value = _escape(str(f.get("value", "") or ""))
            req = " required" if f.get("required") else ""
            kind = str(f.get("kind", "str")).lower()
            if kind == "enum":
                opts = "".join(
                    f'<option value="{_escape(str(v))}"'
                    f'{" selected" if str(v) == str(f.get("value", "")) else ""}>'
                    f"{_escape(str(label_))}</option>"
                    for v, label_ in f.get("options", [])
                )
                inputs.append(
                    f"<label>{label}<select name=\"{name}\"{req}>{opts}</select></label>"
                )
            elif kind == "text":
                inputs.append(
                    f"<label>{label}<textarea name=\"{name}\"{req}>{value}</textarea></label>"
                )
            elif kind == "bool":
                checked = " checked" if value == "true" else ""
                inputs.append(
                    f'<label>{label}<input type="checkbox" name="{name}"{checked}{req}></label>'
                )
            else:
                input_kind = {
                    "str": "text",
                    "email": "email",
                    "int": "number",
                    "decimal": "number",
                    "float": "number",
                    "money": "number",
                    "date": "date",
                    "datetime": "datetime-local",
                    "url": "url",
                }.get(kind, "text")
                inputs.append(
                    f'<label>{label}<input type="{input_kind}" name="{name}" '
                    f'value="{value}"{req}></label>'
                )
        body_html = (
            f'<form class="dz-form-stack" action="{_escape(str(action))}" '
            f'method="{_escape(str(method))}">'
            + "".join(inputs)
            + f'<button type="submit">{_escape(str(submit_label))}</button>'
            + "</form>"
        )
        return (
            f'<section class="dz-surface">'
            f'<header class="dz-surface__header"><h1>{_escape(str(title))}</h1></header>'
            f'<div class="dz-surface__body">'
            f'<section class="dz-region dz-region--kind-form">{body_html}</section>'
            f"</div></section>"
        )
```

Add this branch BEFORE the existing `if mode != SurfaceMode.LIST: raise` block. Then update the error message to mention CREATE/EDIT are now supported.

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_jinja_renderer_adapter.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_page/runtime/template_renderer.py tests/unit/runtime/test_jinja_renderer_adapter.py
git commit -m "feat(render): render_surface handles CREATE+EDIT for parity testing"
```

---

## Task 3: page_routes builds form ctx for CREATE/EDIT surfaces

**Files:**
- Modify: `src/dazzle_page/runtime/page_routes.py`

The existing `_build_dispatch_ctx` handles LIST (`table`) and VIEW (`detail`) shapes. Add a `form` branch for CREATE/EDIT.

- [ ] **Step 1: Locate the form context shape**

```bash
grep -rn "form_context\|FormContext\|render_ctx.form\|class FormContext" src/dazzle_page/runtime/ 2>/dev/null | head -5
```

Find the existing form-rendering context. The Jinja form template gets its data from somewhere; that's the structure to translate.

- [ ] **Step 2: Add form branch to _build_dispatch_ctx**

In `src/dazzle_page/runtime/page_routes.py`, in `_build_dispatch_ctx`, after the `detail` branch:

```python
    form = getattr(render_ctx, "form", None)
    if form is not None:
        fields_out: list[dict[str, Any]] = []
        for field in getattr(form, "fields", []) or []:
            kind = getattr(field, "type", None) or getattr(field, "kind", "str")
            entry = {
                "name": getattr(field, "name", ""),
                "label": getattr(field, "label", "") or getattr(field, "name", ""),
                "kind": str(kind).lower(),
                "required": bool(getattr(field, "required", False)),
                "value": getattr(field, "value", "") or "",
                "placeholder": getattr(field, "placeholder", "") or "",
            }
            options = getattr(field, "options", None)
            if options:
                entry["options"] = [
                    (str(getattr(o, "value", o)), str(getattr(o, "label", o)))
                    for o in options
                ]
            fields_out.append(entry)
        return {
            "fields": fields_out,
            "action": getattr(form, "action", "") or "",
            "method": getattr(form, "method", "POST") or "POST",
            "submit_label": getattr(form, "submit_label", "")
            or ("Save" if getattr(form, "is_edit", False) else "Create"),
        }
```

Update the `_maybe_dispatch_inner_html` precondition to include `form`:

```python
    has_table = getattr(render_ctx, "table", None) is not None
    has_detail = getattr(render_ctx, "detail", None) is not None
    has_form = getattr(render_ctx, "form", None) is not None
    if not (has_table or has_detail or has_form):
        return None
```

- [ ] **Step 3: Run targeted suite**

```bash
pytest tests/ -m "not e2e" -k "render or dispatch or form" -q 2>&1 | tail -5
```

Expected: no regressions.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_page/runtime/page_routes.py
git commit -m "feat(runtime): _build_dispatch_ctx handles CREATE/EDIT (form context)"
```

---

## Task 4: CSS for `.dz-region--kind-form` + form primitives

**Files:**
- Modify: `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`
- Modify: `tests/unit/test_fragment_primitive_css.py`
- Modify: `src/dazzle_page/runtime/static/dist/dazzle.min.css` (regenerated)

- [ ] **Step 1: Add new classes to the presence test**

Append to `_REQUIRED_CLASSES` in `tests/unit/test_fragment_primitive_css.py`:

```python
    # Plan 9 — form-mode region + form primitives
    "dz-region--kind-form",
    "dz-form-stack",
    "dz-field",
    "dz-combobox",
    "dz-submit",
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_fragment_primitive_css.py -v 2>&1 | tail -10
```

Expected: 5 new FAILs.

- [ ] **Step 3: Add CSS rules**

In `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`, append before the closing `} /* @layer components */`:

```css
  /* Form kind — vertical stack of fields with label-above-input layout. */

  .dz-region--kind-form {
    /* Region container; FormStack inside provides actual layout. */
  }

  .dz-form-stack {
    display: flex;
    flex-direction: column;
    gap: var(--space-md);
    max-width: 40rem;
  }

  .dz-field {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
  }

  .dz-field__label {
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    color: var(--colour-text);
  }

  .dz-field__input {
    padding: var(--space-sm) var(--space-md);
    font-size: var(--text-base);
    color: var(--colour-text);
    background: var(--colour-surface);
    border: 1px solid var(--colour-border);
    border-radius: var(--radius-sm);
  }

  .dz-field__input:focus {
    outline: 2px solid var(--colour-accent);
    outline-offset: 1px;
  }

  .dz-combobox {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
  }

  .dz-combobox__label {
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    color: var(--colour-text);
  }

  .dz-combobox__select {
    padding: var(--space-sm) var(--space-md);
    font-size: var(--text-base);
    color: var(--colour-text);
    background: var(--colour-surface);
    border: 1px solid var(--colour-border);
    border-radius: var(--radius-sm);
  }

  .dz-submit {
    align-self: flex-start;
    padding: var(--space-sm) var(--space-lg);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
    color: var(--colour-brand-contrast);
    background: var(--colour-brand);
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
  }

  .dz-submit--variant-secondary {
    background: var(--colour-surface);
    color: var(--colour-text);
    border: 1px solid var(--colour-border);
  }

  .dz-submit--variant-danger {
    background: var(--colour-danger);
    color: var(--colour-brand-contrast);
  }
```

- [ ] **Step 4: Verify presence test passes**

```bash
pytest tests/unit/test_fragment_primitive_css.py -v
```

Expected: all PASS (10 existing + new classes).

- [ ] **Step 5: Rebuild dist**

```bash
python scripts/build_dist.py 2>&1 | tail -3
grep -c "dz-region--kind-form\|dz-form-stack" src/dazzle_page/runtime/static/dist/dazzle.min.css
```

Expected: ≥ 2.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_page/runtime/static/css/components/fragment-primitives.css tests/unit/test_fragment_primitive_css.py src/dazzle_page/runtime/static/dist/
git commit -m "feat(ui): CSS for form-mode region + form primitives"
```

---

## Task 5: Update audit capability matrix

**Files:**
- Modify: `src/dazzle/render/fragment/coverage.py`
- Modify: `tests/unit/render/fragment/test_coverage.py`

The audit's `_SUPPORTED_MODES` becomes `{list, view, create, edit}`. Add `_UNSUPPORTED_FIELD_TYPES = {ref, uuid, json, file}` so REF fields surface as a new blocker.

- [ ] **Step 1: Update the matrix**

In `src/dazzle/render/fragment/coverage.py`:

```python
# Was:  _SUPPORTED_MODES: frozenset[str] = frozenset({"list", "view"})
# Becomes:
_SUPPORTED_MODES: frozenset[str] = frozenset({"list", "view", "create", "edit"})

# Was:  _UNSUPPORTED_FIELD_TYPES: frozenset[str] = frozenset()
# Becomes:
_UNSUPPORTED_FIELD_TYPES: frozenset[str] = frozenset({"ref", "uuid", "json", "file"})
```

The `_audit_surface` walks each section's fields; with the new field-type set populated, surfaces with REF or UUID or JSON or FILE field types now show up as `unsupported_field_type` blockers. This is *expected* — once forms render, REF fields become a meaningful gap.

- [ ] **Step 2: Update affected tests**

In `tests/unit/render/fragment/test_coverage.py`, `test_audit_marks_create_mode_as_blocked` is now wrong (CREATE is supported). Rename and switch:

```python
def test_audit_marks_custom_mode_as_blocked() -> None:
    """Plan 9 added CREATE+EDIT; CUSTOM remains unsupported."""
    surface = SurfaceSpec(name="x", mode=SurfaceMode.CUSTOM)
    report = audit_appspec(_make_appspec([surface]))
    assert report.ready_count == 0
    assert report.blocked_count == 1
    blockers = report.surfaces[0].blockers
    assert any(
        b.kind.value == "unsupported_mode" and b.detail == "CUSTOM" for b in blockers
    )
```

Update `test_audit_aggregates_across_surfaces` to use CUSTOM instead of CREATE.

Update `test_coverage_report_to_text_basic_shape` and `test_coverage_report_to_json_shape` to use CUSTOM.

```bash
pytest tests/unit/render/fragment/test_coverage.py -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/render/fragment/coverage.py tests/unit/render/fragment/test_coverage.py
git commit -m "feat(render): audit recognises CREATE+EDIT support; flags REF/UUID/JSON/FILE field types"
```

---

## Task 6: Flip simple_task surfaces + parity tests

**Files:**
- Modify: `examples/simple_task/dsl/app.dsl`
- Modify: `tests/integration/test_simple_task_render_fragment.py`
- Modify: `tests/integration/test_render_default_unchanged.py`

- [ ] **Step 1: Flip surfaces in DSL**

Find each create/edit surface in `examples/simple_task/dsl/app.dsl` and add `render: fragment`. Specifically `task_create` and `task_edit`. (Other apps' create/edit surfaces stay unflipped for now — Plan 9's stop condition is the audit cumulative count, not flipping every surface.)

```bash
grep -n "surface task_create\|surface task_edit\|mode: create\|mode: edit" examples/simple_task/dsl/app.dsl
```

For each (e.g. `task_create`, `task_edit`), add `render: fragment` after the `mode:` line.

CAUTION: many simple_task entities have `ref` fields (e.g. `assigned_to: ref User`). Those surfaces will partially work via Fragment — non-ref fields render correctly, but ref fields will render as plain text inputs (the `_field_to_primitive` fallback). That's acceptable for the proving case; production users won't flip these surfaces because the audit will report the ref blocker.

- [ ] **Step 2: Validate the DSL**

```bash
cd examples/simple_task && dazzle validate 2>&1 | tail -3 ; cd -
```

Expected: success.

- [ ] **Step 3: Append parity tests**

Append to `tests/integration/test_simple_task_render_fragment.py`:

```python
def _form_ctx(*, value: str = "") -> dict:
    """Deterministic form-mode context."""
    return {
        "fields": [
            {"name": "title", "label": "Title", "kind": "str", "required": True, "value": value},
            {"name": "status", "label": "Status", "kind": "enum", "required": True,
             "value": value, "options": [("open", "Open"), ("done", "Done")]},
        ],
        "action": "/api/Task" if not value else "/api/Task/42",
        "method": "POST",
        "submit_label": "Create" if not value else "Save",
    }


def test_jinja_and_fragment_both_render_create_form() -> None:
    """Plan 9 — CREATE mode parity."""
    services = _make_services()

    jinja_surface = SurfaceSpec(
        name="task_create", title="New Task", mode=SurfaceMode.CREATE, entity_ref="Task",
    )
    fragment_surface = SurfaceSpec(
        name="task_create", title="New Task", mode=SurfaceMode.CREATE, entity_ref="Task",
        render="fragment",
    )

    ctx = _form_ctx()
    jinja_html = dispatch_render(jinja_surface, ctx=ctx, services=services)
    fragment_html = dispatch_render(fragment_surface, ctx=ctx, services=services)

    for renderer_name, html in [("jinja", jinja_html), ("fragment", fragment_html)]:
        assert "<form" in html, f"{renderer_name}: missing <form>"
        assert 'action="/api/Task"' in html, f"{renderer_name}: missing action"
        assert "Title" in html, f"{renderer_name}: missing Title label"
        assert "Status" in html, f"{renderer_name}: missing Status label"
        assert "Create" in html, f"{renderer_name}: missing submit label"


def test_jinja_and_fragment_both_render_edit_form_with_values() -> None:
    """Plan 9 — EDIT mode populates initial values."""
    services = _make_services()

    fragment_surface = SurfaceSpec(
        name="task_edit", title="Edit Task", mode=SurfaceMode.EDIT, entity_ref="Task",
        render="fragment",
    )
    ctx = _form_ctx(value="Buy milk")
    html = dispatch_render(fragment_surface, ctx=ctx, services=services)
    assert "Buy milk" in html
    assert 'action="/api/Task/42"' in html
    assert "Save" in html
```

- [ ] **Step 4: Update render-default-unchanged test**

In `tests/integration/test_render_default_unchanged.py`, expand `expected_flipped`:

```python
    expected_flipped = {"task_list", "task_detail", "task_create", "task_edit"}
```

- [ ] **Step 5: Run all integration tests**

```bash
pytest tests/integration/test_simple_task_render_fragment.py tests/integration/test_render_default_unchanged.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add examples/simple_task/dsl/app.dsl tests/integration/test_simple_task_render_fragment.py tests/integration/test_render_default_unchanged.py
git commit -m "feat(simple_task): flip task_create + task_edit; add CREATE/EDIT parity tests"
```

---

## Task 7: Verify closure + CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run audit on all examples**

```bash
for app in simple_task contact_manager support_tickets ops_dashboard fieldtest_hub; do
  result=$(python -m dazzle.cli fragment-audit "examples/$app" 2>&1 | grep "^Coverage:" | head -1)
  echo "$app : $result"
done
echo ""
for app in simple_task contact_manager support_tickets ops_dashboard fieldtest_hub; do
  python -m dazzle.cli fragment-audit "examples/$app" 2>&1 | grep -E "^\s+[0-9]+\s+unsupported"
done | awk '{count[$2] += $1} END {for (k in count) print count[k], k}' | sort -rn
```

Expected: CREATE+EDIT both at 0; cumulative ready ≥ 75/78. New finding: `unsupported_field_type=ref` count appears (some number — could be 6-12 depending on which surfaces have ref fields). That's the *expected new blocker* — Plan 11 closes it.

- [ ] **Step 2: Run full unit suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 3: Update CHANGELOG**

Add to `## [Unreleased]` under `### Added`:

```markdown
- **Form modes (CREATE + EDIT) for FragmentSurfaceAdapter (Plan 9).**
  Bundled closure of the audit's two largest blockers (17 surfaces each
  across the 5 example apps, 34 in total). The adapter produces a
  Surface with Region(kind="form") containing a FormStack of type-aware
  Fields (str/text/email/int/decimal/bool/date/datetime → Field with
  appropriate kind) and Comboboxes (enum). simple_task.task_create and
  task_edit flipped as proving cases. CSS rules under
  `.dz-region--kind-form` + form-primitive styling. Cumulative example
  coverage rises from 53% to ~96%. New audit finding:
  `unsupported_field_type=ref` (and uuid/json/file) surfaces as the
  next-priority blocker — Plan 11 will close ref-field rendering.
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note Plan 9 — CREATE+EDIT closure (53% → 96%)"
```

---

## Plan completion checklist

- [ ] `pytest tests/ -m "not e2e"` — all pass.
- [ ] `mypy src/dazzle/render --strict` — clean.
- [ ] `dazzle fragment-audit examples/simple_task` shows 0 CREATE + 0 EDIT blockers.
- [ ] Cumulative example coverage at 75/78 = 96% (or close — within ±2 surfaces, depending on REF-field surface counts).
- [ ] `git status` clean.
- [ ] **Stop condition met:** audit reports zero CREATE/EDIT blockers; new REF blocker is expected.

---

## Self-Review

**Spec coverage:**
- Plan 5 carry-forward #2 (CREATE+EDIT closure) → Tasks 1-7.
- Audit's 17+17 CREATE/EDIT counts → close in one bundled plan.

**Placeholder scan:**
- Field-type-to-widget mapping is fully enumerated in `_field_to_primitive`. Out-of-scope kinds fall through to `text` (with audit-flag).
- `_field_to_primitive` returns `Field | Combobox` — both are real Fragment primitive types from Plan 1.

**Type consistency:**
- `_build_form(surface, ctx, *, mode)` consistent in Tasks 1, 3, 6.
- `fields` ctx key carries `[{name, label, kind, required, value, ...}]` shape consistent across Tasks 1, 2, 3, 6.
- `action`, `method`, `submit_label` ctx keys consistent.

**Scope check:**
- Plan covers exactly CREATE+EDIT closure. REF/UUID/JSON/FILE field types deliberately deferred to Plan 11 (audit will surface them as next-priority).
- 7 tasks. Bundled because CREATE+EDIT share form scaffolding; splitting wastes shared work.
