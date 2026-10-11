# UX Catalogue MVP — GitHub Pages component gallery (Sub-project A)

**Status:** Approved design — ready for implementation plan.
**Context:** Developer-outreach UX catalogue. First of three sub-projects (A = MVP page proving the pipeline; B = exhaustive/registry-driven; C = polish/interactivity). This spec is **Sub-project A only**.

## Goal

Publish a **UX component catalogue** to the existing GitHub Pages docs site: one mkdocs
page showing a curated set of Dazzle region display modes (+ the new decorators) rendered
to **real HTML** from **real authored DSL**, each paired with its DSL snippet and a one-line
description. It must double as a **fidelity test** (renders the real DSL→IR→render path, so
it catches drift) and auto-publish via the existing `docs.yml` workflow.

## Why this is achievable (the rails already exist)

- **Publishing:** mkdocs (Material) already deploys to GitHub Pages (`manwithacat.github.io/dazzle/`)
  via `.github/workflows/docs.yml` on push to main.
- **Generator precedent:** `scripts/gen_reference_docs.py` already generates doc pages before
  `mkdocs build` (config-driven, has a `--mode=ci` staleness gate).
- **Serverless render:** `WorkspaceRegionAdapter().build(region, ctx)` → `FragmentRenderer().render()`
  produces real component HTML with no DB/server/browser.
- **Component CSS:** `src/dazzle/page/runtime/static/dist/dazzle.min.css` is a ready bundle.
- **Sample data:** `demo_data` is a first-class Dazzle concept (curated rows per app).

## Design decisions (locked during brainstorm)

1. **MVP first** — one curated page proving the pipeline; exhaustive coverage is Sub-project B.
2. **Render source = real DSL → IR → render** through the real orchestration + adapter, with
   sample data injected at the orchestration seam (no DB). Authentic; catches DSL→IR→render drift.
3. **Source fixture = extend `fixtures/component_showcase`** (additive): keep the existing
   form-widget gallery (it backs widget-type capability demonstrations in
   `mcp/semantics_kb/capabilities.toml`), add a `ux_catalogue` workspace + `demo_data`. The
   canonical "every Dazzle UX component" fixture. (User granted latitude to replace the fixture
   en masse if simpler; additive is preferred because wholesale replacement would orphan the
   widget-capability `demonstrated_in` links — fallback only if additive hits friction.)
4. **Data-injection mechanism** — demo_data items for item-based modes; **canned sample buckets**
   (a small per-region manifest) served via a thin in-memory repository for aggregate/chart modes.
   Render/IR/orchestration all real; only the aggregate *numbers* are fixture-provided. Computing
   real aggregates over demo_data is a Sub-project B upgrade.
5. **Curated MVP mode set (8)**: `list` (+ the `outlier_on` decorator), `metrics`, `bar_chart`,
   `comparison`, `heatmap`, `pivot_table`, `bullet`, `kanban`. The remaining ~30 modes are
   Sub-project B.

## Non-goals (deferred, noted not built)

- Exhaustive coverage of all ~40 display modes (Sub-project B).
- A single registry/source-of-truth that auto-includes new modes (Sub-project B).
- Real aggregate computation over demo_data (Sub-project B) — MVP uses canned buckets.
- Live HTMX interactivity, theme toggle, in-page search, persona overlays, marketing embeds
  (Sub-project C).
- Screenshot/visual-regression imagery (the catalogue is live HTML, not images).
- Replacing/​restructuring `component_showcase`'s form-widget gallery.

## Architecture — four units

The stack: **fixture (content) → render harness (no-DB real render) → generator (page emit) →
publish (mkdocs/CI)**. Each is independently testable.

### 1. Fixture content — `fixtures/component_showcase`
- Add a `ux_catalogue` workspace whose regions are the 8 curated modes (one region per mode),
  sourced from one or two small entities added for this purpose (e.g. a `Metric`/`Item` entity
  with the numeric + enum + date + FK fields the modes need). The existing `Showcase` form entity
  + its widget surface stay untouched.
