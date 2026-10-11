# ADR-0049 Phase 3 — CREATE/EDIT (forms) render via the substrate

> **For agentic workers:** Hybrid mode — inline TDD per task + an independent adversarial review before the flip (3b Task 2) and the delete (3b Task 3). Same arc as Phase 1 (list) and Phase 2 (view), both shipped (v0.92.15–25). **Scope chosen by James 2026-06-29: Sequence 3a→3b (build widgets to proven parity, THEN flip + delete).**

## Why this phase is different (and bigger) than 1/2

Phases 1–2 were **chrome convergence** — the substrate already rendered the content; we closed cosmetic gaps and deleted. Phase 3 is **net-new widget porting**: the substrate form path (`fragment_adapter._build_form` → `forms.py` primitives → `_render_forms.py`) covers the simple field kinds (text/textarea/email/number/decimal/date/datetime/enum→Combobox/bool→checkbox/file→FileUpload/FK→RefPicker/sections→FormSection) but is **missing** the rich widgets the fleet actually uses. `form_renderer.py` (~806 LOC) is the **only** implementation of them.

**The reframe that makes it tractable:** the Alpine/TomSelect/Flatpickr controllers already exist client-side (`static/js/*`); the legacy renderer just emits the right **mount attributes** (`data-dz-widget`, `data-dz-options`, `x-data`, hidden-input splits). So porting a widget = a substrate primitive + renderer that emits the **same mount attributes** to **visual/attribute parity** (D1), register it in the `Fragment` union + `_emit` match + `_field_to_primitive` mapper, thread any new dispatch-ctx keys. Not new client behavior.

## Widget census (the exact port-list — examples + fixtures, 2026-06-29)

| Widget | Usage | Substrate today | Action |
|---|---|---|---|
| `source:` → **search_select** | **21 files**, fleet-wide, **fidelity-gated** (`fidelity_scorer`: `source=` ⇒ must render search_select) | ✗ MISSING | **PORT (first — hard blocker)** |
| `widget=rich_text` | 20 | ✗ MISSING (`rich_text_toolbar`/`rich_text_max_length` opts) | PORT |
| `widget=picker` (Flatpickr date/datetime/range mode) | 20 | ✗ (substrate uses HTML5 native) | PORT |
| `widget=combobox` (TomSelect static enum) | 12 | ◐ substrate `Combobox` is plain `<select>` — legacy wires `data-dz-widget=combobox data-dz-options` | PORT (parity on existing primitive) |
| `widget=slider` | 8 | ✗ MISSING (dzRangeTooltip) | PORT |
| `widget=color` | 8 | ✗ MISSING | PORT |
| `widget=tags` | 6 | ✗ MISSING (TomSelect create+remove) | PORT |
| `: money` (first-class lexer type) | 8 fields (`pra`) | ✗ maps to plain `number` (loses major/minor + currency + dzMoney) | PORT |
| `widget=multi_select` | **0** | ✗ | **DROP legacy at delete (dead)** |
| `widget=range`/date_range | **0** | ✗ | **DROP legacy at delete (dead)** |
| text/textarea/email/number/decimal/date/datetime/enum/bool/file/FK/sections | everywhere | ✓ MATCH | — |

`component_showcase` (the gallery fixture) exercises rich_text/picker/slider/color/tags — it is the **per-widget parity oracle**. `pra` exercises money. ~10 example apps exercise search_select.

## Locked decisions

- **D1 visual/attribute parity, not byte.** Substrate DOM is canonical; re-baseline goldens; gate on `dazzle ux verify` + fidelity (search_select) + card-safety + a11y. Per-widget characterization test pins the legacy mount-attribute contract the client JS depends on (`data-dz-widget`, `data-dz-options` JSON, hidden-input names).
- **D4 no silent legacy fallback after the 3b delete.** `template_renderer` form branch → loud `RuntimeError` (like list/view).
- **3a is independently shippable per widget; 3b flips + deletes only after every ported widget proves parity on `component_showcase` + the fleet + the fidelity gate is green.**
- **Drop dead widgets** (`multi_select`, `date_range`) at 3b rather than port — zero usage. Confirm census still zero at delete time.

## Phase 3a — build widget primitives (each shippable, TDD, ship per widget)

Per-widget recipe (the repeatable loop):
1. **Characterize:** capture legacy `render_form_field` output for the widget across its option matrix (component_showcase / a focused fixture) → snapshot the mount-attribute contract.
2. **Primitive:** add a frozen dataclass to `render/fragment/primitives/forms.py` (fields = the legacy attrs: name/label/required/initial_value + widget-specific opts).
3. **Renderer:** `render/fragment/renderer/_render_forms.py` `_emit_<widget>` emitting the same `data-dz-widget`/`data-dz-options`/`x-data`/hidden-split markup (parity).
4. **Register:** `Fragment` union (`primitives/_base.py`) + `_emit` match (`renderer/_emit.py`) + exhaustiveness/alias/html5 harnesses + `forms.py` `FormStack.fields` union + `FormSection.fields` union.
5. **Mapper:** `fragment_adapter._field_to_primitive` routes the widget/kind → the new primitive.
6. **Dispatch ctx:** thread any new keys (`widget`, `rich_text_toolbar`, `rich_text_max_length`, money `currency`, search `source`/endpoint/debounce) through `page_routes._build_dispatch_ctx` form branch. **Trap (Phases 1–2): the dispatch ctx silently lags the renderer — thread every key the renderer reads.**
7. **Parity test** (`tests/unit/test_form_widget_<widget>_phase3.py`) asserting attribute parity vs legacy. Ship (ruff, full suite, /bump, CHANGELOG, push, CI).

