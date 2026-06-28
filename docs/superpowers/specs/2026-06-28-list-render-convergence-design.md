# Design: List-render convergence — one substrate row-core, capability-composed, archetype-named

**Issue:** (to file) · **Relates:** #1494 (`peek:`/`when_empty:` — downstream consumer), ADR-0038 (completes), ADR-0011 (SSR+htmx), ADR-0023 (typed Fragment emission)
**ADR:** ADR-0048 (new — amends/completes ADR-0038)
**Status:** approved design (architecture + row model approved in brainstorming 2026-06-28), not yet implemented

---

## 1. Problem

Dazzle renders list/table rows through **three independent emitters** in **two layers**:

| Emitter | Layer | Surface (archetype) | Row class | Capabilities |
|---|---|---|---|---|
| `_render_table_row` (`http/runtime/htmx_render.py`) | `http/` | Rich CRUD data-table (`mode: list`, `/app/<entity>`) | `dz-tr-row` | bulk-select, inline-edit, row-state, hover actions, drill, column-visibility |
| `_emit_list_region` (`render/fragment/renderer/_render_tables.py`) | `render/` | Workspace list region (`region kind: list`) | `dz-list-row` | drill, pre-rendered row-actions, CSV, overflow |
| `_emit_table` (`render/fragment/renderer/_render_tables.py`) | `render/` | Embedded Fragment `Table` primitive | `dz-table__row` | drill, optional bulk-select |

