# ADR-0049 — The typed Fragment substrate is the universal render path; the legacy direct-template layer is retired mode-by-mode

**Status:** Accepted (2026-06-29) — **direction committed, phased implementation pending.** Phase 1 (list) first; view, create/edit follow.
**Builds on:** ADR-0023 (typed Fragment emission — created the substrate), ADR-0038 (render/ is pure — relocated rendering into the substrate layer), ADR-0048 (#1505 — converged the list *row* engine onto `render_data_row`). Completes the de-Jinja migration (#1042) at the level of *render-path shape*, not just template syntax.
**Origin:** the #1494/#1505 work surfaced that production runs 100% on a legacy render path while the typed substrate sits unadopted.

## Context

Dazzle has **two parallel server-side render paths for every surface mode** (list, view, create, edit), forked in `page_routes.py::_maybe_dispatch_inner_html` on `surface.render is None`:

- **Legacy "direct-template" path** — `page/runtime/{table_renderer,detail_renderer,form_renderer}.py` (~2,322 LOC). f-strings since #1042, but its *shape* — a separate per-mode renderer, the skeleton+hydrate table, the hand-built `<dt>/<dd>` detail, the wrapper-less form — is a fossil of the Jinja era.
- **Typed Fragment substrate** — `FragmentSurfaceAdapter` + the `render/` primitive renderers. Pure, composable, serverless-testable; the intended future per ADR-0023.

**The inversion:** across all example apps, **zero** surfaces set `render:`, so production runs **100% on the legacy path**, and the substrate is **built but unadopted** (only test fixtures exercise it). The deprecated-shaped path is everything; the modern path is dead code in practice. Every agent operating the codebase must hold *both* models, and new behaviour keeps accreting on the fossil — the classic early-choice ossification (cf. the SQLite-before-ADR-0008 difficulty). For all four modes the two paths emit *different* DOM/CSS, and the legacy form path is actively decaying (it lacks a submit button, #1291, which the substrate fixes).

ADR-0048 already converged the list **row** engine: the legacy list path's rows hydrate via `/api` → `render_data_row` (`dz-tr-row`), the same core the substrate uses. So the remaining fossil is the **chrome** (table/detail/form wrappers + the `dzTable` mount + the skeleton), not the rows.

## Decision

**The typed Fragment substrate is the single, universal server-side render path.** The legacy direct-template renderers are deprecated and **deleted mode-by-mode** as each mode reaches parity. After migration there is one render model: AppSpec → Fragment primitives → HTML.

Load-bearing decisions (rationale in the design spec `docs/superpowers/specs/2026-06-29-substrate-universal-render-path-design.md`):

1. **Visual parity, not byte parity.** The substrate's DOM/CSS becomes canonical; we do **not** contort it to byte-match the legacy output. Each mode's goldens are re-baselined deliberately and verified for **visual + a11y + card-safety** parity. (Byte-matching a fossil would import its shape — the opposite of the goal.)
2. **List keeps skeleton+hydrate; `render_data_row` stays the sole row source.** The substrate list path emits chrome + an empty `<tbody hx-trigger="load">` pointing at `/api` — so rows always come from `render_data_row` (ADR-0048), the substrate only needs **chrome** parity, and fast time-to-first-paint is preserved. Inline-rows remains a future per-surface option, not the default.
3. **The `dzTable` controller mounts on the list Region** (the container that knows it's a stateful list), with the config (sort/bulk/inline/columns) threaded by the substrate builder. Refresh rows continue to assume the mounted controller.
4. **No silent legacy fallback after retirement.** The current default-deny fallback (substrate error → legacy) is a *migration-only* crutch; once a mode's legacy renderer is deleted, substrate errors surface as an error response. The substrate must be robust before each delete.
5. **Default flips per mode.** Migration order: **list → view → create/edit** (list is closest — rows already converged). Per mode: close the substrate chrome gaps → flip the default (treat unset `render` as substrate for that mode) → re-baseline + verify → delete the legacy renderer. CUSTOM is already substrate-only.

## Consequences

- One render model — a single mental map for agents; the fossil and its dual-path fork are gone; new behaviour has one home.
- Fleet-wide, deliberate golden churn (per mode, gated on visual/a11y/card-safety parity).
- ~2,322 LOC of legacy renderers deleted across the phases; `page/runtime/{table,detail,form}_renderer.py` retired.
- The legacy form submit-button bug (#1291) is resolved by adoption.
- **Rejected:** *keep both paths* (the status quo — the fossil ossifies, agents pay the dual-model tax forever). *Byte-match the substrate to legacy* (imports the fossil's shape; defeats the purpose). *Big-bang flip all modes at once* (un-reviewable churn + no fallback during the riskiest moment) — phased, mode-by-mode, each independently shippable and verifiable.

## Follow-ons

Phased design + per-mode parity gap-lists: `docs/superpowers/specs/2026-06-29-substrate-universal-render-path-design.md`. Phase 1 (list) gets the first implementation plan.
