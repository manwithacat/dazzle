# Typed Fragment Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `render: <name>` DSL clause through grammar, IR, parser, linker, and runtime registries — so any surface or region can declare a renderer choice that propagates into the IR. Default behaviour unchanged: with no `render:` clause, every existing example app continues to serve via Jinja.

**Architecture:** Adds one new keyword (`render`) and one optional field on each of `SurfaceSpec` and `WorkspaceRegion`. Linker validation cross-checks the named renderer against a runtime registry. `RendererRegistry` lives next to `PrimitiveRegistry` in the render package; both attach to `RuntimeServices` at startup. The framework registers two renderers — `jinja` (the existing path, wrapped) and `fragment` (the typed substrate from Plan 1). No surface flips — Plan 3 does the first conversion.

**Tech Stack:** Python 3.12+, Pydantic IR, FastAPI runtime, the `dazzle.render.fragment` package from Plan 1.

**Reference spec:** [`docs/superpowers/specs/2026-05-05-typed-fragment-emitter-design.md`](../specs/2026-05-05-typed-fragment-emitter-design.md), §3 and §5.
**Predecessor plan:** [`2026-05-05-typed-fragment-foundations.md`](2026-05-05-typed-fragment-foundations.md).
**Successor plan:** Plan 3 — first conversion + scanner retirement.

**Out of scope for this plan:** the actual dispatch of a request to a non-Jinja renderer; converting any existing template to a Fragment equivalent; flipping any example app's surface to `render: fragment`. Those are Plan 3.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle/core/lexer.py` | Modify | Add `RENDER = "render"` token |
| `src/dazzle/core/ir/surfaces.py` | Modify | Add `render: str \| None = None` field to `SurfaceSpec` |
| `src/dazzle/core/ir/workspaces.py` | Modify | Add `render: str \| None = None` field to `WorkspaceRegion` |
| `src/dazzle/core/dsl_parser_impl/surface.py` | Modify | Handle `render: <name>` clause inside `parse_surface` |
| `src/dazzle/core/dsl_parser_impl/workspace.py` | Modify | Handle `render: <name>` clause inside `parse_workspace_region` |
| `src/dazzle/render/fragment/registry.py` | Modify | Add `RendererRegistry` class alongside existing `PrimitiveRegistry` |
| `src/dazzle/core/linker.py` | Modify | Validate that any `render:` reference resolves to a registered renderer |
| `src/dazzle_http/runtime/services.py` | Modify | Add `renderer_registry` and `primitive_registry` fields on `RuntimeServices` |
| `src/dazzle_http/runtime/renderers/__init__.py` | Create | Renderer adapter package |
| `src/dazzle_http/runtime/renderers/jinja.py` | Create | Thin wrapper around the existing Jinja rendering path; registers under name `"jinja"` |
| `src/dazzle_http/runtime/renderers/fragment.py` | Create | Wraps `FragmentRenderer` from Plan 1; registers under name `"fragment"` |
| `src/dazzle_http/runtime/renderers/init.py` | Create | `register_default_renderers(services)` called at startup |
| `tests/unit/core/test_render_clause_parsing.py` | Create | Parser-level tests for `render:` on surfaces and regions |
| `tests/unit/core/test_render_clause_linking.py` | Create | Linker validation tests (unknown renderer name fails) |
| `tests/unit/render/fragment/test_renderer_registry.py` | Create | RendererRegistry contract tests |
| `tests/unit/runtime/test_runtime_renderer_registries.py` | Create | RuntimeServices wiring tests |
| `tests/integration/test_render_default_unchanged.py` | Create | End-to-end smoke: `simple_task` boots, validates, default render path unchanged |

13 source-file changes + 5 new test files. Smaller than Plan 1 — the substrate already exists; this plan reifies its dispatch surface.

---

## Conventions used in every task

- **TDD throughout.** Failing test → minimal implementation → commit.
- **Test command:** `pytest tests/<path> -v`.
- **Lint after each task:** `ruff check src/ tests/ --fix && ruff format src/ tests/`.
- **Type check after each task:** `mypy src/dazzle/render --strict` (the render package keeps strict). For the broader `src/dazzle` and `src/dazzle_http`, run plain `mypy --ignore-missing-imports` and ensure no new errors are introduced over the pre-existing baseline.
- **Commit messages:** `feat(<area>): <subject>` for new behaviour; `test(<area>): <subject>` for test-only; `chore(<area>): <subject>` for scaffolding.

---

## Phase A — DSL grammar

### Task 1: Add the RENDER token to the lexer

**Files:**
- Modify: `src/dazzle/core/lexer.py` (around line 494, near `LAYOUT = "layout"`)

