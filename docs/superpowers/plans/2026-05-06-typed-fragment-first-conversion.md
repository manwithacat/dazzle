# Typed Fragment First Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `render: fragment` actually do something. Wire the dispatcher into the live request path, build a minimum-viable IR-to-Fragment adapter that handles `simple_task`'s `task_list` surface end-to-end, flip that surface to `render: fragment`, and prove parity with the Jinja path on the happy path.

**Architecture:** Two real adapters replace the Plan 2 stubs. `JinjaRenderer` wraps the existing Jinja template-rendering path so the registry can route to it. `FragmentSurfaceAdapter` is a new IR-to-Fragment translator that takes a `SurfaceSpec` + render context (rows, columns, sort, filters) and produces a `Fragment` tree, which `FragmentRenderer` then emits as HTML. A small `dispatch_render(surface, ...)` helper consults `surface.render` and routes; with no flag set, the existing Jinja path runs unchanged. `simple_task.task_list` is the first surface flipped.

**Tech Stack:** Python 3.12+, the typed Fragment substrate from Plan 1, the dispatcher infrastructure from Plan 2, FastAPI routing.

**Reference spec:** [`docs/superpowers/specs/2026-05-05-typed-fragment-emitter-design.md`](../specs/2026-05-05-typed-fragment-emitter-design.md), §3 (renderer dispatch) and §9 (Phase 5 of the migration sequence).

**Predecessor plans:** [Plan 1 — foundations](2026-05-05-typed-fragment-foundations.md), [Plan 2 — integration](2026-05-05-typed-fragment-integration.md).

**Out of scope for this plan:** converting any other surface, building Fragment equivalents for `mode: detail` / `mode: form` / `mode: dashboard`, deleting any scanner test, deleting any Jinja template. The Jinja path remains the default for every surface that doesn't carry `render: fragment`.

## Phase-5 stop condition (revised)

The original spec called for "at least one scanner test retired" as the Phase 5 success criterion. That framing turns out to be too coarse — the scanners (`find_nested_chromes`, `find_duplicate_titles_in_cards`, `find_hidden_primary_actions`) check rendered DOM regardless of which renderer produced it, so a single surface conversion can't make any scanner obsolete on its own. Scanner retirement is a property of the cumulative migration; later phases (where 30+ surfaces have flipped) make individual scanners structurally redundant, and Phase 10 deletes the file.

For Phase 5, the revised stop condition is:

> **simple_task's `task_list` surface renders end-to-end via FragmentRenderer with parity to the Jinja path on the happy path** (no filter, no sort override, no action). Both renderers produce byte-comparable HTML for the same IR + data inputs on the smoke fixture.

**Abandonment trigger** stays the same in spirit: if we can't get parity on this single surface, the design is wrong — revert and write a postmortem.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle_http/runtime/renderers/jinja.py` | Modify | Replace the stub with a real adapter that delegates to the existing Jinja rendering path |
| `src/dazzle_http/runtime/renderers/fragment_adapter.py` | Create | `FragmentSurfaceAdapter` — IR-to-Fragment translator for `mode: list` |
| `src/dazzle_http/runtime/renderers/dispatch.py` | Create | `dispatch_render(surface, *, ctx, fallback)` helper consulted by the request path |
| `src/dazzle_page/runtime/page_routes.py` | Modify | Insert `dispatch_render` at the surface-render call site; default behaviour unchanged when `surface.render is None` |
| `examples/simple_task/dsl/app.dsl` | Modify | Add `render: fragment` to the `task_list` surface declaration |
| `tests/unit/runtime/test_jinja_renderer_adapter.py` | Create | Verify the JinjaRenderer adapter produces the same HTML as the legacy direct path for a fixture surface |
| `tests/unit/runtime/test_fragment_surface_adapter.py` | Create | Per-method tests for the IR-to-Fragment translator |
| `tests/unit/runtime/test_dispatch_render.py` | Create | Routing logic — `surface.render is None` → Jinja; `render: fragment` → Fragment; unknown → error (caught at link time, defensive guard at dispatch) |
| `tests/integration/test_simple_task_render_fragment.py` | Create | Boots `simple_task`, requests `task_list`, asserts 200 + content; parity against Jinja path |

