# back / ui / render boundary assessment

Date: 2026-06-17
Worktree: `.claude/worktrees/htmx4-eval` @ `841ecb9e7` (current `main`)
Method: static import-topology audit. No code changed. Companion to `htmx4-evaluation.md` — the
question arose because the htmx footprint is smeared across all three packages.

> Question being answered: *Is the `dazzle/http` vs `dazzle/page` split meaningful for a server-side
> rendering framework, and does it help coding agents?*

## Verdict

**The layering is real, intended, and mostly sound — but it is not back-vs-ui, it is a four-layer
stack, and one layer is in the wrong package.** The intended model `back → ui → render → core` is
respected ~95% of the time and *is* valuable for an SSR framework (pure, serverless-testable HTML
production separated from I/O). It is undermined by one concrete defect: **~3,700 lines of pure
rendering code sit in `back/` (the HTTP layer)**, which forces the genuinely-pure `render/` layer to
reach *upward* via lazy in-function imports to dodge the resulting cycle. There is **no enforcement
test**, so this drifted in unnoticed. Fix the misplacement + add a layering drift-test and the split
becomes a genuine asset for coding agents. Today it is a net *mild negative* for them.

## What the split actually is

Not two layers — four, by dependency direction (verified import counts, code-only):

```
back/    422 files   FastAPI runtime: routes, auth, DB, handlers, HX-* contract   (the app)
  │ →ui (10)  →render (48)
ui/       59 files   page/route renderers (*_renderer.py) + static JS/CSS + converters
  │ →render (14)  →back (~0)
render/   45 files   pure AppSpec→Fragment→HTML: html.esc, context, filters, fragment primitives
  │ →core (7)
core/                Parser / IR / AppSpec
```

`ui/runtime/*_renderer.py` (workspace/detail/experience/site/template/…) are **live page-orchestration
code**, not dead legacy duplicates — `workspace_renderer` alone is covered by 19 test files and is the
entry point `back/runtime/workspace_route_builder.py` calls. They sit correctly *above* `render/` and
call down into it (`from dazzle.render.fragment import …`, `render.html.esc`, `render.context`). So the
"two parallel renderer stacks" worry is unfounded: it's one stack, layered.

## The defect: rendering LOC by package

| Package | Rendering LOC | Should it be here? |
|---|---|---|
| `render/` | 13,154 | ✅ yes — this is the pure render layer |
| `ui/runtime/*_renderer.py` | 3,757 | ✅ yes — page orchestration above render |
| **`back/runtime/renderers/`** | **5,387** | ❌ **mostly no** — pure rendering in the HTTP layer |

Inside `back/runtime/renderers/`:
- **`region_adapter/`** (10 modules, **3,239 LOC**) — workspace-region builders (charts/metrics/tables/
  cards/timeline/misc + dispatcher + shared). Imports: `dazzle.render.fragment`, `html.escape`,
  stdlib, its own submodules, and `workspace_card_bodies`. **Zero** repo/session/`await`/`Request`/SQL
  references. It is pure rendering.
- **`workspace_card_bodies.py`** (436 LOC) — imports only stdlib + `dazzle.core.ir.conditions`. Also
  pure.

So ≥3,675 LOC of verifiably-pure rendering is mis-homed in `back/`.

## The consequence: cycle-dodging back-edges

Because the pure render layer needs that pure-but-mis-homed code, `render/` imports *up* into `back/`
— and the only way that doesn't explode at import time is to bury the imports inside functions:

| Back-edge | Sites | Form | What it pulls |
|---|---|---|---|
| `render/fragment/renderer/_render_tables.py` → `back…region_adapter` | 2 | **lazy (in-function)** | `_render_status_badge_html` (pure) |
| `render/fragment/renderer/_render_charts.py` → `back…region_adapter` | 2 | **lazy (in-function)** | region adapter builders (pure) |
| `render/dispatch.py` → `ui.utils.condition_eval` | 1 | **lazy (in-function)** | `evaluate_condition` |

That is the **entire** violation set: 3 files, 5 lazy imports. Lazy in-function import is the canonical
"we have a circular dependency and are hiding it" smell; `render/context.py:413` even carries a comment
about dodging a "render→ui import cycle." The team clearly *knows* the layer rule (it's written verbatim
in `render/onboarding/__init__.py`: *"`dazzle.page.*` must not import `dazzle.http.*`"*, and `render/
onboarding` was deliberately split out of `back` to honor it) — there is just nothing stopping
regressions, so a few crept back.

