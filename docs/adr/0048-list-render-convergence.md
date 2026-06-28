# ADR-0048 — The `render/` substrate is the single source of list-row HTML; `http/` is transport-only

**Status:** Accepted (2026-06-28); **Phase 1+2 implemented** — the rich `dz-tr-row` data-table row now renders solely via `render/fragment/renderer/_data_row.py` (`render_data_row` / `render_data_table_rows`); the duplicate `http/runtime/htmx_render.py::_render_table_row` family is deleted. Phases 3 (fold `list-region`/`embedded` archetypes onto the shared core) and 4 (#1494 `peek:`/`when_empty:`) are planned follow-ons.
**Completes:** ADR-0038 (rendering-layer boundary — its htmx-4 evaluation found "~5,400 LOC of rendering in the HTTP package" and relocated `region_adapter`/`workspace_card_bodies` into `render/`, but never addressed the parallel `htmx_render.py` row renderer). Builds on ADR-0011 (SSR + htmx, no SPA), ADR-0023 (typed Fragment emission, no Jinja).
**Origin:** #1505 — surfaced while implementing #1494's `peek:` render, which would have had to add a chevron in two (then three) places.
**Design + plan:** `docs/superpowers/specs/2026-06-28-list-render-convergence-design.md`; `docs/superpowers/plans/2026-06-28-list-render-convergence-p1p2.md`.

## Context

List/table rows were rendered by **three independent emitters across two layers**:
`_render_table_row` (`http/`, `dz-tr-row`, rich CRUD data-table), `_emit_list_region`
(`render/`, `dz-list-row`, workspace list regions), `_emit_table` (`render/`,
`dz-table__row`, embedded tables). Git archaeology (May 2026) established this split as a
**Jinja-removal migration artifact**, not a principled layering decision: in the Jinja era
the full-page and HTMX-refresh paths *shared* one template family (`fragments/table_rows.html`);
when Jinja was removed (#1042), the two paths were de-Jinja'd **independently, in different
layers, the same week** (#1064 into `render/`, #1361 into `http/`) and never reconverged.
The "HTMX response shaping is a transport concern" rationale sometimes attached to
`htmx_render.py` is **post-hoc** — ADR-0038 never mentions the file, and the substrate was
htmx-aware from its first week (sortable `hx-get` headers, `InlineEdit`/`Toolbar` "with
htmx"), so transport was never a reason the substrate couldn't serve the refresh fragment.

The cost was a duplication tax (every per-row feature added in up to three places — #1494's
`peek:` hit this), divergence risk, and — decisively — **agent-cognition cost**: operating
the tools, an agent must first discover *which* renderer applies before it can reason about
or change list UX.

## Decision

`render/` (the pure typed-Fragment substrate) is the **single source of truth for list-row
HTML**. The rich data-table row is a substrate row-core (`render_data_row`) driven by a
typed, **orthogonal** capability vector (`RowCapabilities`: `bulk_select` / `inline_editable`
/ `drill` / `peek`, growing per archetype). `http/` shrinks to **transport-only**: on an
HTMX list refresh it builds the typed `DataTable` from queried items + column config
(`build_data_table`) and renders it via the substrate (`render_data_table_rows`), returning
the `<tbody>` slice — it no longer emits row HTML.

**Row model: unified structure + named archetypes.** One compositional row-core (base row +
orthogonal capability add-ons), with surface differences expressed as *named archetypes*
(`data-table` / `list-region` / `embedded`) — capability presets, not separate
implementations. This is more legible to an agent than three emitters (one
`f(columns, item, capabilities)` to reason about) **without** flattening the semantic
categories.

**The orthogonality invariant (standing rule).** Capabilities compose because of one
protocol: *the row owns the bare click (`drill`); every interactive sub-element — checkbox,
edit cell, action button, peek chevron — calls `event.stopPropagation()`.* A capability that
cannot satisfy this protocol is the signal it belongs to a **new archetype, not a new
conditional branch in the core.** If this invariant erodes, the legibility gain is lost — so
it is enforced at review, not assumed.

**Byte-stability per phase.** Each migration phase changes *zero* rendered bytes on the
fleet, guarded by characterization fixtures captured from the pre-migration output
(`tests/unit/__snapshots__/data_row_char_1505/`). Visual changes (peek/when_empty) are a
separate, later, deliberately-churning step (#1494, Phase 4).

## Consequences

- One renderer for the rich data-table; `peek:`/`when_empty:` (#1494) land once, in the
  substrate, downstream (Phase 4).
- `render is pure` (ADR-0038) stays a live import-linter contract — the row HTML now
  *originates* in `render/`; `http/` calls *down* for transport only.
- A column-less data-table renders an actions-only row (the `DataTable` empty-columns guard
  was dropped) so the P2 switch is strictly byte-identical even for a misconfigured refresh —
  fail-loud-on-misconfiguration would be a separate, deliberate change, not smuggled into a
  byte-stable phase.
- **Rejected:** *collapse to one identical DOM/CSS across all three surfaces* (maximal
  golden/card-safety churn; erases the semantic archetype signal an agent uses). *A shared
  leaf `render_one_row()` that `http/` and `render/` both call while context-assembly stays
  divergent above it* (papers the seam — unifies the leaf, not the duplicated data-flow).
  *Keep the split as ADR-0038-sanctioned* (the archaeology shows it was never sanctioned).

## Follow-ons

- **Phase 3** — fold `_emit_list_region` + `_emit_table` onto the shared row-core as
  archetype presets (may re-baseline workspace-region goldens; re-run card-safety).
- **Phase 4** — add the `peek` capability + `when_empty` to the shared core (#1494).