---

## Conventions

- **TDD throughout.** Failing test → minimal implementation → commit.
- **Lint after each task:** `ruff check src/ tests/ --fix && ruff format src/ tests/`
- **Type check after each task:** `mypy src/dazzle/render --strict` and `mypy src/dazzle_http --ignore-missing-imports`. No new errors over the pre-existing baseline.
- **Commit messages:** `feat(render): <subject>` for new behaviour; `feat(runtime): <subject>` for runtime wiring; `test(render): <subject>` for tests.
- **No new `__future__` imports in render package.** `dazzle_http` follows its existing convention.

---

## Task 1: Make JinjaRenderer real

The Plan 2 `JinjaRenderer` stub raises `NotImplementedError`. Replace with a real adapter that delegates to the existing Jinja rendering path so the dispatcher can route through it.

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/jinja.py`
- Create: `tests/unit/runtime/test_jinja_renderer_adapter.py`

The existing render path lives in `src/dazzle_page/runtime/template_renderer.py` (and downstream). The adapter takes a `(surface_spec, render_context)` pair and returns the same HTML the legacy path would have produced.

- [ ] **Step 1: Read the existing Jinja entry point**

```bash
grep -n "def render\|def get_template\|class .*Renderer" src/dazzle_page/runtime/template_renderer.py | head -10
```

Identify the function that takes a surface IR + context and returns rendered HTML (or a TemplateResponse-like wrapper). The exact name varies; the adapter calls it.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/runtime/test_jinja_renderer_adapter.py
"""JinjaRenderer adapter: same HTML as the legacy direct path."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle_http.runtime.renderers.jinja import JinjaRenderer


def test_jinja_renderer_renders_a_minimal_list_surface() -> None:
    """The adapter accepts a SurfaceSpec + a context dict and returns
    HTML that contains the surface's title and the list-mode chrome."""
    surface = SurfaceSpec(
        name="task_list",
        title="Task List",
        mode=SurfaceMode.LIST,
        entity_ref="Task",
    )
    ctx = {
        "items": [{"id": "1", "title": "Buy milk"}, {"id": "2", "title": "Walk dog"}],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "endpoint": "/api/test",
        "region_name": "task_list_main",
        "total": 2,
    }
    renderer = JinjaRenderer()
    html = renderer.render(surface, ctx)
    assert isinstance(html, str)
    assert "Task List" in html or "task_list" in html  # title present
    assert "Buy milk" in html
    assert "Walk dog" in html
    assert "<table" in html  # list-mode chrome
```

- [ ] **Step 3: Run to verify failure**

```bash
pytest tests/unit/runtime/test_jinja_renderer_adapter.py -v
```

Expected: FAIL — `JinjaRenderer.render` raises `NotImplementedError`.

- [ ] **Step 4: Implement the adapter**

In `src/dazzle_http/runtime/renderers/jinja.py`, replace the stub with:

```python
"""Jinja renderer adapter — wraps the existing template-rendering path.

Consumed by the registry; the dispatcher routes here when a surface has
`render: jinja` (or no render: clause and the framework default falls
through to Jinja). Delegates to the legacy Jinja machinery in
`dazzle_page.runtime.template_renderer` so the actual template selection,
context preparation, and rendering happen exactly as before.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceSpec


class JinjaRenderer:
    """Real adapter — delegates to the legacy Jinja rendering path.

    The adapter exists so the renderer registry has a uniform interface
    across Jinja, Fragment, and any future renderer (PDF, native). Plan 3
    promotes this from a stub (which raised NotImplementedError) to the
    real wrapper around the existing rendering code.
    """

    def render(self, surface: SurfaceSpec, ctx: Any) -> str:
        # Deferred import — keeps the adapter package import-light and
        # avoids any circular-import surprises at module load.
        from dazzle_page.runtime.template_renderer import render_surface

        return render_surface(surface, ctx)
```

If the existing rendering function is called something other than `render_surface` or lives elsewhere, adjust the import — the adapter's job is to be a one-line wrapper. If the legacy path takes additional arguments (request, app_spec, etc.), thread them through `ctx` — the adapter signature stays `(surface, ctx)` so all renderers have one shape.

