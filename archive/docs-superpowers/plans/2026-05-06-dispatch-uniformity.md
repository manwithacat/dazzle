# Dispatch Uniformity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the hardcoded `if renderer_name == "fragment"` branch in `dispatch_render` so the dispatcher calls every renderer with a uniform `(surface, ctx)` signature. Closes the dispatch shape-routing carry-forward from Plan 3's final review and prepares the substrate for a third renderer (e.g. Penny Dreadful's `cytoscape_3d`) without further dispatcher changes.

**Architecture:** Apply the Adapter pattern. Create a new `FragmentSurfaceRenderer` adapter that wraps `FragmentRenderer` and exposes `render(surface, ctx) -> str`. Internally it builds the Fragment tree via `FragmentSurfaceAdapter` and renders via the underlying `FragmentRenderer`. The renderer registry stores the adapter, not the bare `FragmentRenderer`. The dispatcher becomes a single uniform call: `handler.render(surface, ctx)`. The `Renderer` protocol tightens from `render(*args, **kwargs) -> str` to `render(surface: SurfaceSpec, ctx: dict) -> str`.

**Tech Stack:** Python 3.12+, the typed Fragment substrate from Plan 1, the dispatcher infrastructure from Plans 2 and 3.

**Reference:** carry-forward #1 from Plan 3's final code review (`dispatch_render` shape-routing). Plan 4 closed the CSS gap; this plan closes the dispatch architectural debt before further surface conversions.