Order (leverage / risk):
- [ ] **3a.1 — search_select** (`source:` typeahead). Legacy `_render_search_select`: hidden `#field-{name}` + visible text `<input hx-get hx-trigger="keyup changed delay:Nms" hx-target="#search-results-{name}">` + Alpine `x-show=open`. Primitive `SearchSelect`. **Fidelity gate (`fidelity_scorer` `_check_*_interaction`) must stay green** — it expects `data-dz-widget`/hidden-input shape; pin it. THE BLOCKER — do first, prove on a search_select example app via fidelity.
- [ ] **3a.2 — money** (first-class type). Legacy `_render_money`: `x-data="dzMoney"`, major text `inputmode=decimal` + hidden `{name}_minor` + hidden `{name}_currency`, optional currency `<select>`. Primitive `MoneyField`. Prove on `pra`.
- [ ] **3a.3 — combobox parity** (existing `Combobox`). Legacy wires `data-dz-widget=combobox data-dz-options='{...}'` (TomSelect); substrate emits plain `<select>`. Bring `Combobox`/`_emit_combobox` to the TomSelect mount-attr contract (without breaking the already-shipped detail/list use of Combobox, if any).
- [ ] **3a.4 — picker** (Flatpickr). Legacy `_render_date_picker`: `data-dz-widget=datepicker data-dz-options='{"dateFormat":"Y-m-d"[,"enableTime":true]}'`. Primitive `DatePicker` (or `Field` kind ext). Map date vs datetime.
- [ ] **3a.5 — rich_text.** Legacy `_render_rich_text`: `data-dz-widget=richtext data-dz-options` + hidden input + `data-dz-editor` div; honors `rich_text_toolbar`, `rich_text_max_length`. Primitive `RichText`.
- [ ] **3a.6 — slider.** Legacy `_render_slider`: `data-dz-widget=range-tooltip` + `<input type=range data-dz-slider>` + `<span data-dz-range-value x-text>`. Primitive `Slider`.
- [ ] **3a.7 — color.** Legacy `_render_color`: `x-data="{value}"` + `<input type=color x-model>` + `<span x-text>`. Primitive `ColorField`.
- [ ] **3a.8 — tags.** Legacy `_render_tags`: `data-dz-widget=tags data-dz-options='{"create":true,"plugins":["remove_button"]}'`. Primitive `TagsField`.
- [ ] **3a.9 — wizard stepper** (multi-section interactivity). Legacy `render_form_stepper`: `x-data="dzWizard"` on the form shell + `<ol class=dz-form-stepper>` Alpine step nav. The substrate `FormSection` renders groups but doesn't wire dzWizard. Thread the stepper onto `FormStack` (only when ≥2 sections). Prove on an experience wizard + a multi-section form.

**3a gate:** `component_showcase` + `pra` + the search_select example apps render every widget via the substrate (when the surface opts `render: fragment`) at attribute parity; fidelity green; full suite + card-safety + a11y green. Legacy still default (not flipped) — the substrate path is exercised via explicit `render:` or a targeted test harness until 3b.

## Phase 3b — flip + delete

- [ ] **Task 1 — FLIP.** `page_routes._maybe_dispatch_inner_html` gate (~:1943): add `SurfaceMode.CREATE, SurfaceMode.EDIT` to the dispatch set so unset-`render` forms dispatch to the substrate. Re-baseline form goldens (inspect every diff — D1). **Breaking-ish (CHANGELOG):** forms gain the proper `<form>` wrapper + submit button (#1291 fix, now universal) + the substrate field markup (`dz-field` vs legacy `dz-form-field`).
- [ ] **Task 2 — independent adversarial review (pre-flip-confirm).** Fresh general-purpose subagent: hunt field-value/widget regressions across the full widget matrix (the Phase-2 review caught ref→UUID, money→minor-units, badge→lost-chrome). Fix all findings before confirming the flip. Ship the flip.
- [ ] **Task 3 — independent adversarial review (pre-delete) + DELETE.** Review the missed-caller surface (Phases 1–2 lesson: build-ui/serve/fidelity/experience steps render forms without services; E2E-PG catches them). Then delete `form_renderer.py` (~806 LOC) + the dead `_render_multi_select`/`_render_date_range`. Repoint:
  - `template_renderer._render_body_inner` form branch (`:41-71`) → loud `RuntimeError` (D4).
  - `experience_renderer._render_form_step_body` (`:62-125`, uses `render_form_field` + `render_form_stepper`, page↛http) → substrate via the http experience route pre-render (extend `_render_experience_surface_step` to forms, or a parallel seam).
  - `static_preview` CREATE/EDIT branches → `surface_body_renderer` (already generalised in Phase 2 — verify it covers forms).
  - `fidelity._render_for_fidelity` → already dispatches list+detail; extend to form ctx (`ctx.form`).
  - Remove any `render_form_field`/`render_form_stepper` re-exports.
  - Migrate/delete legacy widget tests; regen complexity/clone/deferred baselines.
- [ ] **Task 4 — ADR/CHANGELOG/ship.** ADR-0049 status → **Phase 3 (forms) SHIPPED → ADR fully realised (substrate is THE universal render path; legacy direct-template layer retired)**. CHANGELOG Removed + Agent Guidance. Bump, push, **monitor E2E (PostgreSQL) + fidelity tiers**.

## Phase 3 gate (ADR-0049 complete) — ✅ MET (v0.92.31)
- [ ] Every `mode: create`/`mode: edit` surface renders via the substrate; every fleet+fixture widget at parity; `form_renderer.py` deleted; fidelity green (search_select); full suite + card-safety + a11y + e2e/PG/browser tier green; `render is pure` + `page ↛ http` KEPT; goldens re-baselined with inspected diffs. **ADR-0049 fully delivered — the `render is None` fork is gone for all four surface modes.**