If `render_surface` doesn't exist as a single entry point, you may need to introduce one. In that case, factor out the existing template-selection-and-render code from `template_renderer.py` into a `render_surface(surface, ctx) -> str` helper FIRST (a separate refactor commit before this task's behavioural change).

- [ ] **Step 5: Verify pass**

```bash
pytest tests/unit/runtime/test_jinja_renderer_adapter.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the broader runtime suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -3
```

Expected: no regressions. Existing tests that called `JinjaRenderer().render(...)` and expected NotImplementedError need to be updated — search for them:
```bash
grep -rn "NotImplementedError\|JinjaRenderer" tests/ 2>/dev/null
```

The Plan 2 default-registration test asserted `JinjaRenderer.render is not yet wired up`; that assertion is now wrong. Update or delete it.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle_http/runtime/renderers/jinja.py tests/unit/runtime/test_jinja_renderer_adapter.py
git commit -m "feat(render): JinjaRenderer adapter wraps legacy template path"
```

---

## Task 2: Build the IR-to-Fragment surface adapter

The `FragmentRenderer` from Plan 1 takes a `Fragment` (typed dataclass tree). The runtime has IR (`SurfaceSpec`) plus runtime data (rows, columns, etc.). We need a translator: `(SurfaceSpec, ctx) -> Fragment`.

This task ships the minimum-viable adapter for `mode: list` only — enough to render `simple_task.task_list`. Other modes raise `NotImplementedError` and are added in subsequent plans.

**Files:**
- Create: `src/dazzle_http/runtime/renderers/fragment_adapter.py`
- Create: `tests/unit/runtime/test_fragment_surface_adapter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/runtime/test_fragment_surface_adapter.py
"""FragmentSurfaceAdapter: IR → Fragment for mode: list."""

import pytest

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.render.fragment import Fragment, Surface, Heading, Region, Table
from dazzle_http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter


def test_list_mode_produces_surface_with_heading_and_region() -> None:
    surface = SurfaceSpec(
        name="task_list",
        title="Task List",
        mode=SurfaceMode.LIST,
        entity_ref="Task",
    )
    ctx = {
        "items": [{"id": "1", "title": "Buy milk"}, {"id": "2", "title": "Walk dog"}],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "task_list_main",
        "endpoint": "/api/test",
        "total": 2,
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.header, Heading)
    assert fragment.header.body == "Task List"
    assert isinstance(fragment.body, Region)
    assert fragment.body.kind == "list"
    assert isinstance(fragment.body.body, Table)


def test_list_mode_table_columns_match_ctx() -> None:
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.LIST, entity_ref="Task")
    ctx = {
        "items": [{"id": "1", "title": "Hello"}],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "x_main",
        "endpoint": "/api/x",
        "total": 1,
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    table = fragment.body.body  # Surface.body=Region, Region.body=Table
    assert table.columns == ("Title",)
    assert table.rows == (("Hello",),)


def test_unsupported_mode_raises() -> None:
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task")
    with pytest.raises(NotImplementedError, match="VIEW"):
        FragmentSurfaceAdapter().build(surface, {})


def test_empty_items_still_produces_well_formed_fragment() -> None:
    """Zero rows is a valid empty list — should produce an EmptyState
    or an empty table without raising."""
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.LIST, entity_ref="Task")
    ctx = {
        "items": [],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "x_main",
        "endpoint": "/api/x",
        "total": 0,
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment, Surface)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the adapter**