**Out of scope:** production-path Jinja parity (carry-forward #3 — separate plan); converting another surface mode (Plan 6+); changing the JinjaRenderer adapter (it already takes `(surface, ctx)` — no change needed).

---

## Stop condition

> **`dispatch_render` no longer special-cases any renderer name.** The function reduces to: resolve the handler, call `handler.render(surface, ctx)`, return the result. All registered renderers (`jinja`, `fragment`, plus any future renderer) satisfy the same `(surface, ctx)` shape. The `Renderer` protocol declares this shape and mypy enforces it on registration.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle_http/runtime/renderers/fragment.py` | Modify | Replace the trivial re-export with a `FragmentSurfaceRenderer` adapter class that wraps `FragmentRenderer` and exposes `render(surface, ctx) -> str` |
| `src/dazzle_http/runtime/renderers/init.py` | Modify | Register `FragmentSurfaceRenderer` instead of bare `FragmentRenderer` |
| `src/dazzle_http/runtime/renderers/dispatch.py` | Modify | Remove the `if renderer_name == "fragment"` branch — single uniform call |
| `src/dazzle/render/fragment/registry.py` | Modify | Tighten `Renderer` protocol to `render(surface: SurfaceSpec, ctx: dict[str, Any]) -> str` |
| `tests/unit/runtime/test_renderer_default_registration.py` | Modify | Update assertion that the registered fragment handler is `FragmentSurfaceRenderer` (not `FragmentRenderer` directly) |
| `tests/unit/runtime/test_fragment_surface_renderer.py` | Create | Adapter contract test: builds a Fragment tree and renders it for `(surface, ctx)` input |
| `tests/unit/runtime/test_dispatch_render.py` | Modify | Remove the special-case mocking; both renderers can be tested with the same scaffold now |
| `CHANGELOG.md` | Modify | Note the dispatch uniformity change |

8 files. Plan 5 is the smallest of the typed-Fragment series.

---

## Conventions

- **TDD throughout.** Failing test → minimal implementation → commit.
- **Lint after each task:** `ruff check src/ tests/ --fix && ruff format src/ tests/`
- **Type check after each task:** `mypy src/dazzle/render --strict` and `mypy src/dazzle_http --ignore-missing-imports`. No new errors over the pre-existing baseline.
- **Commit messages:** `feat(render): <subject>` or `refactor(render): <subject>` for source; `test(render): <subject>` for tests.

---

## Task 1: Create FragmentSurfaceRenderer adapter

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/fragment.py`
- Create: `tests/unit/runtime/test_fragment_surface_renderer.py`

The current `fragment.py` is a one-line re-export of `FragmentRenderer`. Replace with an adapter class that wraps it.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/runtime/test_fragment_surface_renderer.py`:

```python
"""FragmentSurfaceRenderer adapter — uniform (surface, ctx) interface."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle_http.runtime.renderers.fragment import FragmentSurfaceRenderer


def test_fragment_surface_renderer_renders_a_minimal_list_surface() -> None:
    """The adapter accepts a SurfaceSpec + ctx dict and returns HTML
    containing the row content. Internally it builds a Fragment tree
    via FragmentSurfaceAdapter and renders via FragmentRenderer."""
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
    renderer = FragmentSurfaceRenderer()
    html = renderer.render(surface, ctx)
    assert isinstance(html, str)
    assert "Buy milk" in html
    assert "Walk dog" in html
    assert "<table" in html
    assert "dz-surface" in html  # uses Fragment chrome, not Jinja chrome


def test_fragment_surface_renderer_signature_matches_jinja_adapter() -> None:
    """Both adapters share the (surface, ctx) -> str signature so the
    dispatcher can call them uniformly."""
    from dazzle_http.runtime.renderers.jinja import JinjaRenderer

    fragment_render = FragmentSurfaceRenderer.render
    jinja_render = JinjaRenderer.render

    # Same parameter count (self + surface + ctx)
    assert fragment_render.__code__.co_argcount == jinja_render.__code__.co_argcount
    # Same parameter names
    assert fragment_render.__code__.co_varnames[: fragment_render.__code__.co_argcount] == \
        jinja_render.__code__.co_varnames[: jinja_render.__code__.co_argcount]
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_fragment_surface_renderer.py -v
```

Expected: FAIL — `cannot import name 'FragmentSurfaceRenderer'`.

- [ ] **Step 3: Implement the adapter**

Replace `src/dazzle_http/runtime/renderers/fragment.py` content:

```python
"""Fragment renderer adapter — uniform (surface, ctx) interface.

Wraps `dazzle.render.fragment.renderer.FragmentRenderer` so the renderer
registry stores adapters with a uniform shape across Jinja, Fragment, and
future renderers (cytoscape, PDF, etc.). The dispatcher (`dispatch_render`)
calls every registered handler with `(surface, ctx)` — adapters know how
to translate that into whatever the underlying renderer needs.

For the Fragment path: `FragmentSurfaceAdapter` builds a `Fragment` tree
from the IR + ctx, then `FragmentRenderer` emits HTML from the tree.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceSpec
from dazzle.render.fragment.renderer import FragmentRenderer


class FragmentSurfaceRenderer:
    """Adapter — exposes FragmentRenderer through a (surface, ctx) interface.

    Holds an internal FragmentRenderer instance and a FragmentSurfaceAdapter
    instance, both stateless and reusable across requests. Construction is
    cheap (no I/O); the registry stores one instance per app.
    """

    def __init__(self) -> None:
        # Deferred import — fragment_adapter imports SurfaceSpec, no cycle
        # but matches the convention used by other adapter modules.
        from dazzle_http.runtime.renderers.fragment_adapter import (
            FragmentSurfaceAdapter,
        )

        self._renderer = FragmentRenderer()
        self._surface_adapter = FragmentSurfaceAdapter()

    def render(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> str:
        fragment = self._surface_adapter.build(surface, ctx)
        return self._renderer.render(fragment)


# Backwards-compat alias so any caller still importing the bare
# FragmentRenderer from this module keeps working through Plan 5. Plan 6
# can drop this alias once we audit callers.
__all__ = ["FragmentSurfaceRenderer", "FragmentRenderer"]
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/unit/runtime/test_fragment_surface_renderer.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/renderers/fragment.py tests/unit/runtime/test_fragment_surface_renderer.py
git commit -m "feat(render): FragmentSurfaceRenderer adapter for uniform (surface, ctx) shape"
```

---

## Task 2: Register FragmentSurfaceRenderer in defaults

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/init.py`
- Modify: `tests/unit/runtime/test_renderer_default_registration.py`

- [ ] **Step 1: Update the failing test first**

The Plan 2 test asserts the registered fragment handler is a `FragmentRenderer`. After Plan 5 it should be a `FragmentSurfaceRenderer`. Update:

```python
# In tests/unit/runtime/test_renderer_default_registration.py, change:
#   from dazzle.render.fragment.renderer import FragmentRenderer
#   ...
#   assert isinstance(handler, FragmentRenderer)
# to:
#   from dazzle_http.runtime.renderers.fragment import FragmentSurfaceRenderer
#   ...
#   assert isinstance(handler, FragmentSurfaceRenderer)
```

Read the file first to make a clean edit:

```bash
sed -n '1,40p' tests/unit/runtime/test_renderer_default_registration.py
```

Adjust the import and the assertion. Run the test:

```bash
pytest tests/unit/runtime/test_renderer_default_registration.py -v
```

Expected: 1 PASS, 1 FAIL — the test that asserts `isinstance(handler, FragmentSurfaceRenderer)` fails because `init.py` still registers the bare FragmentRenderer.

- [ ] **Step 2: Update init.py**

Read the file first:

```bash
cat src/dazzle_http/runtime/renderers/init.py
```

Replace the import and registration:

```python
# OLD:
# from dazzle_http.runtime.renderers.fragment import FragmentRenderer
# ...
# services.renderer_registry.register(name="fragment", handler=FragmentRenderer())

# NEW:
from dazzle_http.runtime.renderers.fragment import FragmentSurfaceRenderer
# ...
services.renderer_registry.register(name="fragment", handler=FragmentSurfaceRenderer())
```

- [ ] **Step 3: Run to verify pass**

```bash
pytest tests/unit/runtime/test_renderer_default_registration.py -v
```

Expected: 3 PASS.

- [ ] **Step 4: Run the broader runtime suite**

```bash
pytest tests/unit/runtime/ -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/renderers/init.py tests/unit/runtime/test_renderer_default_registration.py
git commit -m "refactor(render): register FragmentSurfaceRenderer adapter (was bare FragmentRenderer)"
```

---

## Task 3: Simplify dispatch_render

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/dispatch.py`
- Modify: `tests/unit/runtime/test_dispatch_render.py`

Remove the `if renderer_name == "fragment"` branch. With both adapters now exposing `(surface, ctx) -> str`, the dispatcher can call them uniformly.

- [ ] **Step 1: Update the dispatch tests first**

The Plan 3 test mocked the `fragment` handler with a sentinel that returned `"<fragment-output/>"` and only asserted the sentinel was called once. Post-Plan-5 the same shape works for both renderers; the test stays meaningful.

Read the existing test:

```bash
cat tests/unit/runtime/test_dispatch_render.py
```

Add a new test that confirms the uniform-call invariant:

```python
def test_dispatch_calls_handler_with_surface_and_ctx_for_both_renderers() -> None:
    """Plan 5: both renderers receive (surface, ctx) — no shape-routing
    in the dispatcher. Confirms by calling both via dispatch_render and
    checking each handler was called with the same argument shape."""
    from unittest.mock import MagicMock
    from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
    from dazzle_http.runtime.renderers.dispatch import dispatch_render
    from dazzle_http.runtime.renderers.init import register_default_renderers
    from dazzle_http.runtime.services import RuntimeServices

    services = RuntimeServices()
    register_default_renderers(services)

    # Replace both registered renderers with sentinels
    jinja_sentinel = MagicMock(spec=["render"])
    jinja_sentinel.render.return_value = "<jinja/>"
    services.renderer_registry._handlers["jinja"] = jinja_sentinel

    fragment_sentinel = MagicMock(spec=["render"])
    fragment_sentinel.render.return_value = "<fragment/>"
    services.renderer_registry._handlers["fragment"] = fragment_sentinel

    ctx = {"items": []}
    s_jinja = SurfaceSpec(name="x", mode=SurfaceMode.LIST)
    s_fragment = SurfaceSpec(name="x", mode=SurfaceMode.LIST, render="fragment")

    dispatch_render(s_jinja, ctx=ctx, services=services)
    dispatch_render(s_fragment, ctx=ctx, services=services)

    # Both received (surface, ctx) — same shape
    jinja_args = jinja_sentinel.render.call_args
    fragment_args = fragment_sentinel.render.call_args
    assert jinja_args[0][0] is s_jinja
    assert jinja_args[0][1] is ctx
    assert fragment_args[0][0] is s_fragment
    assert fragment_args[0][1] is ctx
```

- [ ] **Step 2: Run to verify the new test fails**

```bash
pytest tests/unit/runtime/test_dispatch_render.py::test_dispatch_calls_handler_with_surface_and_ctx_for_both_renderers -v
```

Expected: FAIL — the current dispatcher's `if renderer_name == "fragment"` branch calls `handler.render(fragment)` (one arg, a Fragment tree) for the fragment path, not `handler.render(surface, ctx)`.

- [ ] **Step 3: Simplify dispatch.py**

Replace the entire content of `src/dazzle_http/runtime/renderers/dispatch.py`:

```python
"""Dispatch helper: route a surface render through the right renderer.

Plan 5 simplified the dispatcher to a single uniform call. Every
registered renderer exposes `render(surface, ctx) -> str` via its adapter
(JinjaRenderer wraps the legacy template path; FragmentSurfaceRenderer
wraps the typed Fragment substrate). The dispatcher's only job is to
look up the handler by name and call it.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceSpec
from dazzle.render.fragment.errors import FragmentError
from dazzle_http.runtime.services import RuntimeServices


def dispatch_render(
    surface: SurfaceSpec,
    *,
    ctx: dict[str, Any],
    services: RuntimeServices,
) -> str:
    """Render `surface` using the renderer named by `surface.render`,
    or `"jinja"` if unset. Returns the HTML string.

    Raises FragmentError if the named renderer is not registered.
    """
    renderer_name = surface.render or "jinja"
    handler = services.renderer_registry.resolve(renderer_name)
    if handler is None:
        raise FragmentError(
            f"surface {surface.name!r}: unknown renderer {renderer_name!r}; "
            f"registered renderers: {sorted(services.renderer_registry.registered_names())}"
        )

    return handler.render(surface, ctx)
```

- [ ] **Step 4: Run all dispatch tests**

```bash
pytest tests/unit/runtime/test_dispatch_render.py -v
```

Expected: ALL PASS, including the new uniform-call test from step 1.

The two pre-existing tests (`test_dispatch_uses_jinja_when_render_is_none`, `test_dispatch_uses_fragment_when_render_is_fragment`) used sentinels that returned strings; they still work because `handler.render(surface, ctx)` is called with the same return-value shape.

- [ ] **Step 5: Run integration parity test (Plan 3's stop condition)**

```bash
pytest tests/integration/test_simple_task_render_fragment.py -v
```

Expected: 3 PASS. The parity test is the load-bearing verification that Fragment dispatch still works end-to-end after the refactor.

- [ ] **Step 6: Lint and types**

```bash
ruff check src/dazzle_http/runtime/renderers tests/unit/runtime --fix && ruff format src/dazzle_http/runtime/renderers tests/unit/runtime
mypy src/dazzle_http --ignore-missing-imports
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle_http/runtime/renderers/dispatch.py tests/unit/runtime/test_dispatch_render.py
git commit -m "refactor(render): dispatch_render — uniform handler call, no shape branching"
```

---

## Task 4: Tighten the Renderer protocol

**Files:**
- Modify: `src/dazzle/render/fragment/registry.py`

Now that all renderers have the same shape, the `Renderer` protocol can declare the actual signature instead of `*args, **kwargs`.

- [ ] **Step 1: Read the current protocol**

```bash
sed -n '15,30p' src/dazzle/render/fragment/registry.py
```

The current declaration is:

```python
@runtime_checkable
class Renderer(Protocol):
    """Structural protocol for registered renderers.

    Renderers exist in two shapes — Fragment-tree consumers (FragmentRenderer)
    and IR+context consumers (JinjaRenderer, future PDF/native adapters).
    The dispatcher (`dispatch_render` in `dazzle_http.runtime.renderers.dispatch`)
    knows which signature each registered handler uses; the protocol stays
    flexible to accommodate both shapes."""

    def render(self, *args: Any, **kwargs: Any) -> str: ...
```

- [ ] **Step 2: Tighten the protocol**

Update to:

```python
@runtime_checkable
class Renderer(Protocol):
    """Structural protocol for registered renderers.

    Plan 5 unified the dispatch shape: every renderer adapter takes
    `(surface, ctx)` and returns an HTML string. Adapters bridge to
    underlying renderers — JinjaRenderer wraps the legacy template
    path; FragmentSurfaceRenderer wraps the typed Fragment substrate.
    Custom renderers (e.g. cytoscape_3d, future PDF/native targets) just
    need to satisfy this protocol.

    The first parameter is intentionally `Any` rather than `SurfaceSpec`
    to avoid a circular import (this module is in `dazzle.render.fragment`,
    SurfaceSpec is in `dazzle.core.ir.surfaces`, and the latter imports
    nothing from this module — but the dependency direction across the
    package boundary is one we don't want to invert). The dispatcher's
    call site uses the typed SurfaceSpec; the protocol just structurally
    requires the right arity."""

    def render(self, surface: Any, ctx: dict[str, Any]) -> str: ...
```

- [ ] **Step 3: Run the render package strict mypy**

```bash
mypy src/dazzle/render --strict
```

Expected: clean. If FragmentRenderer (in `src/dazzle/render/fragment/renderer.py`) now fails to satisfy the Renderer protocol because its `render` method takes `(fragment, ctx)` — it does — that's correct: `FragmentRenderer` is no longer the registered handler post-Plan-5; the registered handler is `FragmentSurfaceRenderer`, which has the right shape. The protocol no longer needs to accommodate `FragmentRenderer` directly.

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/registry.py
git commit -m "refactor(render): tighten Renderer protocol to render(surface, ctx) -> str"
```

---

## Task 5: CHANGELOG note + final verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update CHANGELOG**

In `CHANGELOG.md`, add to the `## [Unreleased]` section under `### Changed`:

```markdown
- **Dispatch uniformity.** All registered renderers now expose
  `render(surface, ctx) -> str`. The Fragment path is wrapped in a new
  `FragmentSurfaceRenderer` adapter that internally builds a Fragment
  tree via `FragmentSurfaceAdapter` and renders via `FragmentRenderer`.
  The dispatcher's `if renderer_name == "fragment"` shape-routing is
  gone — `dispatch_render` is now a single uniform call. The `Renderer`
  protocol tightened from `render(*args, **kwargs) -> str` to
  `render(surface, ctx) -> str`. Custom renderers (PDF, native, etc.)
  just need to satisfy this signature; no further dispatcher changes
  required.
```

- [ ] **Step 2: Run the full unit suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 3: Confirm stop condition**

The stop condition: `dispatch_render` no longer special-cases any renderer name. Verify by reading the final state:

```bash
cat src/dazzle_http/runtime/renderers/dispatch.py
```

Expected: NO `if renderer_name == ...` branch. The function ends with `return handler.render(surface, ctx)`.

```bash
grep -n "if renderer_name" src/dazzle_http/runtime/renderers/dispatch.py
```

Expected: no output (the line is gone).

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note Plan 5 dispatch uniformity"
```

---

## Plan completion checklist

- [ ] `pytest tests/unit/runtime/ tests/integration/test_simple_task_render_fragment.py -v` — all pass.
- [ ] `pytest tests/ -m "not e2e"` — no regressions.
- [ ] `mypy src/dazzle/render --strict` — clean.
- [ ] `mypy src/dazzle src/dazzle_http --ignore-missing-imports` — no new errors over baseline.
- [ ] `ruff check src/ tests/ && ruff format --check src/ tests/` — clean.
- [ ] `git status` clean.
- [ ] **Stop condition met:** `dispatch_render` has no `if renderer_name ==` branch; both renderers go through the same uniform call.

---

## Self-Review

**Spec coverage:**
- Plan 3 review carry-forward #1 (dispatch shape-routing): closed by Tasks 1-3.
- Plan 3 review carry-forward #2 (Renderer protocol too loose): closed by Task 4.
- Plan 3 review carry-forward #3 (production-path Jinja parity): explicitly out of scope; separate plan.

**Placeholder scan:**
- All file paths exact.
- Every code block is concrete.
- The "If FragmentRenderer now fails to satisfy" hedge in Task 4 step 3 is intentional — it's a positive observation about why the change is correct, not a TBD.

**Type consistency:**
- `FragmentSurfaceRenderer` from Task 1 is used in Task 2's registration and in Task 3's test assertions.
- The `render(surface, ctx) -> str` signature is used uniformly across Tasks 1, 2, 3, 4.
- `Renderer` protocol's `render(surface: Any, ctx: dict[str, Any]) -> str` (Task 4) is satisfied by both `JinjaRenderer.render(self, surface, ctx)` and `FragmentSurfaceRenderer.render(self, surface, ctx)`.

**Scope check:**
- Plan covers exactly the dispatch-uniformity carry-forward. 5 tasks, smallest plan in the typed-Fragment series.
- Production-path parity test is a deliberately separate concern. Plan 6+ extends as needed.
