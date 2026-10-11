# Design: make the typed Fragment substrate the universal render path; retire the legacy direct-template layer

**ADR:** ADR-0049 · **Builds on:** ADR-0023, ADR-0038, ADR-0048 (#1505) · **Status:** approved direction, phased implementation pending

## 1. Problem (recap)

Two parallel render paths per surface mode, forked at `page_routes.py::_maybe_dispatch_inner_html` on `surface.render is None`. The **legacy** path (`page/runtime/{table,detail,form}_renderer.py`, ~2,322 LOC) is 100% of production; the **typed substrate** (`FragmentSurfaceAdapter` + `render/` renderers) is built but unadopted. The legacy path's *shape* is a Jinja-era fossil; holding both models is a standing agent-cognition tax that grows as behaviour accretes on the fossil. ADR-0048 already converged the list **rows** (`render_data_row`); the remaining fossil is the **chrome**.

## 2. Goals / non-goals

**Goals**
- One server-side render model: AppSpec → Fragment primitives → HTML.
- Delete the legacy direct-template renderers, mode-by-mode.
- Preserve fast time-to-first-paint (list keeps skeleton+hydrate) and the converged row engine (`render_data_row` stays the sole list-row source).

**Non-goals**
- Not byte-matching the substrate to the legacy DOM (visual/a11y/card-safety parity is the bar; see §4.1).
- Not changing the `/api/<entity>` refresh endpoint or `render_data_row` (already canonical).
- Not touching workspace/dashboard/experience routes (separate from surface-mode dispatch — out of scope).
- Not wiring inline-edit/bulk-select into delivery (a *separate* latent gap — see §6; tracked, not part of this initiative).

## 3. Resolved design decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Visual parity, not byte parity.** Substrate DOM/CSS is canonical; goldens re-baselined per mode; parity verified via golden diff inspection + `dazzle ux verify` + card-safety composite + a11y checks. | Byte-matching a fossil imports its shape — defeats the goal. |
| D2 | **List = chrome + skeleton+hydrate.** Substrate list emits chrome + empty `<tbody hx-trigger="load">` → `/api` → `render_data_row`. | Keeps `render_data_row` the sole row source (ADR-0048); only chrome needs parity; fast TTFP preserved. |
| D3 | **`dzTable` controller mounts on the list Region.** Builder threads sort/bulk/inline/columns config. | The Region knows it's a stateful list; refresh rows already assume the mounted controller. |
| D4 | **No silent legacy fallback after a mode's delete.** The default-deny fallback is migration-only. | A deleted renderer can't be a fallback; substrate must be robust first. |
| D5 | **Default flips per mode** by treating unset `render` as substrate for that mode (and deleting the legacy branch). Order: list → view → create/edit. | Smallest reviewable increments; list is closest (rows converged). |

**Flagged for review (genuinely contentious):** D1 (accepting fleet-wide visual re-baseline) and D2 (skeleton+hydrate vs inline — the TTFP/TTI trade you raised). If you'd prefer inline rows for the universal list path, that changes D2 and the row-source story.

## 4. Per-mode phases

Each phase is independently shippable and gated. Pattern per mode: **(a) close substrate chrome gaps → (b) flip default → (c) re-baseline + verify parity → (d) delete legacy renderer.**

### Phase 1 — LIST (closest; rows already converged)

Substrate chrome gaps to close before the flip (from the depth investigation; `_emit_table`/`_build_list` vs `render_filterable_table`):
- **Skeleton tbody + `hx-trigger="load"`** (D2) — add a `skeleton`/endpoint mode to the `Table` primitive + `_emit_table` so first paint emits the empty hydrating tbody instead of inline rows.
- **`dzTable` mount** (D3) — Region (kind=list) emits `x-data="dzTable(id, endpoint, config)"`; config (sortField/sortDir/bulkActions/inlineEditable/entityName) threaded by `_build_list`.
- **Column-visibility menu** (header checkbox grid + toggle) — currently legacy-only.
- **Colgroup / column widths**, **loading spinner overlay**, **screen-reader loading + a11y live region** — currently legacy-only.
- Already at parity: SearchBox, FilterBar, SortHeader, BulkActionToolbar, CreateButton, Pagination, EmptyState (substrate primitives exist).

Flip: `_maybe_dispatch_inner_html` dispatches list surfaces even when `render is None`. Re-baseline list goldens; run `dazzle ux verify` + `test_htmx_workspace_composite` (card-safety) + a11y. Delete `render_filterable_table` + its helpers (~516 LOC) and repoint its two non-test callers (`experience_renderer.py`, `template_renderer.py`).

### Phase 2 — VIEW (detail)

Parity gaps: legacy `render_detail_view` (`dz-detail`, hand-built `<dt>/<dd>`, action/transition/external-link blocks) vs substrate `_build_view` (`Region(kind=detail)` + `Stack`/`Row`). Close the action-toolbar / transition / external-link / related-group gaps in the substrate; **the detail-body partial used by `peek` (`?peek=1`) rides on this** — converging detail rendering makes peek's panel content consistent too. Flip → re-baseline → delete `render_detail_view` (~635 LOC).

### Phase 3 — CREATE / EDIT (forms)

Substrate `_build_form` (`FormStack` + auto `Submit`) already *fixes* the legacy submit-button bug (#1291). Close widget-parity gaps (the ~15 legacy field widgets vs substrate form primitives). Flip → re-baseline → delete `render_form_field` + widgets (~806 LOC). **Breaking-change note:** forms gain the proper `<form>` wrapper + submit button (a fix, but visible) — call out in CHANGELOG.

CUSTOM mode is already substrate-only (no work).

## 5. Testing & parity strategy

- **Characterization first** per mode: capture current legacy output for a representative matrix, then build substrate parity against a *visual* bar (not byte) — inspect every golden diff before re-baselining.
- **Oracles:** `dazzle ux verify` (live render oracle), `test_htmx_workspace_composite` (card-safety on post-swap DOM), a11y checks, the existing per-mode emission tests (re-baselined).
- **Import-linter** `render is pure` stays green (the substrate is in `render/`; chrome moves there too).
- Each phase: full unit suite + the mode's e2e/visual oracle green before the legacy delete.

## 6. Model-driven failure-mode check (per CLAUDE.md)

1. **Failure mode risked:** *visual/behavioural regression* during the flip (the substrate DOM differs from legacy).
2. **Detector:** golden re-baseline diff inspection + `ux verify` live oracle + card-safety composite + a11y — per mode, before delete.
3. **Live?** Yes — all run in CI/the normal workflow.
4. **Traceable?** *Improves* — one render model (AppSpec → Fragment → HTML) is far more traceable than a `render is None` fork into two divergent renderers.
5. **Preserves semantics?** Yes — RBAC/scope/sort/`/api` unchanged; only HTML production unifies.

**Residual risk:** removing the legacy fallback (D4) means a substrate bug becomes a user-visible error rather than a silent downgrade. Mitigation: robustness + the oracles above must pass before each mode's delete; the phased order means only one mode is exposed at a time.

## 7. Separate tracked gap (not this initiative)

Inline-edit and bulk-select are compile-time ceremony that reach **neither** renderer today (the htmx `table_dict` and the Fragment adapter both omit them). Whether to wire them through is a separate product decision — file as its own issue; this initiative neither fixes nor worsens it.

## 8. Open questions for the plan phase

- The `Table` primitive's skeleton-mode field shape (D2) and where `_build_list` decides skeleton vs inline.
- Exact `dzTable` config threading through Region (D3).
- Whether the default-flip is per-mode in `_maybe_dispatch_inner_html` or an IR-level `render` default — pin in Phase 1's plan.
