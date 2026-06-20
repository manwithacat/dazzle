# Navigation Model Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make navigation a pure function of `(persona, appspec, rbac_matrix)` resolved by one builder, so every page shows the same per-persona sidebar with no dead links — eliminating the three-builder drift in issue #1324 (FR-1 + FR-2 + FR-3).

**Architecture:** A persona binds exactly one nav (`persona X: uses nav Y`); a single `build_persona_nav` (in a new `nav_builder.py`) resolves it (curated → auto-discover fallback → access-filter against the RBAC matrix), precomputed once per persona at app build time and read by both the workspace-page and entity-page renderers. Workspace-level nav (`nav_groups`/`nav_ref`/`uses nav`) is removed (clean break, ADR-0003).

**Tech Stack:** Python 3.12, Pydantic IR, custom recursive-descent DSL parser (`dsl_parser_impl/`), FastAPI + typed-Fragment UI runtime, pytest, mypy, ruff.

**Spec:** design comment on issue #1324 + working copy `dev_docs/2026-06-02-navigation-model-redesign-design.md`.

**Conventions:** type hints required (`mypy src/dazzle` clean); `pytest tests/ -m "not e2e"` green before each ship; `ruff check src/ tests/ --fix && ruff format`; clean breaks, no compat shims (ADR-0003); `/bump patch` + CHANGELOG (+ `### Agent Guidance` when conventions change) + push per slice; staged-IR-first (each slice ships green independently).

---

## File Structure

| File | Responsibility | Slice |
|------|----------------|-------|
| `src/dazzle/core/ir/personas.py` | `PersonaSpec` gains `nav_ref: str \| None` | 1 |
| `src/dazzle/core/dsl_parser_impl/scenario.py` | persona block parses `uses nav <name>` → `nav_ref` | 1 |
| `src/dazzle/core/validator.py` (or the validate module that walks personas) | `persona.nav_ref` must resolve to a declared `nav <name>:` | 1 |
| `src/dazzle/page/converters/nav_builder.py` *(new)* | `NavModel` + `build_persona_nav` + `build_all_persona_navs` (pure) | 2 |
| `src/dazzle/page/runtime/page_routes.py` | renderers read precomputed persona nav; delete 3 old builders + skip-branch | 3 |
| `src/dazzle/page/converters/template_compiler.py` | delete persona-union (`1482-1531`) | 3 |
| `src/dazzle/core/ir/workspaces.py` | remove `WorkspaceSpec.nav_groups` + `nav_ref` | 3 |
| `src/dazzle/core/dsl_parser_impl/workspace.py` | remove workspace `uses nav` + `nav_group` grammar | 3 |
| `src/dazzle/core/linker_impl.py` | delete nav_ref prepend (`1418-1442`) | 3 |
| `examples/` , `tests/` | verify auto-discovery still works; update fixtures/tests | 4 |

**Out of scope (next slice, not planned here):** FR-6 lint (reads `NavModel.auto_discovered` + always-filtered items), FR-4 (`when=`), FR-5 (workspace `primary_actions:`).

---

## Slice 1 — IR + parser + validation (additive; workspace nav untouched)

Purely additive: add the persona binding and its validation. Workspace nav still works, so nothing breaks. Renderers ignore `persona.nav_ref` until Slice 3.

### Task 1.1: `PersonaSpec.nav_ref`