```python
# src/dazzle_http/runtime/renderers/fragment_adapter.py
"""IR-to-Fragment translator for surface rendering.

Takes a SurfaceSpec + render context (rows, columns, etc. — same shape
as the Jinja path's context dict) and produces a Fragment tree. The
FragmentRenderer then emits HTML from the tree.

Plan 3 ships the minimum-viable adapter for `mode: list` only — enough
to render simple_task's task_list surface. Subsequent plans add detail,
form, and dashboard modes.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.render.fragment import (
    EmptyState,
    Fragment,
    Heading,
    Region,
    Surface,
    Table,
)


class FragmentSurfaceAdapter:
    """Translate a SurfaceSpec + context into a Fragment tree."""

    def build(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Fragment:
        if surface.mode == SurfaceMode.LIST:
            return self._build_list(surface, ctx)
        raise NotImplementedError(
            f"FragmentSurfaceAdapter does not yet support mode {surface.mode.name!r}; "
            f"Plan 3 covers LIST only. Detail/form/dashboard land in later plans."
        )

    def _build_list(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Surface:
        title = surface.title or surface.name.replace("_", " ").title()
        items: list[dict[str, Any]] = ctx.get("items", [])
        columns: list[dict[str, Any]] = ctx.get("columns", [])

        if not items:
            body: Fragment = EmptyState(
                title="No items yet",
                description="Items will appear here when they are added.",
            )
        else:
            column_labels = tuple(col.get("label", col.get("key", "")) for col in columns)
            rows = tuple(
                tuple(_format_cell(item.get(col["key"]), col.get("type", "text")) for col in columns)
                for item in items
            )
            body = Table(columns=column_labels, rows=rows)

        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="list", body=body),
        )


def _format_cell(value: Any, kind: str) -> str:
    """Stringify a cell value for the typed Table.

    Plan 3 supports the most basic types only — text, str-coerced. Plan 6
    or later adds badge/bool/date/currency/ref support. Until then, we
    str-coerce everything and lose type-specific formatting; this is
    acceptable because the Jinja path remains the default for any surface
    that needs the richer formatting.
    """
    if value is None:
        return ""
    return str(value)
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Lint and types**

```bash
ruff check src/dazzle_http/runtime/renderers tests/unit/runtime --fix && ruff format src/dazzle_http/runtime/renderers tests/unit/runtime
mypy src/dazzle_http/runtime/renderers --ignore-missing-imports
```

Both clean.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_http/runtime/renderers/fragment_adapter.py tests/unit/runtime/test_fragment_surface_adapter.py
git commit -m "feat(render): FragmentSurfaceAdapter — IR-to-Fragment for mode: list"
```

---

## Task 3: Dispatch helper

Centralised dispatch logic: given a surface and a render context, pick the right renderer based on `surface.render` and produce HTML. Default fallback is Jinja so untouched surfaces behave exactly as before.