These are **not** principled tiers. Git archaeology (May 2026) shows the split is a **migration artifact**: in the Jinja era the full-page path and the HTMX-refresh path shared one template family (`fragments/table_rows.html` via `{% include %}`). When Jinja was removed (#1042, `323bce34e`), the two paths were de-Jinja'd **independently, in different layers, the same week** — the full-page/region path into the `render/` substrate (#1064), the HTMX-partial path into `_render_table_row` in `http/` (#1361, `c0f453962` — "port of fragments/table_rows.html row branch"). They never reconverged.

The "transport concern" justification sometimes attached to `htmx_render.py` is **post-hoc**: ADR-0038 never mentions the file, and the substrate was **htmx-aware from its first week** (`207672ef4` "InlineEdit, Toolbar (with htmx)"; `1ab3568e2` sortable `<th>` "hx-get direction-flip"). HTMX transport was never a reason the substrate *couldn't* serve the refresh fragment.

### Consequences (why fix it now)

- **Duplication tax:** any per-row feature must be added in up to three places. #1494's `peek:` hit this immediately — a chevron built in `_render_table_row` does nothing for surfaces rendered by the substrate.
- **Divergence risk:** the same logical "list row" has three DOM/CSS contracts that can drift independently.
- **Agent-cognition cost (the decisive driver):** operating these tools, an agent must first discover *which* of three renderers applies before it can reason about or change list UX. In the #1494 session this cost multiple investigation passes and an initially-misplaced implementation. A single, compositional model collapses that to "add a capability → one place."

## 2. Goals / Non-goals

**Goals**
- `render/` (the pure typed-Fragment substrate) becomes the **single source of list-row truth** for all three archetypes — both context-assembly and HTML emission.
- `http/` shrinks to **transport only**: on an HTMX list refresh it builds the typed table Fragment from queried items + column config, renders it via the substrate, and returns the `<tbody>` slice + HX-\* headers. `_render_table_row` and its row-family siblings in `htmx_render.py` are **deleted**.
- A **unified compositional row-core**: one base row + **orthogonal** capability add-ons. Surface differences are expressed as **named archetypes** (capability presets), not separate implementations.
- `peek:`/`when_empty:` (#1494) then land **once**, downstream of the convergence.

**Non-goals**
- Not flattening the three archetypes into one identical DOM. Archetypes stay semantically distinct (see §3) — the *implementation* converges, the *visual/interaction category* is preserved.
- Not changing *what* HTML is produced for existing surfaces in the convergence phases — each phase is **byte-stable** (ADR-0038 style). Visual changes (peek wiring) are a separate, later, deliberately-churning step (#1494 slice 4).
- Not touching sort/pagination/search semantics, RBAC/scope, or the skeleton-hydrate first-paint model of the rich table.

## 3. The row model — unified structure + named archetypes

### 3.1 Capability vector (orthogonal)

A list row is `render_row(columns, item, capabilities)` where `capabilities` is an explicit, enumerable set:

- `bulk_select` → leading checkbox cell (+ select-all in header)
- `inline_edit` (per-column) → dual `<template x-if>` display/edit cell
- `row_state` → Alpine `:class` binds (`is-selected`/`is-saving`/`is-error`)
- `row_actions` → trailing actions cell (see flavor note in §3.3)
- `drill` → the row owns a bare-click `hx-get` to the detail surface
- `peek` → chevron control + hidden sibling panel row (#1494)
- `column_visibility` → `x-show="isColumnVisible(...)"` per cell

Region-level capabilities (`sort` headers, `pagination`/infinite-scroll, `CSV` export, `overflow`) sit on the table/region primitive, not the row, and are independently orthogonal.

### 3.2 The orthogonality protocol (the load-bearing invariant)

Capabilities compose because of **one rule**:

> **The row owns the bare click (`drill`). Every interactive sub-element — checkbox, edit cell, action button, peek chevron — calls `event.stopPropagation()`.**

This is what lets `bulk_select`, `inline_edit`, `row_actions`, `peek`, and `drill` coexist on one row without entanglement: each add-on contributes a bounded, independent piece of DOM and opts out of the row-level click. It is a single learnable rule — exactly the property that makes the unified core legible to an agent.

**Design test:** if a proposed capability cannot satisfy this protocol (it must interact with another capability's behaviour), that is the signal it belongs to a **different archetype**, not the shared core. Orthogonality is enforced, not assumed.

### 3.3 Archetypes (capability presets + marker)

Three named archetypes map to presets and carry a semantic marker (`data-dz-list-kind`) so both CSS and an inspecting agent retain the category:

| Archetype | Preset capabilities | dzTable Alpine controller | Marker |
|---|---|---|---|
| `data-table` | bulk_select, inline_edit, row_state, row_actions(hover), drill, column_visibility, peek? | mounted | `data-dz-list-kind="data-table"` |
| `list-region` | drill, row_actions(pre-rendered), peek? | not mounted | `data-dz-list-kind="region"` |
| `embedded-table` | drill, optional bulk_select | not mounted | `data-dz-list-kind="embedded"` |

Genuine divergences resolved by archetype, not by branching the core:
- **`row_actions` flavor** — `data-table` uses hover icon-buttons (view/edit/delete); `list-region` uses pre-rendered buttons (#1148). Unify the *input* (a list of action specs) and let the archetype choose the *presentation*; the action-spec list is the shared contract.
- **dzTable controller dependence** — `inline_edit`/`row_state` require the `dzTable` Alpine controller, which only `data-table` mounts. Encoded as an archetype property, so the core never emits edit/state DOM for archetypes that can't drive it.

### 3.4 DOM/CSS convergence stance

Class names *may* converge where it reduces cognitive load (a shared base row class) but the archetype marker is retained, and per-archetype CSS hooks remain. Concretely: a shared base class (e.g. `dz-row`) carries common structure; the archetype marker + existing per-archetype classes carry the variant styling. The phasing (§5) makes any class change a deliberate, golden-reviewed step — never a silent side effect.

## 4. Architecture

### 4.1 Where the row-core lives

In `render/` (the pure substrate). The substrate gains a capability-bearing **`DataTable`** primitive for the rich archetype; `ListRegion` and `Table` remain for the other two. All three delegate per-row rendering to **one** shared row-core function in `render/fragment/renderer/` that takes `(columns, item, RowCapabilities)` and emits the `<tr>` (+ optional peek panel row). Cell display, ref/drill resolution, escaping, and the §3.2 protocol live there once.

### 4.2 The transport-only `http/` adapter

On an HTMX list refresh (`list_handlers.py`):
1. Query items + resolve columns (unchanged — RBAC/scope/sort/filter stay in `http/`).
2. **Build the typed `DataTable` Fragment** from items + columns + the surface's resolved capabilities (this is the context-assembly convergence — the `http/` path now produces the *same typed input* the first-paint path would).
3. Render it through the substrate; return the **`<tbody>` inner slice** (a substrate-provided "render rows of this table fragment" entry, so we don't string-slice fragile HTML).
4. Attach HX-\* headers. This is the only `http/` responsibility left.

`_render_table_row`, `_render_table_empty`, `_render_table_sentinel`, `_render_table_pagination`, `_render_inline_edit`, `_render_cell_display` in `htmx_render.py` are deleted once their callers route through the substrate; `test_typed_runtime_no_jinja.py`'s module list shrinks accordingly.

### 4.3 Substrate "render rows only" entry

The substrate exposes a function that renders just the rows (`<tbody>` children) of a `DataTable`/`ListRegion`/`Table` fragment, so both the full-region emitter and the `http/` transport adapter call the same code for the row set. This is the seam that guarantees first-paint and refresh can never diverge.

## 5. Phased migration (byte-stable per phase)

Each phase ships independently, full-suite-green, golden-verified.

- **Phase 1 — Build `DataTable` + row-core to byte-reproduce `dz-tr-row`.** Add the `DataTable` primitive + the shared row-core in `render/`, configured to emit **exactly** today's `_render_table_row` output for the `data-table` archetype. Characterization tests assert byte-equality against the current `_render_table_row` for a matrix of capability combinations. No caller switched yet → zero fleet churn.
- **Phase 2 — Switch the `http/` refresh path onto the substrate; delete `_render_table_row`.** `list_handlers.py` builds the `DataTable` fragment and renders the tbody slice. Golden/byte tests prove the HTMX response is identical. Delete the `htmx_render.py` row family. Net: the rich table now has **one** renderer.
- **Phase 3 — Fold `_emit_list_region` + `_emit_table` onto the shared row-core.** Re-express them as archetype presets over the core. This *may* churn workspace-region goldens (class/marker normalization) — each diff inspected and re-baselined deliberately. Card-safety composite (`test_htmx_workspace_composite.py`) re-run on the post-fold DOM.
- **Phase 4 — `peek:` + `when_empty:` once (downstream #1494).** Add the `peek` capability and `when_empty` to the shared core; they apply to every archetype that opts in, in one place. This is where the existing #1494 slice plan resumes — now trivial because there is a single seam. (The stashed WIP `stash@{0}` is superseded; re-derive peek on the converged core.)
- **ADR-0048** — written in Phase 1, documenting the convergence, completing ADR-0038's unfinished relocation, and recording the post-hoc nature of the prior "transport concern" framing.

## 6. Testing & blast radius

- **Characterization-first:** Phase 1/2 are guarded by byte-equality tests captured from the *current* output before any switch — the migration's safety net.
- **Affected goldens:** `test_route_generator_row_class_1327.py` (#1327 binding), `test_dispatch_ctx_list_*.py`, `test_list_index_emission.py`, the fleet list goldens, `test_htmx_workspace_composite.py` (card-safety), `test_typed_runtime_no_jinja.py` (module list shrinks). Phases 1–2 should leave all green unchanged; Phase 3 re-baselines region goldens deliberately.
- **Import contracts:** `render/ ↛ http/` stays green (the row-core is in `render/`, `http/` calls *down*). `test_import_contracts.py` / `test_import_boundaries.py` unaffected in direction.

## 7. Model-driven failure-mode check (per CLAUDE.md)

1. **Which failure mode does this risk?** *Over-abstraction / hidden semantics* (MDF) — a capability-parameterised god-primitive could obscure what a surface renders.
2. **Which detector catches it if we're wrong?** The orthogonality design-test (§3.2): non-composing capabilities must split into archetypes, keeping each path bounded; plus byte-golden tests that pin the DSL→DOM mapping.
3. **Is the detector live?** Yes — golden/byte tests run every commit; the orthogonality rule is a review gate encoded in this spec and the ADR.
4. **Can an engineer/agent trace runtime DOM back to DSL/AppSpec?** *Improved* — one `render_row(columns, item, capabilities)` function + named archetypes is a more traceable mapping than three independent emitters selected implicitly by request path.
5. **Does it preserve Postgres/auth/workflow/UI semantics?** Yes — RBAC/scope/sort stay in `http/`; only HTML production moves. Archetype markers preserve UI category.

**Residual risk note:** the win depends on capabilities staying orthogonal. If a future capability forces interaction, the correct response is a new archetype, not a conditional branch in the core — otherwise the legibility gain erodes. This is documented as the standing invariant in ADR-0048.

## 8. Open questions for the plan phase

- Exact shape of `RowCapabilities` (frozen dataclass vs flags on the primitive) — resolve in writing-plans.
- Whether `DataTable` and `Table` ultimately merge (Phase 3+) or stay sibling primitives — decide after Phase 2 proves the core.
- The substrate "render rows only" entry signature (takes a built fragment vs `(columns, items, caps)`) — pin in Phase 1.
