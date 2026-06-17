# ADR-0038 — Rendering layer boundary: `render/` is pure and acyclic

**Status:** Accepted (2026-06-17). Implementation in progress on branch `htmx4-eval` (region_adapter
relocation + layering drift-test).
**Completes:** ADR-0011 (SSR + htmx — no SPA) and ADR-0023 (typed Fragment emission). This ADR does not
change *what* HTML we produce or *how* (f-strings + `dazzle.render.html.esc`); it fixes *where* the
producing code lives and makes the existing-but-unenforced layer rule a live gate.
**Origin:** surfaced during the htmx 4 evaluation (`docs/evaluation/back-ui-render-boundary.md`), which
found ~5,400 LOC of rendering in the HTTP package and cycle-dodging lazy imports.
**Continues:** issue **#1086**, which already migrated `template_renderer`/`template_context`/
`surface_access`/`access_evaluator`/`page_builder`/`dispatch` from `ui`/`back` into `dazzle.render` and
locked in `ui/ ↛ back/` via `tests/unit/test_import_boundaries.py`. That test's docstring lists the
`render→ui`/`back→ui` helpers (incl. `condition_eval`, `region_adapter` neighbours) as **explicit
future work**. This ADR executes the next slice of that plan — the `render/` subtree specifically — and
extends the same test to cover it.

## Context

Dazzle's runtime is a four-layer stack, by dependency direction:

```
back/    FastAPI runtime: routes, auth, DB, handlers, the HX-* contract   (the app — 422 files)
  │ → ui, → render
ui/      page/route renderers (*_renderer.py) + static JS/CSS + converters  (59 files)
  │ → render
render/  pure AppSpec→Fragment→HTML: html.esc, context, filters, primitives (45 files)
  │ → core
core/    Parser / IR / AppSpec
```

The intended invariant — **`back → ui → render → core`, acyclic; `render/` and `ui/` never import
`back/`** — is already written down (verbatim in `render/onboarding/__init__.py`, and `render/
onboarding` was deliberately split *out* of `back` to honor it). It is the right boundary for an SSR
framework: it lets the HTML-producing layer be pure, deterministic, and unit-testable without booting a
server — the property the typed-Fragment substrate (ADR-0023) depends on.

Two defects undermine it today:

1. **Misplaced pure rendering.** `back/runtime/renderers/region_adapter/` (10 modules, 3,239 LOC) and
   `back/runtime/workspace_card_bodies.py` (436 LOC) are pure rendering — they import only
   `dazzle.render.fragment`, `dazzle.core.ir`, `html.escape`, and stdlib; zero repo/session/`await`/
   `Request`/SQL. They sit in the HTTP layer for no structural reason.

2. **Cycle-dodging back-edges.** Because that pure code lives in `back/`, the genuinely-pure `render/`
   layer reaches *up* into it. The only way that survives import time is **lazy in-function imports** —
   the canonical "we have a circular dependency and are hiding it" smell. The complete violation set:
   - `render/fragment/renderer/_render_tables.py` → `back…region_adapter` (×2, lazy)
   - `render/fragment/renderer/_render_charts.py` → `back…region_adapter` (×2, lazy)
   - `render/dispatch.py` → `ui.utils.condition_eval` (×1, lazy)

Nothing enforces the rule, so the regressions drifted in unnoticed. Per the Model-Driven Failure-Modes
review rule, a documented-but-not-live detector is a known weak spot — this is one.

**Agent impact (why this is worth fixing now, not someday):** with rendering smeared across three
packages, "where is HTML produced?" has three answers — one counter-intuitively in the HTTP layer — so
a coding agent (or a workflow fan-out) cannot scope a markup change to one package or verify it in
isolation. It must trace `back → ui → render` plus the hidden back-edges. The htmx 4 evaluation hit
exactly this. A clean boundary gives the crisp routing rule "markup → `render/` (test serverless);
route/data/auth → `back/`."

## Decision

### D1 — `render/` is the single home for pure rendering; it imports only `render`, `core`, stdlib/3p

No HTML-producing code that lacks an I/O reason lives in `back/` or `ui/`. `render/` must not import
`dazzle.ui` or `dazzle.back` — at module top level **or** inside functions. Lazy imports do not launder
a layer violation; they hide it.