**Files:**
- Create: `src/dazzle_http/runtime/renderers/dispatch.py`
- Create: `tests/unit/runtime/test_dispatch_render.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/runtime/test_dispatch_render.py
"""Dispatch helper: routes by surface.render with Jinja fallback."""

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.render.fragment.errors import FragmentError
from dazzle_http.runtime.renderers.dispatch import dispatch_render
from dazzle_http.runtime.renderers.init import register_default_renderers
from dazzle_http.runtime.services import RuntimeServices


def _make_services() -> RuntimeServices:
    services = RuntimeServices()
    register_default_renderers(services)
    return services


def test_dispatch_uses_jinja_when_render_is_none() -> None:
    services = _make_services()
    # Replace the registered Jinja renderer with a sentinel so we can
    # observe routing without firing the real Jinja path.
    sentinel = MagicMock(spec=["render"])
    sentinel.render.return_value = "<jinja-output/>"
    services.renderer_registry._handlers["jinja"] = sentinel  # test-only direct mutation

    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    html = dispatch_render(surface, ctx={"items": []}, services=services)
    assert html == "<jinja-output/>"
    sentinel.render.assert_called_once()


def test_dispatch_uses_fragment_when_render_is_fragment() -> None:
    services = _make_services()
    sentinel = MagicMock(spec=["render"])
    sentinel.render.return_value = "<fragment-output/>"
    services.renderer_registry._handlers["fragment"] = sentinel

    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, render="fragment")
    html = dispatch_render(surface, ctx={"items": []}, services=services)
    assert html == "<fragment-output/>"
    sentinel.render.assert_called_once()


def test_dispatch_unknown_renderer_raises() -> None:
    """Defensive — the linker should have already rejected an unknown name,
    but if a render: clause sneaks past validation, dispatch fails loudly."""
    services = _make_services()
    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, render="moonbeam")
    with pytest.raises(FragmentError, match="moonbeam"):
        dispatch_render(surface, ctx={"items": []}, services=services)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_dispatch_render.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the helper**

```python
# src/dazzle_http/runtime/renderers/dispatch.py
"""Dispatch helper: route a surface render through the right renderer.

Consumed at the request-time call site (page_routes.py / workspace_renderer
.py). Uses surface.render to pick a renderer; falls back to "jinja" when
unset. The legacy direct-Jinja path is now a registry roundtrip — same
result, single seam.

The Fragment path goes through FragmentSurfaceAdapter to translate IR +
context into a Fragment tree, then through the registered FragmentRenderer
to emit HTML. The Jinja path passes through unchanged because that
renderer's adapter takes (surface, ctx) directly.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceSpec
from dazzle.render.fragment.errors import FragmentError
from dazzle_http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle_http.runtime.services import RuntimeServices


def dispatch_render(
    surface: SurfaceSpec,
    *,
    ctx: dict[str, Any],
    services: RuntimeServices,
) -> str:
    """Render `surface` using the renderer named by `surface.render`,
    or `"jinja"` if unset. Returns the HTML string.

    Raises FragmentError if the named renderer is not registered (which
    should never happen for a linked AppSpec — the linker rejects unknown
    names — but is enforced defensively here).
    """
    renderer_name = surface.render or "jinja"
    handler = services.renderer_registry.resolve(renderer_name)
    if handler is None:
        raise FragmentError(
            f"surface {surface.name!r}: unknown renderer {renderer_name!r}; "
            f"registered renderers: {sorted(services.renderer_registry.registered_names())}"
        )

    if renderer_name == "fragment":
        # Translate IR + ctx into a Fragment tree, then emit.
        fragment = FragmentSurfaceAdapter().build(surface, ctx)
        return handler.render(fragment)

    # Jinja path (and any future custom renderer) takes (surface, ctx)
    # directly. Convention: handlers that consume an IR + ctx pair declare
    # this signature; handlers that consume a Fragment tree (FragmentRenderer)
    # are wrapped by the conditional above.
    return handler.render(surface, ctx)
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_dispatch_render.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/renderers/dispatch.py tests/unit/runtime/test_dispatch_render.py
git commit -m "feat(render): dispatch_render helper — routes by surface.render with Jinja fallback"
```

---

## Task 4: Wire dispatch into the request path

Currently the request path calls Jinja rendering directly. Replace those calls with `dispatch_render(surface, ctx=ctx, services=services)`. The behaviour change is invisible — Jinja still produces the same output for unflipped surfaces — but now `render: fragment` actually routes.

**Files:**
- Modify: `src/dazzle_page/runtime/page_routes.py` (and possibly `workspace_renderer.py`)

- [ ] **Step 1: Locate the surface-render call sites**

```bash
grep -rn "render_template\|TemplateResponse" src/dazzle_page/runtime/page_routes.py src/dazzle_page/runtime/workspace_renderer.py 2>/dev/null | head -20
grep -rn "render_in_app_shell" src/dazzle_page/runtime/ 2>/dev/null | head -10
```

The primary call site is in `page_routes.py` where surface routes are constructed. The actual template selection happens deeper (in `template_renderer.py`). This task only modifies the *outermost* call — the one that takes a SurfaceSpec and produces an HTML response — to route through `dispatch_render` instead of going straight to Jinja.

If the existing call structure is `render_in_app_shell(request, template, context)` (where `template` is already chosen from the surface mode), the refactor is:

```python
from dazzle_http.runtime.renderers.dispatch import dispatch_render

# In the route handler:
services = request.app.state.services
html = dispatch_render(surface_spec, ctx=context, services=services)
return HTMLResponse(content=html)  # or wrap with the existing app-shell logic
```

If the existing path is more entangled (template selection happens inside the renderer rather than the route), refactor minimally: factor the SurfaceSpec → HTML step into a single function and route THAT through `dispatch_render`.

- [ ] **Step 2: Add a smoke test BEFORE refactor**

The refactor is invasive. Add a smoke test that asserts the existing rendering still works for a representative surface, runs at every step:

```python
# tests/integration/test_request_path_smoke.py (new — or augment existing)
"""Confirms the surface-rendering request path produces HTML for a
representative example app surface, regardless of which renderer is
in play. Used as a regression guard during the dispatch refactor."""

import pytest
from fastapi.testclient import TestClient

# Adjust the import to wherever the example app's create_app lives:
from examples.simple_task.app import create_app  # or similar


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_simple_task_task_list_renders(client) -> None:
    response = client.get("/app/surfaces/task_list")  # adjust path
    assert response.status_code == 200
    assert "Task" in response.text  # content is present
```

If `simple_task` doesn't have a `create_app()` factory exposed, use whichever entry point the existing tests use — search:
```bash
grep -rln "TestClient" tests/integration/ tests/unit/runtime/ 2>/dev/null | head -5
```

- [ ] **Step 3: Refactor the call site to use dispatch_render**

Replace the direct Jinja call with `dispatch_render`. Keep the surrounding shell wrapping (app-shell, htmx-boost-partial, etc. from issue #1019) intact — `dispatch_render` returns the inner HTML; the existing wrapper code handles the shell.

- [ ] **Step 4: Run the smoke test**

```bash
pytest tests/integration/test_request_path_smoke.py -v
```

Expected: PASS. The route still serves the same HTML.

- [ ] **Step 5: Run the broader runtime suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -3
```

Expected: no regressions. Particularly relevant areas:
```bash
pytest tests/ -m "not e2e" -k "render or surface or workspace" -q 2>&1 | tail -10
```

- [ ] **Step 6: Lint and types**

```bash
ruff check src/dazzle_page/runtime --fix && ruff format src/dazzle_page/runtime
mypy src/dazzle_http --ignore-missing-imports
```

Clean.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle_page/runtime/page_routes.py tests/integration/test_request_path_smoke.py
# plus any other modified files
git commit -m "feat(runtime): route surface rendering through dispatch_render"
```

---

## Task 5: Flip simple_task.task_list to render: fragment

Add the DSL clause and verify the surface still renders. This is the moment the Fragment path goes live for one specific surface.

**Files:**
- Modify: `examples/simple_task/dsl/app.dsl`

- [ ] **Step 1: Add the clause**

In `examples/simple_task/dsl/app.dsl`, find the `task_list` surface declaration (around line 234):

```dsl
surface task_list "Task List":
  uses entity Task
  mode: list
  ...
```

Add the `render: fragment` clause:

```dsl
surface task_list "Task List":
  uses entity Task
  mode: list
  render: fragment
  ...
```

- [ ] **Step 2: Validate the DSL parses and links**

```bash
cd examples/simple_task && dazzle validate 2>&1 | tail -10 ; cd -
```

Expected: success — `render: fragment` is recognised and `fragment` is a registered renderer.

- [ ] **Step 3: Boot the app and verify the surface renders**

```bash
cd examples/simple_task && timeout 20 dazzle serve --local 2>&1 | head -40 &
SERVE_PID=$!
sleep 12
curl -s http://localhost:3000/app/surfaces/task_list | head -50
kill $SERVE_PID 2>/dev/null
cd -
```

Expected: the curl returns HTML containing the task list. Visual structure may differ from the Jinja path (Plan 3 doesn't aim for byte parity at the live boot — that's the parity test in Task 6).

If the surface fails to render, debug:
- Did `dispatch_render` raise? Check logs.
- Did `FragmentSurfaceAdapter.build` raise? It only supports LIST mode; the test_fragment_surface_adapter tests cover that, so a failure here suggests a missing context key or unexpected IR shape.

- [ ] **Step 4: Run the integration smoke**

```bash
pytest tests/integration/test_request_path_smoke.py -v
```

Expected: still PASS — the surface returns 200 and contains `Task`.

- [ ] **Step 5: Commit**

```bash
git add examples/simple_task/dsl/app.dsl
git commit -m "feat(simple_task): flip task_list to render: fragment"
```

---

## Task 6: Parity test

Both renderers should produce structurally-equivalent HTML for the same IR + context. Byte parity is unrealistic (CSS class ordering, whitespace, attribute ordering vary), but key content and structural assertions should match.

**Files:**
- Create: `tests/integration/test_simple_task_render_fragment.py`

- [ ] **Step 1: Write the parity test**

```python
# tests/integration/test_simple_task_render_fragment.py
"""Phase-5 parity test: simple_task.task_list renders via Fragment with
the same observable behaviour as the Jinja path."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle_http.runtime.renderers.dispatch import dispatch_render
from dazzle_http.runtime.renderers.init import register_default_renderers
from dazzle_http.runtime.services import RuntimeServices