The lexer's `TokenType` enum maps each value-string to a recognised keyword. Adding an entry creates a new keyword.

- [ ] **Step 1: Locate the LAYOUT entry**

In `src/dazzle/core/lexer.py`, find the line `LAYOUT = "layout"` (around line 494). The new RENDER token goes alphabetically near it.

- [ ] **Step 2: Add the RENDER token**

Insert `RENDER = "render"` in alphabetical order within the `TokenType` enum block. Example placement (the surrounding entries depend on the actual file; insert wherever `R*` keywords live):

```python
RENDER = "render"
```

- [ ] **Step 3: Verify the lexer recognises the keyword**

```bash
python -c "from dazzle.core.lexer import TokenType; print(TokenType.RENDER)"
```

Expected output: `TokenType.RENDER`

Run the existing lexer tests:

```bash
pytest tests/unit/test_lexer.py -v 2>&1 | tail -20
```

Expected: All pass (no regressions). If a lexer-keyword-list test exists and it asserts a fixed count, update it.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/core/lexer.py
git commit -m "feat(lexer): add RENDER token for the render: DSL clause"
```

---

## Phase B — IR

### Task 2: Add `render` field to SurfaceSpec

**Files:**
- Modify: `src/dazzle/core/ir/surfaces.py` (the `SurfaceSpec` class around line 281)
- Test: `tests/unit/core/test_render_clause_parsing.py` (new — but the field-existence assertion goes here)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/test_render_clause_parsing.py`:

```python
"""Tests for the render: DSL clause on SurfaceSpec and WorkspaceRegion."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec


def test_surface_spec_render_default_none() -> None:
    s = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    assert s.render is None


def test_surface_spec_render_explicit() -> None:
    s = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, render="fragment")
    assert s.render == "fragment"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/core/test_render_clause_parsing.py::test_surface_spec_render_default_none -v
```

Expected: FAIL with `AttributeError` or Pydantic `extra fields not permitted`.

- [ ] **Step 3: Add the render field**

In `src/dazzle/core/ir/surfaces.py`, inside `class SurfaceSpec`, add a new field. Place it near `display: str | None = None` (around line 330) so related "rendering choice" fields cluster:

```python
    # Plan 2 (#TBD): renderer name. Optional; resolves through the
    # RendererRegistry on RuntimeServices. None = framework default
    # (Jinja today; Fragment when a primitive exists for the surface mode
    # — see linker resolution rules). Validated at link time.
    render: str | None = None
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/core/test_render_clause_parsing.py::test_surface_spec_render_default_none tests/unit/core/test_render_clause_parsing.py::test_surface_spec_render_explicit -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/surfaces.py tests/unit/core/test_render_clause_parsing.py
git commit -m "feat(ir): SurfaceSpec.render field for renderer choice"
```

---

### Task 3: Add `render` field to WorkspaceRegion

**Files:**
- Modify: `src/dazzle/core/ir/workspaces.py` (the `WorkspaceRegion` class around line 390)
- Test: `tests/unit/core/test_render_clause_parsing.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/core/test_render_clause_parsing.py`:

```python
from dazzle.core.ir.workspaces import WorkspaceRegion


def test_workspace_region_render_default_none() -> None:
    r = WorkspaceRegion(name="alerts")
    assert r.render is None


def test_workspace_region_render_explicit() -> None:
    r = WorkspaceRegion(name="alerts", render="cytoscape_3d")
    assert r.render == "cytoscape_3d"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/core/test_render_clause_parsing.py::test_workspace_region_render_default_none tests/unit/core/test_render_clause_parsing.py::test_workspace_region_render_explicit -v
```

Expected: FAIL.

- [ ] **Step 3: Add the render field**

In `src/dazzle/core/ir/workspaces.py`, inside `class WorkspaceRegion`, add (near `display: DisplayMode = DisplayMode.LIST`):

```python
    # Plan 2 (#TBD): renderer name override at region level. Optional;
    # falls through to the surface's renderer if unset, then to the
    # framework default. Validated at link time against the RendererRegistry.
    render: str | None = None
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/core/test_render_clause_parsing.py -v
```