## Does the split help coding agents?

**Today: mild net negative.** Concrete evidence from the htmx audit that prompted this: answering
"how is htmx / form submission wired?" required grepping three packages, and the htmx contract is split
between `ui/runtime/htmx.py` (defines `HtmxDetails` + helpers) and `back/runtime/htmx_response.py`
(re-exports them) with emission in `render/` *and* `ui/`. "Where is HTML produced?" has three answers,
one of them counter-intuitively in the HTTP layer. An agent cannot reason locally; it must trace
`back → ui → render` plus the hidden back-edges.

**Fixed: clear positive.** A clean version — `render/` as the *only* place HTML is produced, no
back-edges, a thin assets-only `ui/`, `back/` purely I/O — gives an agent a crisp routing rule:
- "change the HTML/markup" → `render/`, unit-test serverless
- "change a route / data / auth" → `back/`

That is exactly the kind of boundary that lets an agent (or a workflow fan-out) scope work to one
package and verify it in isolation. The value is real and largely already built; it's ~3,700 misplaced
lines and a missing gate away from paying off. **The split is worth keeping and finishing, not
abandoning.**

## Recommendation

**Two pieces, small relative to the payoff, and both de-risk the htmx 4 migration** (which is expensive
*partly because* rendering is smeared across three packages):

1. **Relocate the pure rendering out of `back/`.** Move `back/runtime/renderers/region_adapter/` and
   `workspace_card_bodies.py` down into `render/` (likely `render/fragment/region/`). They depend only
   downward, so this is mechanical: move modules, flip the lazy `render→back` imports to normal
   top-level `render`-internal imports, update `back`'s import sites (≈48 `back→render` already exist,
   so callers stay in the legal direction). No behavior change; existing tests are the oracle. Estimate:
   **1–2 days** including the test-suite reconciliation.

2. **Add a layering drift-test (zero new deps).** Matches the project's existing drift-test idiom
   (`test_api_surface_drift.py`, `test_vendor_hash_drift.py`, `test_docs_drift.py`). A `pytest` that
   walks the AST of `src/dazzle/render/**` and `src/dazzle/page/**` and **fails on any import** of a
   higher layer:
   - `render/` may import: `render`, `core`, stdlib/3p. **Not** `ui`, **not** `back`.
   - `ui/` may import: `ui`, `render`, `core`, stdlib/3p. **Not** `back`.
   - lazy in-function imports count (walk all `ast.Import`/`ast.ImportFrom`, not just module-top).

   This makes the rule *live* (per the Model-Driven Failure-Modes review rule: a detector that runs in
   the normal workflow, not merely documented). `import-linter` would also work declaratively, but a
   custom test avoids a new pinned dependency and fits the established pattern. Estimate: **0.5 day**.

Sequencing vs htmx 4: **do this first.** After it, htmx 4 touches one rendering path with one home for
the htmx contract, shrinking the Tier-1 surface in `htmx4-evaluation.md`.

## Is an ADR warranted?

**Yes — a short one.** The layer rule currently lives only as a docstring sentence in one `__init__.py`.
It is a real architectural invariant (`back → ui → render → core`, acyclic) that already has a written
rationale and is about to gain an enforcement gate. That is precisely what an ADR is for. Proposed:
**ADR-0038 "Rendering layer boundary: render/ is pure and acyclic"** — states the four-layer direction,
the "render/ is the only HTML producer" rule, the enforcement test, and records the region_adapter
relocation as the change that made it true. It should cross-reference ADR-0011 (SSR+htmx) and ADR-0023
(typed Fragments), which this completes rather than supersedes.

## Open questions

- Target location for the relocated code: `render/fragment/region/` vs a new `render/region/`?
- `import-linter` (declarative, +1 dep) vs custom AST drift-test (zero dep, matches idiom)? (Recommend
  custom.)
- Should the relocation be one commit (clean-break per ADR-0003) or staged module-by-module behind the
  new test? (Clean-break is more in keeping with house style, given tests are the oracle.)
- Do the `ui/runtime/*_renderer.py` page renderers eventually fold into `render/` too, or is
  "orchestration in ui, primitives in render" a deliberate and worth-keeping sub-seam? (Leaning:
  keep — they legitimately coordinate route/context concerns.)