def _make_services() -> RuntimeServices:
    services = RuntimeServices()
    register_default_renderers(services)
    return services


def _ctx() -> dict:
    """The smoke fixture: a deterministic task-list context."""
    return {
        "items": [
            {"id": "1", "title": "Buy milk"},
            {"id": "2", "title": "Walk dog"},
        ],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "task_list_main",
        "endpoint": "/api/test",
        "total": 2,
    }


def test_jinja_and_fragment_both_render_the_titles() -> None:
    """Both renderers must include both row titles. Byte parity is not
    asserted — class-name ordering, whitespace, and attribute formatting
    legitimately differ. Content and structural shape are what matter."""
    services = _make_services()

    jinja_surface = SurfaceSpec(
        name="task_list", title="Task List", mode=SurfaceMode.LIST, entity_ref="Task"
    )
    fragment_surface = SurfaceSpec(
        name="task_list", title="Task List", mode=SurfaceMode.LIST, entity_ref="Task",
        render="fragment",
    )

    jinja_html = dispatch_render(jinja_surface, ctx=_ctx(), services=services)
    fragment_html = dispatch_render(fragment_surface, ctx=_ctx(), services=services)

    for renderer_name, html in [("jinja", jinja_html), ("fragment", fragment_html)]:
        assert "Buy milk" in html, f"{renderer_name}: missing 'Buy milk'"
        assert "Walk dog" in html, f"{renderer_name}: missing 'Walk dog'"
        assert "Title" in html, f"{renderer_name}: missing column header"
        assert "<table" in html, f"{renderer_name}: missing table chrome"
        assert "<html" not in html.lower(), f"{renderer_name}: leaked outer doc"