- Add `demo_data` rows (under the fixture's `dsl/seeds/demo_data/` or `demo_data/`) for the
  catalogue entities so item-based modes (`list`, `bullet`, `kanban`, `heatmap`) have content.
- The `list` region carries `outlier_on:` to showcase the new decorator inline.
- Regenerate `tests/unit/fixtures/dazzle_validate_baseline.json` (the fixture's validate output
  changes); update the fixture's `expected/` references if guides/compliance shift.

### 2. Render harness — `src/dazzle/testing/ux_catalogue.py` (new; importable by both the generator script and the fidelity test; no I/O beyond reading the fixture)
- A function `render_region_html(appspec, region, *, sample) -> str` that:
  1. Builds the orchestration inputs for `region` (the `WorkspaceRegionContext`, a fake request,
     a no-auth user context, the resolved `columns`), reusing the **existing page-route /
     context-builder helpers** rather than reconstructing them by hand. **(Key implementation task
     — the plan pins the exact reusable entry point; if driving full orchestration proves too
     heavy, the plan may select the highest existing route-handler seam and feed it fakes.)**
  2. Provides sample data via an **in-memory repository**: item lists from demo_data; for
     aggregate modes, an `aggregate(...)` that returns the region's **canned buckets** from the
     catalogue manifest (objects exposing `.dimensions` / `.measures` as the real repo does).
  3. Runs the **real** `compute_region_render_inputs` → `WorkspaceRegionAdapter.build` →
     `FragmentRenderer.render`, returning the HTML string.
- A **catalogue manifest** (`fixtures/component_showcase/ux_catalogue.manifest.toml` or a Python
  dict in the harness) mapping each catalogued region → `{description, canned_buckets?}`. This is
  the one place sample aggregate numbers live.

### 3. Generator — `scripts/gen_ux_catalogue.py` (mirrors `gen_reference_docs.py`)
- Loads the `component_showcase` AppSpec, iterates the `ux_catalogue` regions in declared order.
- Per region: `html = render_region_html(...)`, extract the region's DSL snippet (slice the
  source `.dsl` by the region's parsed line span, or re-emit from IR), read its description from
  the manifest.
- Emits `docs/reference/ux-catalogue.md`: intro + per-mode section = `## <Title>` · description ·
  the rendered HTML wrapped in `<div class="dz-catalogue-preview">…</div>` · a fenced ` ```dsl `
  block with the snippet.
- `--mode=ci`: regenerate to a temp buffer and `diff` against the committed page; exit non-zero on
  drift (matches `gen_reference_docs.py`), so a stale page fails CI.

### 4. Publish — mkdocs + `docs.yml`
- Copy the framework CSS bundle into the docs assets (e.g. `docs/assets/dazzle.min.css`, plus
  `tokens.css`/`dz-tones.css` if the bundle doesn't already include them) and add it as mkdocs
  `extra_css`. **Scope** it: wrap previews in `.dz-catalogue-preview` and, if the bundle's
  selectors are global enough to fight the Material theme, prefix the catalogue CSS under that
  wrapper during the copy step (the plan decides scoping vs raw-include after inspecting the
  bundle's selector specificity).
- Add `UX Catalogue` to mkdocs `nav`.
- Add a `python scripts/gen_ux_catalogue.py` step to `docs.yml` **before** `mkdocs build`
  (alongside the existing `gen_reference_docs.py` step).

## Testing

- **Fidelity gate** (`tests/unit/test_ux_catalogue.py`): for every region in the `ux_catalogue`
  workspace, `render_region_html(...)` returns non-empty HTML containing that mode's expected
  primitive marker (e.g. `dz-bar-track`/`role="progressbar"` for comparison, `data-dz-tone` on the
  `outlier_on` row, a `<table>` for list/pivot). This is the real-render drift detector.
- **Generator staleness**: `gen_ux_catalogue.py --mode=ci` in the docs workflow (and optionally a
  unit test) fails if `docs/reference/ux-catalogue.md` is out of date.
- **Fixture validates**: `cd fixtures/component_showcase && dazzle validate` exit 0; existing
  `test_example_index.py` (asserts the fixture exists/validates) stays green; regen the validate
  baseline.
- **Full suite**: `pytest -m "not e2e"` green before ship (golden-master / docs-drift live outside
  the gate subset). The 3 `test_fuzzer_oracle` failures are pre-existing pollution — ignore.

## Risks / open implementation questions (pinned in the plan, not fabricated here)

- **Orchestration-input construction (the main risk):** building a real `WorkspaceRegionContext` +
  request + user context + columns without a server. The plan must find the highest reusable
  builder (page-route layer) and drive it with fakes + the in-memory repo; if full orchestration is
  disproportionate for the MVP, the plan may justify the highest authentic seam that still exercises
  DSL→IR→render. This is the one part that could expand scope — the plan front-loads a spike on it.
- **CSS scoping:** whether `dazzle.min.css` can be included raw or must be prefix-scoped under
  `.dz-catalogue-preview` to avoid clobbering Material. Decided by inspecting the bundle.
- **DSL-snippet extraction:** by source-line span (needs the parser to expose the region's line
  range) vs re-emitting from IR. The plan picks one.

## Deferred (each its own future sub-project / brainstorm)

- **Sub-project B:** exhaustive coverage (all display modes + every decorator), registry-driven
  single-source-of-truth so new modes auto-appear, real aggregate computation over demo_data,
  per-mode "anatomy"/contract notes.
- **Sub-project C:** live HTMX interactivity, theme/dark-mode toggle, in-page search, per-persona
  overlays, marketing-site embedding.
