# `peek:` (2c) + `when_empty:` (3d) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship the first two declarative-over-htmx-4 UX-maturity primitives — `peek:` (action-proximate inline detail/edit, 2c) and `when_empty:` (self-suppressing empty region, 3d) — taking criteria 2c and 3d from level 2 to level 4.

**Architecture:** Thin DSL keywords (`peek:` on a list surface, `when_empty:` on a region) compile to IR fields with a true-unset discriminator (mirroring #1492's `display_unset`); right-by-default resolvers pick the behaviour when unset; render emits native htmx-4 wiring (chevron + `hx-get` of the existing detail partial; lazy `intersect` fetch that self-removes when empty), plus two vendored beta extensions (`hx-optimistic`, `hx-upsert`) for optimistic click-to-edit and in-place row upsert. The default-flip + probe re-score is isolated to the final slice so the primitive slices stay byte-stable.

**Tech Stack:** Python 3.12, Pydantic IR, the Dazzle DSL parser mixins, the typed Fragment render substrate + `htmx_render` tbody path, htmx 4.0.0-beta4 (already vendored) + `hx-optimistic`/`hx-upsert` beta extensions.

**Spec:** `docs/architecture/1494-peek-when-empty-design.md` (§1–§8). Read it before starting.

## Global Constraints

- **No `from __future__ import annotations` in FastAPI route files** (ADR-0014).
- **No backward-compat shims** — `slide_over: true` becomes a parse-time alias for `peek: slide_over` with a deprecation diagnostic; update all example DSL in the same commit (ADR-0003).
- **All probe/resolver imports module-top** — never function-body (the #1438 deferred-import ratchet; bit the #1492/#1493 probes twice).
- **No bare `except Exception: return …`** — use a `hasattr`/specific-exception guard (`test_no_bare_except_pass`).
- **Regenerate the UX catalogue** (`python scripts/gen_ux_catalogue.py`) whenever badge/region rendered output changes; it's the one committed rendered artifact.
- **Run the FULL unit suite before each ship** — golden-master + example snapshots drift differently than `-k`-filtered runs (`[[feedback-ir-field-additions-full-suite]]`).
- **Ship discipline:** `/bump patch`, clean worktree, CHANGELOG entry (+ `### Agent Guidance` when a new pattern lands), full suite green, monitor CI.
- **Card-safety invariants** (`docs/reference/card-safety-invariants.md`) apply to the expand panel (new region-ish DOM): run `tests/unit/test_htmx_workspace_composite.py`.

---

## Slice 1 — `peek:` IR + parser + `expand` render (native, byte-stable)

Resolver present but **default off** (opt-in) this slice → byte-stable on the fleet. Closes nothing yet; sets up the mechanism.

### Task 1.1: `peek` IR field + true-unset discriminator

**Files:**
- Modify: `src/dazzle/core/ir/surfaces.py` (SurfaceSpec, ~line 327)
- Test: `tests/unit/test_peek_when_empty_1494.py` (create)

**Interfaces:**
- Produces: `SurfaceSpec.peek: PeekMode` (enum `expand|slide_over|off`) defaulting to a sentinel; `SurfaceSpec.peek_unset: bool = Field(default=True, exclude=True)` (True = author wrote nothing; `exclude=True` keeps it out of corpus snapshots, like `display_unset`).

- [ ] **Step 1: Write the failing test** — assert `SurfaceSpec()` has `peek_unset is True` and a default `peek`; assert setting `peek` is round-trippable.
- [ ] **Step 2: Run, verify fail** (`AttributeError: peek`).
- [ ] **Step 3: Add `PeekMode` enum (`expand`/`slide_over`/`off`) + the two fields** to SurfaceSpec, mirroring `WorkspaceRegion.display`/`display_unset` exactly (read `workspaces.py:991-996` first).
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Regenerate the ir-types api-surface baseline** (`dazzle inspect api ir-types --write`) — adding an IR field always drifts it (`[[feedback-ir-field-additions-full-suite]]`). Add the CHANGELOG note later.
- [ ] **Step 6: Commit** (`feat(ir): SurfaceSpec.peek + peek_unset discriminator (#1494 slice 1)`).

### Task 1.2: `peek:` parser keyword + `slide_over:` alias

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/surface.py` (add `_kw_peek`, register in the keyword map; locate the existing `slide_over` handling first — Step 0 — and repoint it to set `peek=slide_over` + emit a deprecation diagnostic)
- Modify: `docs/reference/grammar.md` (document `peek:` + the alias)
- Test: `tests/unit/test_peek_when_empty_1494.py`

**Interfaces:**
- Consumes: `SurfaceSpec.peek`/`peek_unset` (Task 1.1).
- Produces: a `peek: expand|slide_over|off` surface clause that sets `peek` + `peek_unset=False`; `slide_over: true` → `peek=slide_over`, `peek_unset=False`, + a deprecation warning.

- [ ] **Step 0: Locate the current `slide_over` origin** — `grep -rn slide_over src/dazzle/core src/dazzle/page/converters`. Confirm where `TableContext.slide_over` is set (it was not found on SurfaceSpec/converters in scouting — establish the real path before repointing).
- [ ] **Step 1: Write failing tests** — parse `peek: expand` → `surface.peek == PeekMode.EXPAND`, `peek_unset is False`; parse no clause → `peek_unset is True`; parse `slide_over: true` → `peek == PeekMode.SLIDE_OVER` + a deprecation diagnostic present; an unknown value → parse error.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Add `_kw_peek`** (module-level `_kw_*` per the #1097 pattern at `surface.py:693+`); validate the value against `PeekMode`; register in the keyword dispatch map. Repoint `slide_over`.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Update `docs/reference/grammar.md`; run `test_docs_drift.py`.**
- [ ] **Step 6: Commit.**

### Task 1.3: `resolve_peek_mode` resolver (default OFF this slice)

**Files:**
- Create: `src/dazzle/page/runtime/peek_resolver.py` (or extend `auto_display.py` — match where `resolve_region_display_mode` lives)
- Test: `tests/unit/test_peek_when_empty_1494.py`

**Interfaces:**
- Produces: `resolve_peek_mode(surface, entity) -> PeekMode`. **This slice:** explicit value wins; unset → `PeekMode.OFF` (so the fleet is byte-stable). The default-flip to `expand` happens in Slice 4.

- [ ] **Step 1: Write failing tests** — explicit `peek=expand` → `EXPAND`; unset → `OFF` (this slice); unset with no detail surface → `OFF`.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** the resolver (module-top imports only).
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit.**

### Task 1.4: `expand` render — chevron + detail-partial insert

**Files:**
- Modify: `src/dazzle/http/runtime/htmx_render.py` (`_render_table_row`, ~line 274; the drill block at 333-336)
- Modify: the list/table context builder to carry `peek_mode` + a detail-partial URL template
- Modify: the route layer to serve a **detail body partial** (`hx-get` target) if one doesn't already exist (Step 0 confirms)
- Test: `tests/unit/test_peek_when_empty_1494.py`

**Interfaces:**
- Consumes: `resolve_peek_mode` (1.3); the existing `render_detail_view`/detail body renderer (one detail renderer, not two).
- Produces: when `peek_mode == expand`, each row carries a chevron control (`aria-expanded`, `hx-get` the detail partial into an inserted sibling row, `hx-target` the new row, toggle to remove on collapse). `off` → today's drill markup unchanged.

- [ ] **Step 0: Confirm the detail-partial route** — find or add an endpoint returning just the detail body fragment (reuse `render_detail_view`). Record its URL template.
- [ ] **Step 1: Write failing tests** — a table with `peek_mode=expand` renders a chevron + `hx-get="<detail-partial>"` + `aria-expanded="false"`; `peek_mode=off` renders the unchanged drill `<a>`; byte-identical to pre-#1494 when `off`.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** the chevron/expand branch in `_render_table_row`; thread `peek_mode` through the table context.
- [ ] **Step 4: Run, verify pass; run `test_htmx_workspace_composite.py`** (card-safety on the expanded DOM).
- [ ] **Step 5: Commit.**

### Slice 1 gate
- [ ] `pytest tests/ -m "not e2e"` fully green; `ruff check`/`ruff format`/`mypy src/dazzle` clean; import-linter `lint-imports` KEPT.
- [ ] Byte-stable on the fleet (no example sets `peek:`; default resolves `off`). `/bump patch`, CHANGELOG, ship, monitor CI.

---

## Slice 2 — click-to-edit + optimistic + upsert (beta extensions)

### Task 2.1: Vendor `hx-optimistic` + `hx-upsert`
**Files:** `scripts/update_vendors.py` (pinned version + provenance check + `sourceMappingURL` strip, per #1467/#860), `src/dazzle/page/runtime/static/vendor/`, the dist bundle list (`scripts/build_dist.py` + JS bundle), `app_chrome.py` script tags.
- [ ] Fetch the pinned beta extension files (jsDelivr/unpkg, byte-verify); wire into `update_vendors.py`; add to dist + chrome; rebuild dist; bump fingerprint (#1468). Test: a vendor-presence test asserts the files exist + are referenced. Commit.

### Task 2.2: Click-to-edit view⇄edit partial swap
**Files:** the detail-partial route (add an edit-partial variant), `detail_renderer`/the partial renderer (Edit toggle `hx-get`s the edit partial; Save `hx-put`s and swaps back).
- [ ] TDD: the detail partial renders an `Edit` control that `hx-get`s the edit partial; the edit partial renders inputs + a Save that `hx-put`s the entity and `hx-target`s the row/panel back to the view partial. Reuses the existing form-field renderer. Commit.

### Task 2.3: Optimistic save + upsert-by-id
**Files:** the edit-partial Save control (add `hx-optimistic` + `hx-upsert` attrs keyed by row id).
- [ ] TDD: Save markup carries `hx-optimistic` (optimistic value, rollback on non-2xx) + `hx-upsert` targeting the row by id. Scope: local edit→row-refresh only (no multi-user live-insert). Commit.

### Slice 2 gate
- [ ] Full suite green; lint/mypy/import-linter clean; dist rebuilt + committed; `/bump`, CHANGELOG, ship, CI.

---

## Slice 3 — `when_empty:` IR + parser + suppress/collapse render (native, byte-stable)

### Task 3.1: `when_empty` IR field + unset discriminator
**Files:** `src/dazzle/core/ir/workspaces.py` (WorkspaceRegion, ~line 960). Mirror `display`/`display_unset`: `when_empty: WhenEmpty` (`message|suppress|collapse`) + `when_empty_unset: bool = Field(default=True, exclude=True)`.
- [ ] TDD + regenerate ir-types baseline. Commit.

### Task 3.2: `when_empty:` parser keyword
**Files:** the region/workspace parser dispatcher (`dsl_parser_impl/workspace.py`); `grammar.md`.
- [ ] TDD: `when_empty: suppress|collapse|message` sets the field + `_unset=False`; unknown → parse error; drift gate. Commit.

### Task 3.3: `resolve_when_empty` + suppress/collapse render
**Files:** a resolver (default `message` this slice — byte-stable); the lazy-region fetch/render path (`workspace_region_*` / the region fetch handler) returns a self-removing partial when the region resolves empty + `suppress`, header-only when `collapse`.
- [ ] **Step 0:** find the lazy-region (`intersect`) fetch handler + where emptiness is known server-side. TDD: empty + `suppress` → self-removing partial (OOB/`hx-swap` delete of the region wrapper); empty + `collapse` → header-only; `message` → unchanged. Commit.

### Slice 3 gate
- [ ] Full suite green; lint/mypy/import-linter; byte-stable (default `message`). `/bump`, CHANGELOG, ship, CI.

---

## Slice 4 — default-flip + probes + baselines + catalogue (the churn)

### Task 4.1: Flip the defaults
**Files:** `resolve_peek_mode` (unset + entity-has-detail-surface → `expand`), `resolve_when_empty` (unset + region-is-lazy/secondary → `suppress`; primary → `message`). Add an `is_primary`/region-role signal to the resolver inputs.
- [ ] TDD the default matrix. Commit.

### Task 4.2: Probes + baselines 2 → 4
**Files:** `src/dazzle/qa/ux_maturity.py` (`_probe_2c`, `_probe_3d` — assert the resolvers + render wiring exist; bump the `2c`/`3d` `Criterion.declared` 2→4 + rationale), `tests/unit/test_ux_maturity_baseline.py` (update the backlog/level comments).
- [ ] TDD: `crit_2c.declared == 4`, `crit_3d.declared == 4`, both probes `.ok`; `drift_violations()` empty. Commit.

### Task 4.3: Regenerate fleet goldens + catalogue
**Files:** all churned example/golden snapshots; `docs/reference/ux-catalogue.md` + `docs/assets/dazzle-catalogue.css` (add a `peek`/`when_empty` catalogue mode + manifest marker).
- [ ] Run the full suite; for each churned golden, **inspect** the diff (peek wiring appears where the entity has a detail surface; empty lazy regions vanish) before regenerating. Regenerate catalogue. Commit.

### Slice 4 gate
- [ ] Full suite green; lint/mypy/import-linter; `dazzle ux maturity --drift` clean (2c/3d re-scored to 4). `/bump`, CHANGELOG (+ `### Agent Guidance` on the `peek:`/`when_empty:` default + resolver pattern), ship, CI. Close #1494.

---

## Self-Review

- **Spec coverage:** §1 DSL surface → Tasks 1.2/3.2; §2 IR+parser → 1.1/1.2/3.1/3.2; §3 native render → 1.4/3.3; §4 beta exts → 2.1/2.2/2.3; §5 resolvers+probes → 1.3/4.1/4.2; §6 churn → 4.3; §7 slices → the four slices; §8 MDF check → the unset discriminators (1.1/3.1) keep the resolved value inspectable. Covered.
- **Open investigations folded into Step 0s** (not placeholders): slide_over origin (1.2), detail-partial route (1.4), lazy-region empty seam (3.3) — each is the first step of its task because the scouting pass couldn't pin them from grep alone.
- **Type consistency:** `PeekMode {expand,slide_over,off}` and `WhenEmpty {message,suppress,collapse}` used consistently; `peek_unset`/`when_empty_unset` discriminators mirror `display_unset`; `resolve_peek_mode`/`resolve_when_empty` signatures stable across slices (Slice 1/3 default off/message; Slice 4 flips the unset branch only).