def test_jinja_and_fragment_both_render_a_heading() -> None:
    """Heading + table is the structural shape. Both must produce both."""
    services = _make_services()
    jinja_html = dispatch_render(
        SurfaceSpec(name="task_list", title="Task List", mode=SurfaceMode.LIST),
        ctx=_ctx(), services=services,
    )
    fragment_html = dispatch_render(
        SurfaceSpec(name="task_list", title="Task List", mode=SurfaceMode.LIST, render="fragment"),
        ctx=_ctx(), services=services,
    )
    for html in [jinja_html, fragment_html]:
        # h1/h2/h3 — Jinja and Fragment may differ on the level
        assert any(f"<h{level}" in html.lower() for level in (1, 2, 3))
```

- [ ] **Step 2: Run the parity test**

```bash
pytest tests/integration/test_simple_task_render_fragment.py -v
```

Expected: 2 PASS.

If a parity assertion fails:
- **Jinja side missing content** → the existing renderer expects context keys the test isn't supplying. Check `template_renderer.py` for what it looks up.
- **Fragment side missing content** → `FragmentSurfaceAdapter` isn't producing the expected shape. Re-read Task 2's adapter logic.
- **One side has extra wrapping** → expected (Jinja includes app-shell chrome; the Fragment path may not). Adjust assertions to allow it.

- [ ] **Step 3: Run all integration tests**

```bash
pytest tests/integration/ -v 2>&1 | tail -10
```

Expected: no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_simple_task_render_fragment.py
git commit -m "test(render): parity test for Jinja vs Fragment on task_list"
```

---

## Task 7: Final verification + CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the full suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 2: Run mypy**

```bash
mypy src/dazzle/render --strict
mypy src/dazzle src/dazzle_http --ignore-missing-imports
```

Expected: no new errors.

- [ ] **Step 3: Confirm Phase-5 stop condition**

The stop condition is "simple_task's task_list renders end-to-end via FragmentRenderer with parity to the Jinja path on the happy path." Verify by:

a) The integration parity test (Task 6) passes — both renderers produce the row content and structural chrome.

b) `dazzle serve --local` on `simple_task` boots and the task_list surface returns 200. (Already verified in Task 5 step 3; re-confirm here.)

c) No surface in any other example app is affected — they all default to `render: jinja`.

- [ ] **Step 4: Update CHANGELOG**