Expected: 4 PASS (2 from Task 2 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/workspaces.py tests/unit/core/test_render_clause_parsing.py
git commit -m "feat(ir): WorkspaceRegion.render field for renderer choice"
```

---

## Phase C — Parser

### Task 4: Surface parser handles `render:` clause

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/surface.py` (`parse_surface` method, around line 39)
- Test: `tests/unit/core/test_render_clause_parsing.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/core/test_render_clause_parsing.py`:

```python
from dazzle.core.dsl_parser import parse_dsl


def test_surface_parser_accepts_render_clause() -> None:
    src = """
module test
app demo "Demo"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
  render: fragment
"""
    module = parse_dsl(src)
    assert len(module.surfaces) == 1
    assert module.surfaces[0].render == "fragment"


def test_surface_parser_render_omitted_remains_none() -> None:
    src = """
module test
app demo "Demo"

entity Task "Task":
  id: uuid pk

surface task_list "Tasks":
  uses entity Task
  mode: list
"""
    module = parse_dsl(src)
    assert module.surfaces[0].render is None
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/core/test_render_clause_parsing.py::test_surface_parser_accepts_render_clause -v
```

Expected: FAIL — parser doesn't recognise the `render:` clause; either a parse error or `render is None` despite the clause.

- [ ] **Step 3: Add the parser branch**

In `src/dazzle/core/dsl_parser_impl/surface.py`, inside `parse_surface` (around line 39–235), add a new local variable initialiser at the top of the method (alongside `layout = "wizard"`):

```python
        render: str | None = None  # Plan 2: optional renderer name
```

Then add a new `elif self.match(...)` branch in the dispatch loop (around line 82, near the LAYOUT branch). Place it alphabetically near other clauses (after PRIORITY or near ACCESS):

```python
            # Plan 2: render: <renderer-name> — opt into a non-default renderer
            elif self.match(TokenType.RENDER):
                self.advance()
                self.expect(TokenType.COLON)
                render_token = self.expect_identifier_or_keyword()
                render = render_token.value
                self.skip_newlines()
```

Finally, locate the `return ir.SurfaceSpec(...)` call at the bottom of the method (where the parsed values are passed to the constructor) and add `render=render` to its keyword arguments. The exact line is at the end of `parse_surface` — search for `SurfaceSpec(` in the method.

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/core/test_render_clause_parsing.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/surface.py tests/unit/core/test_render_clause_parsing.py
git commit -m "feat(parser): handle render: clause in surface declarations"
```

---

### Task 5: Workspace region parser handles `render:` clause

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/workspace.py` (`parse_workspace_region` method, around line 1316)
- Test: `tests/unit/core/test_render_clause_parsing.py` (append)

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_workspace_region_parser_accepts_render_clause() -> None:
    src = """
module test
app demo "Demo"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list

workspace ops "Ops":
  region tasks:
    source: Task
    render: fragment
"""
    module = parse_dsl(src)
    workspaces = module.workspaces
    assert len(workspaces) == 1
    region = workspaces[0].regions[0]
    assert region.render == "fragment"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/core/test_render_clause_parsing.py::test_workspace_region_parser_accepts_render_clause -v
```

Expected: FAIL — parser ignores the `render:` clause inside region.

- [ ] **Step 3: Add the parser branch**

In `src/dazzle/core/dsl_parser_impl/workspace.py`, inside `parse_workspace_region` (around line 1316), follow the same pattern as Task 4:

a) Add `render: str | None = None` to the local variable initialisers at the top.

b) Add an `elif self.match(TokenType.RENDER):` branch in the dispatch loop. Locate it next to existing optional clauses like `display:` or `source:`:

```python
            elif self.match(TokenType.RENDER):
                self.advance()
                self.expect(TokenType.COLON)
                render_token = self.expect_identifier_or_keyword()
                render = render_token.value
                self.skip_newlines()
```

c) Add `render=render` to the `WorkspaceRegion(...)` constructor call at the end of the method.

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/core/test_render_clause_parsing.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/workspace.py tests/unit/core/test_render_clause_parsing.py
git commit -m "feat(parser): handle render: clause in workspace regions"
```

---

## Phase D — Renderer registry

### Task 6: Add RendererRegistry class

**Files:**
- Modify: `src/dazzle/render/fragment/registry.py` (existing file; add a new class)
- Modify: `src/dazzle/render/fragment/__init__.py` (export the new class)
- Test: `tests/unit/render/fragment/test_renderer_registry.py` (new)

The existing `PrimitiveRegistry` and `RendererRegistry` are sibling concepts: registries indexed by name. They live in the same module so they share the same registration-error semantics.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/render/fragment/test_renderer_registry.py`:

```python
"""RendererRegistry contract tests."""

from typing import Protocol

import pytest

from dazzle.render.fragment.errors import PrimitiveRegistrationError
from dazzle.render.fragment.registry import RendererRegistry


class _FakeRenderer:
    """Minimal stub satisfying the renderer protocol."""

    def render(self, fragment: object, ctx: object | None = None) -> str:
        return "<stub/>"


def test_register_and_resolve() -> None:
    registry = RendererRegistry()
    handler = _FakeRenderer()
    registry.register(name="stub", handler=handler)
    assert registry.resolve("stub") is handler


def test_duplicate_registration_rejected() -> None:
    registry = RendererRegistry()
    registry.register(name="dup", handler=_FakeRenderer())
    with pytest.raises(PrimitiveRegistrationError, match="already registered"):
        registry.register(name="dup", handler=_FakeRenderer())


def test_resolve_unknown_returns_none() -> None:
    registry = RendererRegistry()
    assert registry.resolve("absent") is None


def test_registered_names_listing() -> None:
    registry = RendererRegistry()
    registry.register(name="a", handler=_FakeRenderer())
    registry.register(name="b", handler=_FakeRenderer())
    assert sorted(registry.registered_names()) == ["a", "b"]
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/render/fragment/test_renderer_registry.py -v
```

Expected: FAIL with `ImportError: cannot import name 'RendererRegistry'`.

- [ ] **Step 3: Add the class**

In `src/dazzle/render/fragment/registry.py`, append (after the existing `primitive` decorator):

```python
class RendererRegistry:
    """Mutable registry mapping renderer names to handler instances.

    Registration happens at startup; resolution at request-time. The
    resolved handler is the object whose `render(fragment, ctx)` method
    the dispatcher calls when an IR node carries `render: <name>`.

    Sibling to `PrimitiveRegistry` (in this module). Reuses
    `PrimitiveRegistrationError` for duplicate-name rejection so callers
    can catch one exception type for both registries.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, object] = {}

    def register(self, *, name: str, handler: object) -> None:
        if name in self._handlers:
            existing = self._handlers[name]
            raise PrimitiveRegistrationError(
                f"renderer {name!r} already registered to {existing!r}; "
                f"cannot re-register to {handler!r}"
            )
        self._handlers[name] = handler

    def resolve(self, name: str) -> object | None:
        return self._handlers.get(name)

    def registered_names(self) -> list[str]:
        return list(self._handlers.keys())
```

In `src/dazzle/render/fragment/__init__.py`, add `RendererRegistry` to the imports and to `__all__`:

```python
from dazzle.render.fragment.registry import (
    DEFAULT_REGISTRY,
    PrimitiveRegistry,
    RendererRegistry,
    primitive,
)
```

And in `__all__`, add `"RendererRegistry"` near `"PrimitiveRegistry"`.

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/render/fragment/test_renderer_registry.py -v
```

Expected: 4 PASS.

```bash
mypy src/dazzle/render --strict
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/registry.py src/dazzle/render/fragment/__init__.py tests/unit/render/fragment/test_renderer_registry.py
git commit -m "feat(render): RendererRegistry alongside PrimitiveRegistry"
```

---

## Phase E — Linker validation

### Task 7: Linker rejects unknown renderer names

**Files:**
- Modify: `src/dazzle/core/linker.py` (or `linker_impl.py` — pick the file that orchestrates surface/region validation)
- Test: `tests/unit/core/test_render_clause_linking.py` (new)

The linker validates IR after parsing. We need a new check: any `render` field that's set must reference a name in the renderer registry.

But the linker doesn't know about runtime registries. There are two reasonable shapes:

**Option A:** Pass the renderer registry into the linker (as we already pass other things). This makes validation a runtime decision.

**Option B:** Hardcode an allowlist of known renderer names at link time (`{"jinja", "fragment"}`), and let the runtime registry enforce more granularly when serving.

We pick **Option A** — the registry is the single source of truth, and link-time validation should reject typos before serving begins. The registry is constructed at runtime startup (Task 9) before linking happens.

For testability, the linker accepts a `known_renderers: set[str] | None = None` parameter; if `None`, the validation is skipped (preserves behaviour for tests/tools that don't care). Production callers always pass the populated set.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/core/test_render_clause_linking.py`:

```python
"""Linker validation: render: references resolve to known renderer names."""

import pytest

from dazzle.core.dsl_parser import parse_dsl
from dazzle.core.linker import build_appspec, RenderValidationError


_DSL_BASE = """
module test
app demo "Demo"

entity Task "Task":
  id: uuid pk
  title: str(200)
"""


def _parse(extra: str):
    return parse_dsl(_DSL_BASE + extra)


def test_linker_accepts_known_renderer_on_surface() -> None:
    module = _parse("""
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: fragment
""")
    appspec = build_appspec([module], root_module_name="test", known_renderers={"jinja", "fragment"})
    assert appspec.surfaces[0].render == "fragment"


def test_linker_rejects_unknown_renderer_on_surface() -> None:
    module = _parse("""
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: moonbeam
""")
    with pytest.raises(RenderValidationError, match="unknown renderer 'moonbeam'"):
        build_appspec([module], root_module_name="test", known_renderers={"jinja", "fragment"})


def test_linker_skips_render_validation_when_no_registry_supplied() -> None:
    """Backwards-compatible default for non-runtime callers (lint, tests)."""
    module = _parse("""
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: anything_at_all
""")
    appspec = build_appspec([module], root_module_name="test", known_renderers=None)
    assert appspec.surfaces[0].render == "anything_at_all"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/core/test_render_clause_linking.py -v
```

Expected: FAIL — `RenderValidationError` doesn't exist; `known_renderers` kwarg unrecognised.

- [ ] **Step 3: Add the linker validation**

In `src/dazzle/core/linker.py`:

a) Define a new error class near the top of the file:

```python
class RenderValidationError(ValueError):
    """A `render:` clause referenced a renderer that is not registered."""
```

b) Update the `build_appspec` signature to accept the registry hint:

```python
def build_appspec(
    modules: list[ir.ModuleIR],
    root_module_name: str,
    *,
    known_renderers: set[str] | None = None,
) -> ir.AppSpec:
```

c) After the existing build phases (surfaces, workspaces, etc. are assembled), but before the final `return ir.AppSpec(...)`, add a validation pass:

```python
    if known_renderers is not None:
        _validate_render_references(surfaces, workspaces, known_renderers)
```

Where `workspaces` is whichever local variable holds the assembled workspace list. (Search the file for the existing `surfaces` accumulator and find the workspace equivalent — they're typically built in the same phase.)

d) Add the helper near the bottom of the file (or in `linker_impl.py` if the file convention prefers helpers there):

```python
def _validate_render_references(
    surfaces: list[ir.SurfaceSpec],
    workspaces: list[ir.WorkspaceSpec],
    known: set[str],
) -> None:
    for s in surfaces:
        if s.render is not None and s.render not in known:
            raise RenderValidationError(
                f"surface {s.name!r}: unknown renderer {s.render!r}; "
                f"registered renderers: {sorted(known)}"
            )
    for ws in workspaces:
        for r in ws.regions:
            if r.render is not None and r.render not in known:
                raise RenderValidationError(
                    f"workspace {ws.name!r} region {r.name!r}: "
                    f"unknown renderer {r.render!r}; "
                    f"registered renderers: {sorted(known)}"
                )
```

(Adjust attribute access to match the actual `WorkspaceSpec.regions` field name; check `src/dazzle/core/ir/workspaces.py`.)

e) Export `RenderValidationError` from `src/dazzle/core/linker.py` (or wherever the existing public symbols live).

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/core/test_render_clause_linking.py -v
```

Expected: 3 PASS.

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

Expected: no regressions in the wider test suite.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/linker.py tests/unit/core/test_render_clause_linking.py
git commit -m "feat(linker): validate render: references against known renderer set"
```

---

## Phase F — Runtime wiring

### Task 8: Add registries to RuntimeServices

**Files:**
- Modify: `src/dazzle_http/runtime/services.py`
- Test: `tests/unit/runtime/test_runtime_renderer_registries.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/unit/runtime/test_runtime_renderer_registries.py`:

```python
"""RuntimeServices carries the renderer and primitive registries."""

from dazzle.render.fragment.registry import PrimitiveRegistry, RendererRegistry
from dazzle_http.runtime.services import RuntimeServices


def test_runtime_services_has_renderer_registry() -> None:
    services = RuntimeServices()
    assert isinstance(services.renderer_registry, RendererRegistry)


def test_runtime_services_has_primitive_registry() -> None:
    services = RuntimeServices()
    assert isinstance(services.primitive_registry, PrimitiveRegistry)


def test_runtime_services_registries_are_independent_per_instance() -> None:
    """Each RuntimeServices instance gets its own registry — no shared state."""
    a = RuntimeServices()
    b = RuntimeServices()
    a.renderer_registry.register(name="x", handler=object())
    assert b.renderer_registry.resolve("x") is None
```

(Create `tests/unit/runtime/__init__.py` if it doesn't already exist.)

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_runtime_renderer_registries.py -v
```

Expected: FAIL — `RuntimeServices` has no `renderer_registry` attribute.

- [ ] **Step 3: Add the fields**

In `src/dazzle_http/runtime/services.py`:

a) Add the imports at the top (after the existing imports):

```python
from dazzle.render.fragment.registry import PrimitiveRegistry, RendererRegistry
```

b) Add the two fields to the `RuntimeServices` dataclass, near the existing `event_bus` and `presence_tracker`:

```python
    renderer_registry: RendererRegistry = field(default_factory=RendererRegistry)
    primitive_registry: PrimitiveRegistry = field(default_factory=PrimitiveRegistry)
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_runtime_renderer_registries.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/services.py tests/unit/runtime/test_runtime_renderer_registries.py tests/unit/runtime/__init__.py
git commit -m "feat(runtime): renderer + primitive registries on RuntimeServices"
```

---

### Task 9: Default renderer adapters + startup registration

**Files:**
- Create: `src/dazzle_http/runtime/renderers/__init__.py`
- Create: `src/dazzle_http/runtime/renderers/jinja.py`
- Create: `src/dazzle_http/runtime/renderers/fragment.py`
- Create: `src/dazzle_http/runtime/renderers/init.py`
- Test: `tests/unit/runtime/test_renderer_default_registration.py` (new)

These are thin adapters. The Jinja adapter wraps the existing rendering path (it doesn't replace it — Jinja stays the actual default in Plan 2). The Fragment adapter wraps `FragmentRenderer` from Plan 1. Both register against `services.renderer_registry`.

- [ ] **Step 1: Write failing test**

Create `tests/unit/runtime/test_renderer_default_registration.py`:

```python
"""Default Jinja and Fragment renderers register at startup."""

from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle_http.runtime.renderers.init import register_default_renderers
from dazzle_http.runtime.services import RuntimeServices


def test_register_default_renderers_adds_jinja_and_fragment() -> None:
    services = RuntimeServices()
    register_default_renderers(services)
    assert sorted(services.renderer_registry.registered_names()) == ["fragment", "jinja"]


def test_fragment_handler_is_a_FragmentRenderer() -> None:
    services = RuntimeServices()
    register_default_renderers(services)
    handler = services.renderer_registry.resolve("fragment")
    assert isinstance(handler, FragmentRenderer)


def test_default_registration_is_idempotent_in_practice() -> None:
    """Calling twice on the same services raises (registry rejects duplicates)."""
    import pytest
    from dazzle.render.fragment.errors import PrimitiveRegistrationError
    services = RuntimeServices()
    register_default_renderers(services)
    with pytest.raises(PrimitiveRegistrationError):
        register_default_renderers(services)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_renderer_default_registration.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle_http.runtime.renderers'`.

- [ ] **Step 3: Create the adapter package**

```python
# src/dazzle_http/runtime/renderers/__init__.py
"""Renderer adapters that plug into RuntimeServices.renderer_registry."""
```

```python
# src/dazzle_http/runtime/renderers/jinja.py
"""Jinja renderer adapter — wraps the existing template-rendering path.

This adapter exists so that the renderer registry has a uniform interface
across Jinja, Fragment, and any future renderer (PDF, native). The Plan 2
scope deliberately does NOT route requests through the registry — Jinja
remains the request-time default. This adapter is a placeholder ensuring
`register_default_renderers` produces a complete registry.
"""

from typing import Any


class JinjaRenderer:
    """Stub adapter for the existing Jinja rendering path.

    Plan 2 registers this object so the registry has a `"jinja"` entry; the
    actual Jinja invocation continues to live in the legacy rendering code.
    Plan 3 connects the registry to the request path, at which point this
    adapter will gain a real `render(fragment, ctx)` method that dispatches
    to the existing template rendering.
    """

    def render(self, fragment: Any, ctx: Any | None = None) -> str:
        raise NotImplementedError(
            "JinjaRenderer.render is not yet wired up; Plan 2 registers the "
            "adapter for completeness but does not route requests through it. "
            "The legacy Jinja rendering path remains active."
        )
```

```python
# src/dazzle_http/runtime/renderers/fragment.py
"""Fragment renderer adapter — wraps `dazzle.render.fragment.renderer.FragmentRenderer`.

Re-exported here so the registration site has a stable adapter import even
if the underlying renderer package reorganises in future. Today this is a
trivial re-export; Plan 3 may add per-request token resolution here.
"""

from dazzle.render.fragment.renderer import FragmentRenderer


__all__ = ["FragmentRenderer"]
```

```python
# src/dazzle_http/runtime/renderers/init.py
"""Default renderer registration — called once at app startup.

`register_default_renderers(services)` populates the renderer registry with
the framework defaults: Jinja (legacy path, stub adapter) and Fragment
(typed substrate from Plan 1). Apps may register additional renderers
after this call (e.g. Penny Dreadful's `cytoscape_3d`).
"""

from dazzle_http.runtime.renderers.fragment import FragmentRenderer
from dazzle_http.runtime.renderers.jinja import JinjaRenderer
from dazzle_http.runtime.services import RuntimeServices


def register_default_renderers(services: RuntimeServices) -> None:
    """Register the framework default renderers on `services`.

    Idempotent in spirit but not in implementation — calling twice on the
    same services raises `PrimitiveRegistrationError` because the registry
    rejects duplicate names. Tests should construct fresh `RuntimeServices`
    instances rather than reuse and re-register.
    """
    services.renderer_registry.register(name="jinja", handler=JinjaRenderer())
    services.renderer_registry.register(name="fragment", handler=FragmentRenderer())
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_renderer_default_registration.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/renderers tests/unit/runtime/test_renderer_default_registration.py
git commit -m "feat(runtime): default Jinja+Fragment renderer registration"
```

---

### Task 10: Hook startup registration into the live runtime

**Files:**
- Modify: the runtime startup path that constructs `RuntimeServices`. Search for the call site:
  ```bash
  grep -rn "RuntimeServices()" src/dazzle_http/ src/dazzle/cli/ 2>/dev/null
  ```
  Typical sites: `src/dazzle_http/runtime/server.py` or `src/dazzle/cli/serve.py`. Use whichever is the canonical app-startup entry.

- [ ] **Step 1: Locate the construction site**

Run:
```bash
grep -rn "RuntimeServices()" src/dazzle_http/ src/dazzle/cli/ src/dazzle_http/runtime/
```

Identify the file where `RuntimeServices` is constructed and attached to `app.state`. There may be more than one (test fixtures, etc.) — focus on the production path.

- [ ] **Step 2: Add the registration call**

After `services = RuntimeServices()`, add:

```python
from dazzle_http.runtime.renderers.init import register_default_renderers
register_default_renderers(services)
```

(Or import at the top of the file — either is fine, follow local convention.)

- [ ] **Step 3: Verify the existing serve path still works**

```bash
cd examples/simple_task && timeout 10 dazzle serve --local 2>&1 | tail -20
```

Expected: the app boots without error. The existing UI should still render via Jinja. Look for `INFO ... Application startup complete.` or equivalent. If there's an error in the registration path, fix before committing.

(If `dazzle serve` is too heavy for a fast iteration, instead run a smaller smoke test that constructs the runtime services as production does — search for an existing `tests/integration/test_runtime_smoke.py`-style test and emulate its pattern.)

Run the full unit suite to catch any test that reaches the runtime services and now sees the new registries:

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

Expected: no new failures.

- [ ] **Step 4: Commit**

```bash
git add <the modified startup file>
git commit -m "feat(runtime): register default renderers at app startup"
```

---

## Phase G — End-to-end smoke

### Task 11: Linker integration with live registry

**Files:**
- Modify: the production call to `build_appspec` (search: `grep -rn "build_appspec(" src/`). The site that does linking *at runtime* (rather than from `dazzle validate` CLI) needs to pass `known_renderers` derived from `services.renderer_registry.registered_names()`.
- Test: `tests/integration/test_render_default_unchanged.py` (new)

- [ ] **Step 1: Write the smoke test**

Create `tests/integration/test_render_default_unchanged.py`:

```python
"""End-to-end smoke: simple_task boots, validates, and renders unchanged
under the default (no `render:` clauses anywhere) configuration."""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser import parse_dsl
from dazzle.core.linker import build_appspec, RenderValidationError


SIMPLE_TASK_DSL = Path(__file__).parent.parent.parent / "examples" / "simple_task"


def _load_simple_task_dsl() -> str:
    """Concatenate all .dsl files in the example into a single source string."""
    files = sorted(SIMPLE_TASK_DSL.glob("**/*.dsl"))
    if not files:
        pytest.skip(f"simple_task example not found at {SIMPLE_TASK_DSL}")
    return "\n\n".join(f.read_text() for f in files)


def test_simple_task_links_with_known_renderers() -> None:
    """The example app has no render: clauses; linking must succeed."""
    src = _load_simple_task_dsl()
    module = parse_dsl(src)
    appspec = build_appspec([module], root_module_name="simple_task", known_renderers={"jinja", "fragment"})
    assert appspec is not None
    # No surface in simple_task should declare a render override.
    for s in appspec.surfaces:
        assert s.render is None, f"surface {s.name} has unexpected render={s.render!r}"


def test_simple_task_links_when_render_validation_disabled() -> None:
    """Backwards compat: passing known_renderers=None must not break the
    pre-Plan-2 validate path."""
    src = _load_simple_task_dsl()
    module = parse_dsl(src)
    appspec = build_appspec([module], root_module_name="simple_task", known_renderers=None)
    assert appspec is not None


def test_unknown_renderer_in_added_clause_is_caught() -> None:
    """Inject a `render: moonbeam` clause and confirm linking rejects it."""
    src = _load_simple_task_dsl()
    # Add a render clause to the first surface declaration via string append.
    # If simple_task doesn't have a parseable surface block this falls
    # through to a synthetic minimal app.
    test_module_src = """
module synthetic
app demo "Demo"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
  render: moonbeam
"""
    module = parse_dsl(test_module_src)
    with pytest.raises(RenderValidationError, match="unknown renderer 'moonbeam'"):
        build_appspec([module], root_module_name="synthetic", known_renderers={"jinja", "fragment"})
```

(Create `tests/integration/__init__.py` if it doesn't already exist.)

- [ ] **Step 2: Run to verify**

```bash
pytest tests/integration/test_render_default_unchanged.py -v
```

Expected: 3 PASS. If the simple_task DSL load fails (path or skipping), debug the path resolution; the test must run, not skip silently.

- [ ] **Step 3: Find and update production link-time call site**

```bash
grep -rn "build_appspec(" src/dazzle_http/ src/dazzle/cli/ src/dazzle/agent/ src/dazzle/mcp/ 2>/dev/null
```

For each call site that runs at request-time or app-boot-time (NOT call sites in tests, validators, or read-only tools), pass the populated registry names:

```python
appspec = build_appspec(
    modules,
    root_module_name=...,
    known_renderers=set(services.renderer_registry.registered_names()),
)
```

If a call site doesn't have access to `services` directly, pass it through whatever orchestrator owns the call. If a call site is genuinely tooling (lint, MCP read-only), leave `known_renderers=None` (the legacy path).

- [ ] **Step 4: Run the full test suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

Expected: no regressions.

```bash
mypy src/dazzle/render --strict
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_render_default_unchanged.py tests/integration/__init__.py <production call-site files>
git commit -m "feat(linker): wire renderer registry into runtime link-time validation"
```

---

## Plan completion checklist

After Task 11 is committed:

- [ ] `pytest tests/unit/render/ tests/unit/core/test_render_clause_*.py tests/unit/runtime/ tests/integration/test_render_default_unchanged.py -v` — all pass.
- [ ] `pytest tests/ -m "not e2e"` — no regressions outside the new tests.
- [ ] `mypy src/dazzle/render --strict` — clean.
- [ ] `mypy src/dazzle src/dazzle_http --ignore-missing-imports` — no new errors over the pre-existing baseline.
- [ ] `ruff check src/ tests/ && ruff format --check src/ tests/` — clean.
- [ ] Boot `examples/simple_task` via `dazzle serve --local` (or equivalent fast smoke); confirm the UI renders unchanged. Default render path is still Jinja; no surface has flipped.
- [ ] Confirm `git status` clean.
- [ ] **Stop condition met:** all existing examples still serve unchanged. The `render:` clause exists, parses, lints, and routes through the registry — but no surface in the framework or examples uses it. Plan 3 is the next step.

---

## Self-Review

**Spec coverage:**
- Spec §3 (renderer dispatch + `render:` DSL) → Tasks 1 (lexer), 2–3 (IR), 4–5 (parser), 6 (registry), 7 (linker), 8–10 (runtime wiring), 11 (live integration).
- Spec §5 (primitive registration API) → Already shipped in Plan 1 Task 8 (`PrimitiveRegistry` + `@primitive` decorator); this plan only attaches it to `RuntimeServices` (Task 8). No new registration logic here.
- Spec §4 (Jinja interop), §6 (token integration), §7 (htmx integration), §8 (anti-Turing boundary) → Either shipped in Plan 1 or out of scope until Plan 3.
- Spec §9 phase plan: this is Plan 2 = spec Phase 4. The "stop condition" ("All existing examples still serve unchanged") is enforced by the smoke test in Task 11.

**Placeholder scan:**
- No "TBD"/"TODO"/"implement later" anywhere except the placeholder issue-number markers `(#TBD)` in the IR field comments — those are intentional and will be replaced when an issue number is assigned. Acceptable for plan delivery.
- All file paths are exact; the linker tasks (7, 11) explicitly note the `grep -rn` step for locating call sites because there are multiple plausible sites and the engineer should not have to guess.
- Every step contains complete code or a complete command.

**Type consistency:**
- `RendererRegistry` defined in Task 6 with `register(name, handler)` / `resolve(name) -> object | None` / `registered_names() -> list[str]` — used consistently in Tasks 8, 9, 10, 11.
- `RenderValidationError` defined in Task 7 — referenced in Task 11.
- `register_default_renderers(services)` defined in Task 9 — called in Task 10.
- The `known_renderers: set[str] | None = None` linker parameter in Task 7 matches the call sites in Task 11.

**Scope check:**
- Plan covers spec Phase 4. Self-contained: end state is production runtime aware of the registry but defaulting to Jinja. Plan 3 is its own unit of work.