**Files:**
- Modify: `src/dazzle/core/ir/personas.py` (PersonaSpec, fields at `:56-66`)
- Test: `tests/unit/test_personas_ir.py` (create if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_personas_ir.py
from dazzle.core.ir.personas import PersonaSpec


def test_persona_spec_carries_nav_ref():
    p = PersonaSpec(id="teacher", label="Teacher", nav_ref="teaching")
    assert p.nav_ref == "teaching"


def test_persona_spec_nav_ref_defaults_none():
    assert PersonaSpec(id="teacher", label="Teacher").nav_ref is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_personas_ir.py -v`
Expected: FAIL — `PersonaSpec` has no field `nav_ref` (pydantic rejects the kwarg).

- [ ] **Step 3: Add the field**

In `src/dazzle/core/ir/personas.py`, alongside `role: str | None = None` (`:66`):

```python
    # #1324: the persona's single nav binding (`uses nav <name>`). Navigation
    # is per-persona-global — a persona has exactly one sidebar — so this is a
    # scalar, not a list. Resolved by ui/converters/nav_builder.build_persona_nav.
    nav_ref: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_personas_ir.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/personas.py tests/unit/test_personas_ir.py
git commit -m "#1324 PersonaSpec.nav_ref — per-persona nav binding (IR)"
```

### Task 1.2: Parse `uses nav <name>` in the persona block

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/scenario.py` (`_PersonaState` `:460`, `_PERSONA_KEYWORDS` `:579`, `_build_persona` `:609`)
- Test: `tests/unit/test_parser.py` (persona parsing section) or `tests/unit/test_persona_parser.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_persona_parser.py
from dazzle.core.parser import parse_dsl  # the project's parse entry point


def _parse(src: str):
    return parse_dsl(src, file="test.dsl")


def test_persona_uses_nav_binds_nav_ref():
    src = """module m
app a "A"

nav teaching:
  group "Marking":
    item Assignment

persona teacher "Teacher":
  uses nav teaching
"""
    appspec = _parse(src)
    persona = next(p for p in appspec.personas if p.id == "teacher")
    assert persona.nav_ref == "teaching"
```

> If `parse_dsl`/import path differs, mirror an existing persona test in `tests/unit/test_parser.py` (search `parse_persona` / `personas`).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_persona_parser.py -v`
Expected: FAIL — `uses` inside a persona block hits `_on_unknown_persona` (renamed-keyword guard) or `nav_ref` is `None`.

- [ ] **Step 3: Add the keyword parser + state field + builder wiring**

In `scenario.py`, add to `_PersonaState` (after `role`):

```python
    nav_ref: str | None = None  # #1324: `uses nav <name>`
```

Add a token-keyed parser (near the other `_p_kw_*`):

```python
def _p_kw_uses_nav(parser: Any, state: _PersonaState) -> None:
    """``uses nav <name>`` — bind the persona's single nav definition (#1324)."""
    parser.advance()  # consume `uses`
    if not parser.match(TokenType.NAV):
        token = parser.current_token()
        raise make_parse_error(
            "Expected `nav` after `uses` in a persona block (`uses nav <name>`)",
            parser.file,
            token.line,
            token.column,
        )
    parser.advance()  # consume `nav`
    state.nav_ref = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()
```

Register it in `_PERSONA_KEYWORDS`:

```python
_PERSONA_KEYWORDS: dict[TokenType, KeywordParser[_PersonaState]] = {
    TokenType.DESCRIPTION: _p_kw_description,
    TokenType.GOALS: _p_kw_goals,
    TokenType.PROFICIENCY: _p_kw_proficiency,
    TokenType.USES: _p_kw_uses_nav,  # #1324
}
```

Pass it through in `_build_persona`:

```python
        role=state.role,
        nav_ref=state.nav_ref,  # #1324
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_persona_parser.py -v`
Expected: PASS.

- [ ] **Step 5: Run the parser/IR drift + persona suites**

Run: `pytest tests/unit/test_parser.py tests/unit/test_personas_ir.py -q`
Expected: PASS (no regressions in existing persona parsing).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/scenario.py tests/unit/test_persona_parser.py
git commit -m "#1324 parse `uses nav <name>` in persona block -> PersonaSpec.nav_ref"
```

### Task 1.3: Validate `persona.nav_ref` resolves to a declared nav

**Files:**
- Modify: `src/dazzle/core/validator.py` (add a `validate_*` function; wire into the aggregate the same way the ~30 existing validators are — confirm by reading `core/lint.py:lint_appspec` and the validator module)
- Test: `tests/unit/test_validator.py` (or the existing validator test module)

- [ ] **Step 1: Write the failing test**

```python
def test_persona_nav_ref_must_resolve():
    # Build an AppSpec with a persona referencing a nav that doesn't exist.
    # Use the project's parse path; expect a validation error.
    src = """module m
app a "A"
persona teacher "Teacher":
  uses nav nonexistent
"""
    errors = validate_appspec(parse_dsl(src, file="t.dsl"))  # match real signatures
    assert any("nonexistent" in e.message and "nav" in e.message.lower() for e in errors)
```

> Match the real `validate_*` signature and error type by reading an existing validator + its test.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_validator.py -k nav_ref -v`
Expected: FAIL — no validation yet; unresolved nav_ref passes silently.

- [ ] **Step 3: Add the validator**

```python
def validate_persona_nav_refs(appspec: AppSpec) -> tuple[list[ValidationError], list[ValidationWarning]]:
    """#1324: a persona's `uses nav <name>` must reference a declared `nav` def."""
    errors: list[ValidationError] = []
    declared = {n.name for n in getattr(appspec, "navs", []) or []}
    for persona in appspec.personas:
        if persona.nav_ref is not None and persona.nav_ref not in declared:
            errors.append(
                ValidationError(
                    message=(
                        f"persona '{persona.id}' uses nav '{persona.nav_ref}', "
                        f"but no `nav {persona.nav_ref}:` is declared"
                    )
                )
            )
    return errors, []
```

Wire it into the aggregate validator (mirror an adjacent `validate_*` registration).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_validator.py -k nav_ref -v`
Expected: PASS.

- [ ] **Step 5: Full unit gate + mypy**

Run: `pytest tests/ -m "not e2e" -q && mypy src/dazzle`
Expected: PASS; mypy `Success`.

- [ ] **Step 6: Ship slice 1**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
# /bump patch ; update CHANGELOG (### Added: persona `uses nav`, PersonaSpec.nav_ref + validation)
git add -A && git commit -m "#1324 slice 1: persona nav binding + validation (IR/parser/validate)"
git push origin main && git push origin v<new>
```

CHANGELOG note (Added): "persona `uses nav <name>` binding (`PersonaSpec.nav_ref`) + validate-time check; not yet consumed by renderers (slice 1 of #1324)."

---

## Slice 2 — `nav_builder.py`: NavModel + the unified builder (pure, isolated)

Build and fully unit-test the pure builder against synthetic inputs. Not wired to renderers yet.

### Task 2.1: `NavModel` types

**Files:**
- Create: `src/dazzle/page/converters/nav_builder.py`
- Test: `tests/unit/test_nav_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_nav_builder.py
from dazzle.page.converters.nav_builder import NavModel, NavGroup, NavLink


def test_nav_model_is_frozen_and_holds_groups():
    link = NavLink(label="Assignments", route="/a/list/Assignment", icon="file", entity="Assignment")
    group = NavGroup(label="Marking", icon=None, collapsed=False, links=(link,))
    model = NavModel(groups=(group,), auto_discovered=False)
    assert model.groups[0].links[0].entity == "Assignment"
    assert model.auto_discovered is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_nav_builder.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Define the types**

```python
"""Unified per-persona navigation builder (#1324).

Navigation is a pure function of (persona, appspec, rbac_matrix) — all static.
This module is the single source of a persona's sidebar: every page renders the
same precomputed NavModel for the current persona, so the three legacy builders
(workspace-page, entity-page, persona-union) can no longer drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.personas import PersonaSpec
    from dazzle.rbac.matrix import AccessMatrix


@dataclass(frozen=True)
class NavLink:
    label: str
    route: str
    icon: str | None = None
    entity: str | None = None  # target entity/workspace name (filtering + FR-6 lint)


@dataclass(frozen=True)
class NavGroup:
    label: str
    icon: str | None
    collapsed: bool
    links: tuple[NavLink, ...]


@dataclass(frozen=True)
class NavModel:
    groups: tuple[NavGroup, ...]
    auto_discovered: bool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_nav_builder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/page/converters/nav_builder.py tests/unit/test_nav_builder.py
git commit -m "#1324 NavModel types (nav_builder)"
```

### Task 2.2: `build_persona_nav` — curated path

**Files:**
- Modify: `src/dazzle/page/converters/nav_builder.py`
- Test: `tests/unit/test_nav_builder.py`

- [ ] **Step 1: Write the failing test**

```python
def test_curated_nav_resolves_navspec_groups(make_appspec, permit_all_matrix):
    # make_appspec: helper building an AppSpec with a `nav teaching:` def
    # (group "Marking" -> item Assignment) and persona teacher uses nav teaching.
    appspec = make_appspec(
        navs=[("teaching", [("Marking", ["Assignment"])])],
        personas=[("teacher", "teaching")],
        list_surfaces={"Assignment": "/a/list/Assignment"},
    )
    persona = appspec.personas[0]
    model = build_persona_nav(appspec, persona, permit_all_matrix)
    assert model.auto_discovered is False
    assert model.groups[0].label == "Marking"
    assert model.groups[0].links[0].entity == "Assignment"
    assert model.groups[0].links[0].route == "/a/list/Assignment"
```

> Add `make_appspec` and `permit_all_matrix` fixtures to the test module (or `conftest`). `permit_all_matrix` is a stub whose `.get(role, entity, op)` always returns `PolicyDecision.PERMIT`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_nav_builder.py -k curated -v`
Expected: FAIL — `build_persona_nav` undefined.

- [ ] **Step 3: Implement curated resolution + access filter**

```python
from dazzle.rbac.matrix import PolicyDecision  # at module top (runtime import OK in ui)


def _route_for(appspec: AppSpec, target: str) -> str | None:
    """Resolve a nav item target (entity or workspace name) to a route."""
    # workspace target
    for ws in getattr(appspec, "workspaces", []) or []:
        if ws.name == target:
            return f"/workspaces/{ws.name}"
    # entity list-surface target
    for surface in getattr(appspec, "surfaces", []) or []:
        if surface.mode.value == "list" and surface.entity_ref == target:
            return f"/list/{target}"  # match the app's real list route shape in slice 3
    return None


def _persona_can_list(matrix: AccessMatrix, role: str, entity: str) -> bool:
    return matrix.get(role, entity, "list") != PolicyDecision.DENY


def build_persona_nav(appspec: AppSpec, persona: PersonaSpec, matrix: AccessMatrix) -> NavModel:
    if persona.nav_ref is not None:
        nav_def = next((n for n in appspec.navs if n.name == persona.nav_ref), None)
        if nav_def is not None:
            groups = _resolve_curated(appspec, nav_def, persona, matrix)
            return NavModel(groups=tuple(groups), auto_discovered=False)
    groups = _auto_discover(appspec, persona, matrix)  # Task 2.3
    return NavModel(groups=tuple(groups), auto_discovered=True)


def _resolve_curated(appspec, nav_def, persona, matrix) -> list[NavGroup]:
    role = persona.effective_role
    out: list[NavGroup] = []
    for g in nav_def.groups:
        links: list[NavLink] = []
        for item in g.items:
            if not _persona_can_list(matrix, role, item.entity):
                continue  # FR-3: drop dead links
            route = _route_for(appspec, item.entity)
            if route is None:
                continue
            links.append(NavLink(label=item.entity, route=route, icon=item.icon, entity=item.entity))
        if links:
            out.append(NavGroup(label=g.label, icon=g.icon, collapsed=g.collapsed, links=tuple(links)))
    return out
```

> Route shapes (`/list/<entity>`, `/workspaces/<name>`) are placeholders to be reconciled with the real route prefixes in Slice 3 (the renderer already knows `app_prefix`). Keep `_route_for` the single place that knows route shape.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_nav_builder.py -k curated -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/page/converters/nav_builder.py tests/unit/test_nav_builder.py
git commit -m "#1324 build_persona_nav: curated path + access filter (FR-3)"
```

### Task 2.3: Access-filter drops dead links (FR-3)

**Files:**
- Modify/Test: same.

- [ ] **Step 1: Write the failing test**

```python
def test_access_filter_drops_denied_entity(make_appspec, matrix_denying):
    appspec = make_appspec(
        navs=[("teaching", [("Marking", ["Assignment", "Secret"])])],
        personas=[("teacher", "teaching")],
        list_surfaces={"Assignment": "/a/list/Assignment", "Secret": "/a/list/Secret"},
    )
    persona = appspec.personas[0]
    # matrix_denying: DENY for (teacher, Secret, list); PERMIT otherwise
    model = build_persona_nav(appspec, persona, matrix_denying(role="teacher", entity="Secret"))
    entities = [l.entity for g in model.groups for l in g.links]
    assert "Assignment" in entities
    assert "Secret" not in entities  # no dead link
```

- [ ] **Step 2: Run test to verify it fails** — Run: `pytest tests/unit/test_nav_builder.py -k access_filter -v`. Expected: PASS already if Task 2.2 implemented the filter; if it was stubbed, FAIL. (This task exists to pin FR-3 explicitly.)

- [ ] **Step 3:** No new code if Task 2.2 included the filter; otherwise add the `_persona_can_list` guard shown above.

- [ ] **Step 4: Run** — Expected: PASS.

- [ ] **Step 5: Commit** (if changed)

```bash
git commit -am "#1324 test: access-filter drops DENY-listed nav items"
```

### Task 2.4: Auto-discover fallback + `build_all_persona_navs`

**Files:**
- Modify: `src/dazzle/page/converters/nav_builder.py` (reuse `workspace_allowed_personas` from `workspace_converter.py:467`)
- Test: `tests/unit/test_nav_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_auto_discover_when_no_nav_ref(make_appspec, permit_all_matrix):
    appspec = make_appspec(
        workspaces=[("classroom", ["Assignment", "Lesson"])],  # ws -> accessible entities
        personas=[("teacher", None)],  # no nav_ref
        list_surfaces={"Assignment": "/a/list/Assignment", "Lesson": "/a/list/Lesson"},
    )
    model = build_persona_nav(appspec, appspec.personas[0], permit_all_matrix)
    assert model.auto_discovered is True
    entities = {l.entity for g in model.groups for l in g.links}
    assert {"Assignment", "Lesson"} <= entities


def test_build_all_persona_navs_keys_by_persona_id(make_appspec, permit_all_matrix):
    appspec = make_appspec(
        navs=[("teaching", [("Marking", ["Assignment"])])],
        personas=[("teacher", "teaching"), ("admin", None)],
        list_surfaces={"Assignment": "/a/list/Assignment"},
    )
    navs = build_all_persona_navs(appspec, permit_all_matrix)
    assert set(navs) == {"teacher", "admin"}
    assert navs["teacher"].auto_discovered is False
    assert navs["admin"].auto_discovered is True
```

- [ ] **Step 2: Run to verify failure** — Run: `pytest tests/unit/test_nav_builder.py -k "auto_discover or build_all" -v`. Expected: FAIL.

- [ ] **Step 3: Implement fallback + the all-personas precompute**

```python
from dazzle.page.converters.workspace_converter import workspace_allowed_personas


def _auto_discover(appspec: AppSpec, persona: PersonaSpec, matrix: AccessMatrix) -> list[NavGroup]:
    """Union of the persona's accessible workspaces' entity list-surfaces."""
    role = persona.effective_role
    personas = list(getattr(appspec, "personas", []) or [])
    seen: set[str] = set()
    links: list[NavLink] = []
    for ws in getattr(appspec, "workspaces", []) or []:
        allowed = workspace_allowed_personas(ws, personas)  # None = all personas
        if allowed is not None and persona.id not in {p.id for p in allowed}:
            continue
        for region in ws.regions:
            for src in ([region.source] if region.source else []) + list(getattr(region, "sources", []) or []):
                if src in seen or not _persona_can_list(matrix, role, src):
                    continue
                route = _route_for(appspec, src)
                if route is None:
                    continue
                seen.add(src)
                links.append(NavLink(label=src, route=route, entity=src))
    return [NavGroup(label="", icon=None, collapsed=False, links=tuple(links))] if links else []


def build_all_persona_navs(appspec: AppSpec, matrix: AccessMatrix) -> dict[str, NavModel]:
    """Precompute every persona's nav once (link/build time). Keyed by persona.id."""
    return {p.id: build_persona_nav(appspec, p, matrix) for p in getattr(appspec, "personas", []) or []}
```

- [ ] **Step 4: Run to verify pass** — Expected: PASS.

- [ ] **Step 5: Full unit gate + mypy**

Run: `pytest tests/ -m "not e2e" -q && mypy src/dazzle`
Expected: PASS; mypy `Success`.

- [ ] **Step 6: Ship slice 2**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
# /bump patch ; CHANGELOG ### Added: nav_builder (NavModel + build_persona_nav/build_all_persona_navs), not yet wired
git add -A && git commit -m "#1324 slice 2: unified nav_builder (NavModel + per-persona builder, isolated)"
git push origin main && git push origin v<new>
```

---

## Slice 3 — Renderer cutover + removal of the legacy paths (the load-bearing slice)

This is the refactor. It wires the precompute into the runtime, switches both renderers to read `NavModel`, and **then** deletes the three old builders, the persona-union, the skip-branch, the workspace nav grammar/IR, and the linker prepend — atomically, because their consumers are now gone. **Read the current nav-consuming renderer code before writing each replacement.**

### Task 3.1: Precompute + store per-persona navs at app build

**Files:**
- Modify: the UI runtime setup that has the `AppSpec` and builds shared per-request context (find the owner of `appspec` + the RBAC matrix at boot; `generate_access_matrix` at `rbac/matrix.py:519`). Store `dict[str, NavModel]` where page handlers can read it (the same context object that today holds `appspec`).
- Test: `tests/unit/test_nav_builder.py` (a boot-integration test) or a runtime context test.

- [ ] **Step 1:** Read how `page_routes.py` obtains shared state today (search where `appspec`/`personas` reach the handlers — a `RuntimeServices`/`ServerState`/context object per ADR-0005). Identify the single construction point.

- [ ] **Step 2: Write the failing test** — assert that after building the runtime context for a small app, `context.persona_navs["teacher"]` is a `NavModel`. (Match the real context type/attr.)

- [ ] **Step 3:** At that construction point, compute once:

```python
from dazzle.rbac.matrix import generate_access_matrix
from dazzle.page.converters.nav_builder import build_all_persona_navs

persona_navs = build_all_persona_navs(appspec, generate_access_matrix(appspec))
# store on the shared context object (e.g. ServerState/RuntimeServices) as `persona_navs`
```

- [ ] **Step 4: Run** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "#1324 precompute per-persona NavModel at app build (link-time)"
```

### Task 3.2: Workspace-page renderer reads precomputed nav

**Files:**
- Modify: `src/dazzle/page/runtime/page_routes.py` — replace the workspace-page nav builder (`:2465+`) and delete the auto-discovery-skip-when-grouped branch (`:2511`).

- [ ] **Step 1:** Read `page_routes.py:2455-2560` to see how the built `ws_nav_items`/`ws_entity_nav` dicts feed the sidebar fragment. Identify the sidebar render input contract.

- [ ] **Step 2: Write/adjust a test** — a workspace-page render test asserting the sidebar matches the persona's precomputed `NavModel` (same links regardless of whether the page is a workspace page). Use an existing page-render test as the template (search `test_*workspace*` / sidebar tests).

- [ ] **Step 3:** Replace the per-request nav construction with: look up `context.persona_navs[current_persona.id]` and adapt `NavModel` → the sidebar fragment input. Delete the `ws_grouped_entities`/`ws_entity_nav`/skip-branch block (`:2491-2513+`). Keep the workspace *links* if the design wants workspaces as nav destinations — they come from the persona nav now, not a separate builder.

- [ ] **Step 4: Run** the workspace-page render tests — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "#1324 workspace-page renderer reads precomputed persona nav; drop skip-branch"
```

### Task 3.3: Entity-page renderer reads precomputed nav; delete persona-union

**Files:**
- Modify: `src/dazzle/page/runtime/page_routes.py` (`:632-667`)
- Delete: persona-union in `src/dazzle/page/converters/template_compiler.py:1482-1531`

- [ ] **Step 1:** Read `page_routes.py:632-667` and `template_compiler.py:1482-1531` to see the entity-page resolution + union it calls.

- [ ] **Step 2: Write/adjust a test** — entity-page render shows the *same* sidebar as the workspace page for the same persona (the core anti-drift assertion). One test, two page types, identical nav.

- [ ] **Step 3:** Replace the entity-page resolution with `context.persona_navs[current_persona.id]`. Delete the persona-union function in `template_compiler.py` and its call site.

- [ ] **Step 4: Run** entity-page + cross-page tests — Expected: PASS; the drift assertion holds.

- [ ] **Step 5: Commit**

```bash
git commit -am "#1324 entity-page renderer reads precomputed persona nav; delete persona-union"
```

### Task 3.4: Remove workspace nav IR, grammar, and linker prepend (clean break)

**Files:**
- Modify: `src/dazzle/core/ir/workspaces.py` (remove `WorkspaceSpec.nav_groups` `:1238`, `nav_ref` `:1244`)
- Modify: `src/dazzle/core/dsl_parser_impl/workspace.py` (remove the `uses nav` block `:2429-2436` and the `NAV_GROUP/GROUP` handler `:2437-2441`; remove `nav_ref`/`nav_groups` from the workspace state at `:2675`)
- Modify: `src/dazzle/core/linker_impl.py` (delete the nav_ref prepend `:1418-1442`; keep collecting `navs` for the appspec — `build_persona_nav` needs `appspec.navs`)
- Test: update any test asserting workspace nav_groups; add a test that `workspace … : nav_group …` now raises a parse error.

- [ ] **Step 1: Write the failing test** — assert a workspace declaring `nav_group` or `uses nav` raises a parse error (grammar removed).

- [ ] **Step 2: Run** — Expected: FAIL (still parses today).

- [ ] **Step 3:** Remove the fields, the two workspace grammar branches, the workspace-state nav fields, and the linker prepend loop. **Keep** the `navs`/`nav_index` collection in `linker_impl.py` (top-level `nav` defs must still reach `appspec.navs`); only delete the `resolved_workspaces` prepend block (`:1430-1442`), restoring it to a plain pass-through of `symbols.workspaces.values()`.

- [ ] **Step 4: Run** — Expected: PASS (parse error raised; nav defs still collected).

- [ ] **Step 5: Full unit gate + mypy** — Run: `pytest tests/ -m "not e2e" -q && mypy src/dazzle`. Fix fallout (tests/fixtures referencing workspace nav_groups). Expected: PASS; mypy `Success`.

- [ ] **Step 6: Ship slice 3**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
# /bump patch ; CHANGELOG ### Changed + ### Removed + ### Agent Guidance (see below)
git add -A && git commit -m "#1324 slice 3: renderer cutover to unified persona nav; remove workspace nav (clean break)"
git push origin main && git push origin v<new>
```

CHANGELOG:
- **Changed:** "Navigation is now per-persona-global — one sidebar per persona, identical on every page, resolved by `ui/converters/nav_builder.build_persona_nav` and precomputed at app build. Workspace and entity pages can no longer show divergent sidebars (#1324, FR-1/FR-2). Dead links are filtered by LIST access (FR-3)."
- **Removed:** "Workspace-level navigation — `WorkspaceSpec.nav_groups`/`nav_ref`, the `workspace … uses nav` / `nav_group` grammar, and the linker's nav_ref prepend. Bind nav on the persona: `persona X: uses nav Y`."
- **Agent Guidance:** "Author navigation as top-level `nav <name>:` defs bound per persona (`persona X: uses nav Y`); a persona has exactly one sidebar. Do not put `nav_group`/`uses nav` on a workspace (removed). A nav item the persona can't LIST is auto-dropped; a persona with no `uses nav` gets an auto-discovered sidebar (lint will flag this once FR-6 lands)."

---

## Slice 4 — Example/fixture verification + docs

No example/fixture uses curated workspace nav today (verified: zero `uses nav`/`nav_group` matches in `examples/`+`fixtures/`), so this slice is mostly confirming auto-discovery still works and adding one worked example of the new model.

### Task 4.1: Confirm auto-discovery parity on examples

- [ ] **Step 1:** `pytest tests/ -m "not e2e" -q` — confirm the example-app render/lint/discovery tests are green after slice 3 (these exercise auto-discovery, the fallback path).
- [ ] **Step 2:** Boot one example locally (e.g. `examples/simple_task`) and confirm the sidebar renders via auto-discovery (no curated nav). Document the observed nav.
- [ ] **Step 3: Commit** any test adjustments.

### Task 4.2: Add a worked per-persona nav example

- [ ] **Step 1:** Pick a multi-persona example (e.g. `support_tickets` or `ops_dashboard`); add a top-level `nav <name>:` def and bind it on one persona via `uses nav`. Add/extend a render test asserting that persona's sidebar matches the curated def and a second persona still auto-discovers.
- [ ] **Step 2: Run** that example's tests + `dazzle validate` on it — Expected: PASS.
- [ ] **Step 3: Ship slice 4**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
# /bump patch ; CHANGELOG ### Added: worked per-persona nav example
git add -A && git commit -m "#1324 slice 4: worked per-persona nav example + auto-discovery parity"
git push origin main && git push origin v<new>
```

### Task 4.3: Close-out

- [ ] Comment on #1324: FR-1/FR-2/FR-3 shipped (slices 1-4, versions …); FR-6 lint is the next slice (reads `NavModel.auto_discovered` + always-filtered items); FR-4/FR-5 remain open/independent. Leave #1324 open (or convert to an FR-6/FR-4/FR-5 tracking umbrella).

---

## Self-review notes (addressed)

- **Spec coverage:** FR-1 (Slice 3 single builder + cutover), FR-2 (Slice 1 persona binding), FR-3 (Slice 2 access-filter; Tasks 2.2/2.3). FR-6/FR-4/FR-5 explicitly out of scope.
- **Type consistency:** `NavModel`/`NavGroup`/`NavLink` and `build_persona_nav(appspec, persona, matrix)` / `build_all_persona_navs(appspec, matrix)` names are used identically across Tasks 2.x and 3.x. `persona_navs` is the storage attribute name throughout Slice 3.
- **Known integration unknowns (read code, don't guess):** the exact route prefixes in `_route_for` (Slice 3 reconciles with the renderer's `app_prefix`), the shared-context type holding `persona_navs` (Task 3.1 Step 1), and the sidebar fragment input contract (Tasks 3.2/3.3 Step 1). These are flagged as "read first" steps rather than fabricated code, because they depend on current renderer internals the executor must read at task time.