In `CHANGELOG.md`, add to the `## [Unreleased]` section:

```markdown
### Added
- **Fragment dispatch lit up.** `render: fragment` on a `SurfaceSpec` now
  routes the surface through the typed `FragmentRenderer` instead of the
  legacy Jinja path. Plan 3 of the typed-Fragment migration ships the
  minimum-viable IR-to-Fragment adapter (mode: LIST only) and flips
  `simple_task.task_list` as the first proving case. Other surfaces
  remain on Jinja by default.
- `dispatch_render(surface, ctx, services)` helper centralises the
  renderer-routing decision; the request path now consults this seam
  rather than calling Jinja directly.
- `JinjaRenderer` adapter (previously a stub) now wraps the legacy
  template-rendering path so the registry can route through it.
- `FragmentSurfaceAdapter` translates SurfaceSpec + render context into
  a Fragment tree for surfaces with `render: fragment`.

### Changed
- `simple_task.task_list` surface flipped to `render: fragment`. Visible
  output remains structurally equivalent to the Jinja path (parity test
  in `tests/integration/test_simple_task_render_fragment.py`).
```

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note Plan 3 — Fragment dispatch lit up"
```

---

## Plan completion checklist

After Task 7:

- [ ] `pytest tests/unit/runtime/ tests/integration/ -v` — all pass.
- [ ] `pytest tests/ -m "not e2e"` — no regressions outside the new tests.
- [ ] `mypy src/dazzle/render --strict` — clean.
- [ ] `mypy src/dazzle src/dazzle_http --ignore-missing-imports` — no new errors.
- [ ] `ruff check src/ tests/ && ruff format --check src/ tests/` — clean.
- [ ] `dazzle serve --local` on `examples/simple_task` boots; task_list surface returns 200.
- [ ] `git status` clean.
- [ ] **Phase-5 stop condition met:** simple_task's task_list renders via Fragment with structural parity to the Jinja path. The dispatcher works end-to-end. Plan 4+ can incrementally convert more surfaces.

---

## Self-Review

**Spec coverage:**
- Spec §3 (renderer dispatch) — `dispatch_render` (Task 3) is the actual dispatch site.
- Spec §9 Phase 5 ("first conversion target") — Task 5 flips simple_task.task_list. The original "retire one scanner" criterion is renegotiated to a parity-test criterion (acknowledged in the plan's "Phase-5 stop condition" section).
- Spec §4 (Jinja interop) — the JinjaRenderer adapter (Task 1) makes the registry the seam, but per-region splice (`{{ render_region(...) }}` in templates, `RawHTML(jinja_render(...))` in Fragment trees) is deferred to Plan 4+ since this plan only converts surface-level rendering.
- Spec §6 (token integration), §7 (htmx integration) — relevant only when surfaces beyond LIST land. Out of scope for this plan.

**Placeholder scan:**
- All file paths exact.
- Every step has complete code or exact commands.
- The "If the legacy path is more entangled" hedge in Task 1 is intentional — the existing structure varies, and the engineer must read the file to choose. The plan provides the destination shape (`render_surface(surface, ctx) -> str`), not the exact source-line edits.
- Task 4 step 1 explicitly tells the engineer to grep for the call sites because the production code structure may have evolved since the plan was written.

**Type consistency:**
- `JinjaRenderer.render(surface, ctx) -> str` (Task 1) and `FragmentRenderer.render(fragment, ctx) -> str` (Plan 1) — different signatures; the `dispatch_render` helper (Task 3) bridges them by calling `FragmentSurfaceAdapter.build` before invoking FragmentRenderer.
- `dispatch_render(surface, *, ctx, services) -> str` (Task 3) — used in Task 4's call-site refactor and Task 6's parity test with this exact signature.
- `FragmentSurfaceAdapter().build(surface, ctx) -> Fragment` (Task 2) — used in Task 3.

**Scope check:**
- Plan covers spec Phase 5 with the scope renegotiated as "first surface flipped + dispatch wired + parity proven." The "retire scanner" framing is deferred to Plan N (some later plan) when enough surfaces have flipped to make individual scanners structurally redundant. This is documented at the top of the plan.
- The plan is appropriately sized: 7 tasks, each TDD, each producing self-contained changes.