### D2 — Relocate the misplaced subsystems into `render/` (and pure helpers to their layer)

Relocations (clean break, no shims — ADR-0003; the existing test suite is the behavioral oracle):
- `back/runtime/renderers/region_adapter/` → `render/fragment/region/` (10 modules) — eliminates the
  `render→back` edges from `_render_tables.py`/`_render_charts.py` (they become `render`-internal).
- `back/runtime/workspace_card_bodies.py` → `render/fragment/region/` — pure (`core.ir` + stdlib);
  region_adapter and two `back` fetchers import it (the latter as legal `back→render`).
- `_resolve_row_links` (pure stdlib helper, currently in `back/runtime/renderers/fragment_adapter.py`)
  → a `render/fragment/region/` helper — shared by the moved region_adapter and by `back`'s standalone
  list path (which now imports it as `back→render`).
- `ui/utils/condition_eval.py` → `core/condition_eval.py` — pure (`datetime` + `core.comparison`); its
  natural home is `core` (the lowest layer, importable by everyone). Resolves the `render→ui` edge in
  `render/dispatch.py` and also advances #1086's `back→ui` cleanup (back imports it too).

`back/` keeps calling all of this — the `back → render`/`back → core` direction is legal and already
has ~48 sites. **Out of scope (remains #1086 future work):** the broader `back→ui` helper list
(`theme`, `css_loader`, `htmx`, `app_chrome`, `site_renderer`, `workspace_renderer`, …) and folding the
`ui/runtime/*_renderer.py` page layer down (see D4).

### D3 — The boundary is enforced by extending the existing live boundary test

`tests/unit/test_import_boundaries.py` (from #1086) already enforces `ui/ ↛ back/` and `back/ ↛`
migrated-render-modules, scanning the `ui/` and `back/` subtrees. This ADR **extends that same test** to
also scan `src/dazzle/render/**` and fail on any import (top-level **or** in-function/lazy — the current
scanner is line-regex; the extension must catch indented imports too) of a higher layer: `render/` ↛
{`ui`, `back`}. No new test file (avoids two parallel boundary gates) and no new dependency. This keeps
the detector *live in the normal workflow* (the failure-modes rule's bar), so the rule cannot silently
regress again.

### D4 — The `ui/runtime/*_renderer.py` page-orchestration sub-seam is kept

`ui/runtime`'s page/detail/experience/workspace/site renderers legitimately coordinate route- and
context-level concerns and call *down* into `render/`. "Orchestration in `ui`, primitives in `render`"
is a deliberate sub-seam, not a violation, and is **not** folded into `render/` by this ADR.

## Consequences

- `render/` becomes importable and testable with zero `back/` surface — pure-rendering unit tests no
  longer risk dragging in the FastAPI runtime.
- The htmx 4 migration (`docs/evaluation/htmx4-evaluation.md`) shrinks: one rendering path and one home
  for the htmx contract instead of three.
- Imports in `back/` that previously referenced `back.runtime.renderers.region_adapter` /
  `workspace_card_bodies` now reference `render.fragment.region`. This is a clean-break rename across
  call sites in the same change (ADR-0003).
- A new always-on test gate fails any future `render→ui/back` or `ui→back` import. Contributors adding
  such an edge must instead move the shared code down a layer or invert the dependency.

## Failure-modes check (per CLAUDE.md review rule)

1. *Mode risked?* — None increased; this **reduces** "side code drifts from the model" risk by
   consolidating rendering and forbidding hidden cross-layer coupling.
2. *Detector?* — The layering drift-test (D3).
3. *Live?* — Yes: a `pytest` in the normal `not e2e` suite, run pre-ship and in CI.
4. *Traceable to DSL/AppSpec?* — Unchanged; relocation is structural, rendering semantics identical.
5. *Preserves semantics?* — Yes; pure move, no behavior change, existing tests are the oracle.

## Open questions (resolved at implementation)

- Target dir `render/fragment/region/` vs `render/region/` — chose `render/fragment/region/` (it is
  Fragment-emitting code; keeps the Fragment surface cohesive).
- `import-linter` vs custom AST test — chose custom (zero new pinned dependency; matches `*_drift.py`).
