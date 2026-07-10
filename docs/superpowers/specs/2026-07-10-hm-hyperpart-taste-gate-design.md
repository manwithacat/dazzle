# HM Hyperpart taste-gate — deterministic component-discipline gate + on-demand vision (#1567, slice 1)

**Date:** 2026-07-10
**Issue:** #1567 (slice 1 of 2)
**Status:** Design approved
**Depends on:** #1566 (HM design-context — shipped v0.101.9)

## Context

#1567 bundles two affordances: (1) a **Hyperpart taste-gate** that holds a newly-authored
HM component to the house aesthetic at *authoring time*, and (2) a supported path for an
agent to stand up a **new property** (family pick/author + auto-score). Per the approved
scope decision, this spec covers **only affordance 1**; affordance 2 (the new-property
authoring path) is deferred to its own spec.

The model-driven-failure-modes review rule (`docs/architecture/model-driven-failure-modes.md`)
is the governing constraint: *a detector that isn't live in the normal workflow doesn't count.*
So the gate must be cheap and deterministic enough to run every time (in `pytest -m gate` +
CI), not a documented-but-dormant check.

### What already exists (so we don't rebuild it)

- **`dazzle qa taste-panel`** — blind vision-LLM judges scoring whole rendered *pages*, fleet
  vs dialect references. Expensive (subscription/API-billed), page-level, on-demand. NOT a
  per-component live gate.
- **Card-safety** (`src/dazzle/testing/ux/contract_checker.py`) — deterministic scanners over
  *rendered DOM*, enforced live by the composite gate `tests/unit/test_htmx_workspace_composite.py`.
  Already covers a new component's rendered output. We **reference** it, not re-implement.
- **`core/sitespec_hygiene.py`** (#1566) — deterministic CSS-text structural scoring, but its
  6 dimensions are landing-page-specific (fluid type, section rhythm, containers). Not a
  component rubric — it's the *pattern to mirror*, not the thing to reuse.
- **#1566 `core/design_context.py`** — the unified facade. Its surface × method matrix records
  `app_internals × deterministic` as an **empty cell** (the honest gap: no deterministic
  app-internals rubric exists yet).

### The organizing insight

A new Hyperpart is a CSS file (+ optional controller). A cheap, deterministic per-component
score of *token discipline* is exactly the `app_internals × deterministic` rubric that #1566's
matrix flagged as missing. **This gate fills that empty cell.** The gate is not a bolt-on lint;
it is the fourth rubric in the design-context, and its dimensions map into the same concept
vocabulary.

Corpus measurement (2026-07-10, the ~65 `components/*.css` files) confirms the score is
*discriminating*, not saturated: `button.css`/`alert.css` use 0 hardcoded hex colours, while
`table.css` (7) and `dashboard-card.css` (4) carry a few; `px` literals are ~0 fleet-wide
(everything is rem/tokens). So a per-component floor catches a rogue new component that sprays
raw values while the disciplined corpus sits high.

## Goal

A live, deterministic, per-component floor gate that holds every HM component (`packages/hatchi-maxchi/components/*.css`)
to token discipline — registered into #1566's design-context so it fills the empty
`app_internals × deterministic` matrix cell — plus an on-demand advisory vision command for a
judged "does it look right" read, plus an authoring-workflow doc that makes all three
discoverable.

## Design

Five parts, in dependency order.

### Part A — `core/component_hygiene.py` (the deterministic rubric)

A new module mirroring `core/sitespec_hygiene.py` structurally:

- `ComponentDimension` — frozen dataclass `(key: str, weight: int, description: str, check: Callable[[str], tuple[float, str]])`.
- `COMPONENT_HYGIENE_DIMENSIONS: tuple[ComponentDimension, ...]` — weights sum to 100:
  - **`colour_tokens`** (40) — fraction of colour declarations (`color:`, `background`, `border-color`,
    `fill`, `stroke`, and colour stops) whose value is `var(--…)`-driven vs a raw hex/`rgb(`/`hsl(`/
    named colour. The discriminating check.
  - **`namespace`** (20) — fraction of class selectors that use the `.dz-` namespace (HM convention).
  - **`motion_tokens`** (20) — fraction of `transition`/`animation` declarations that reference a
    `var(--dz-transition…)`/`var(--…)` token vs an inline hardcoded duration/easing.
  - **`sizing_tokens`** (20) — fraction of `border-radius`/`padding`/`margin`/`gap` declarations
    that are token/var-driven or rem/em vs raw `px` (px=0 today → this is a regression-catcher).
- `score_component_css(css: str) -> dict[str, object]` — returns `{"total": float /100, "breakdown": {key: {sub_score, weight, points, detail}}}`, byte-for-byte
  the same shape `score_sitespec_css` returns (so tooling/report code is uniform).
- `hm_component_paths() -> list[Path]` — glob `packages/hatchi-maxchi/components/*.css`, sorted.
  Uses `Path(__file__).resolve().parents[3]` for the repo root (same idiom as `hm_sitespec_css`).

Each `check` is a pure `str -> (0..1, detail)` function with a regex over the CSS text; no I/O,
no render, DB-free. A declaration with no applicable properties (e.g. a component with zero
colour declarations) scores that dimension `1.0` with a "n/a" detail — absence is not a
violation.

`__all__` exports the dataclass, the tuple, `score_component_css`, `hm_component_paths`.

**HM-boundary note:** the module reads `packages/hatchi-maxchi/components/*.css` to *measure*
them (governance, not consumption) — exactly like `sitespec_hygiene` and the reservoir metric.
It is added to the `SANCTIONED` set in `tests/unit/test_hm_boundary.py` with that rationale.

### Part B — register the rubric into #1566's design-context

In `src/dazzle/core/design_context.py`:

- Append a fourth `RubricRef("component", "app_internals", "deterministic", tuple(d.key for d in COMPONENT_HYGIENE_DIMENSIONS))`
  to `RUBRICS`. This fills `matrix()[("app_internals", "deterministic")]` — no longer `None`.
- Extend `DESIGN_CONCEPTS` so every new component dimension is claimed by exactly one concept
  (the hard gate requires it): `component.colour_tokens → colour`, `component.namespace → structure`,
  `component.motion_tokens → motion`, `component.sizing_tokens → rhythm`.
- Update `render_markdown()` implicitly (it iterates `RUBRICS`/`matrix()`/concepts, so the
  matrix row for App internals now shows `core/component_hygiene.py (4 dims)` in the deterministic
  column and the ">app-internals × deterministic empty" caveat is removed/reworded to reflect
  that the cell is now filled).
- Regenerate `docs/reference/hm-design-context.md` via `scripts/gen_design_context.py`.

The #1566 claim-integrity gate (`tests/unit/test_design_context.py`) now automatically covers
the 4 new dimensions (every dimension claimed by exactly one concept; total dimension count
becomes 24). Its `test_accessor_shapes` count and the matrix "empty cell" assertion are updated
to reflect the filled cell.

### Part C — the per-component floor gate (the live enforcement)

`tests/unit/test_component_hygiene.py`, `pytestmark = pytest.mark.gate`, DB-free:

- `test_every_component_clears_the_floor` — for each `hm_component_paths()` file, assert
  `score_component_css(text)["total"] >= FLOOR`. `FLOOR` is a module constant set just below the
  current corpus minimum (measured during implementation, then rounded down — e.g. if the weakest
  real component scores 88.0, FLOOR = 85.0). A new Hyperpart is scored automatically and must
  clear the floor to ship. The failure message names the component and its weakest dimension.
- `test_floor_is_a_real_ratchet` — assert `FLOOR` is within a sane band (e.g. `70 <= FLOOR <= corpus_min`)
  so nobody accidentally sets it to 0. (Locks the gate's teeth in.)
- Card-safety is **already** enforced live by the composite gate — this file adds a comment
  pointing there and does not duplicate DOM scanning.

No git-diff logic: the whole corpus is scored every run, so the floor holds existing components
to the standard *and* auto-covers new ones (per the approved per-component-floor decision).

### Part D — `dazzle qa component-vision` (on-demand advisory, NOT in CI)

A new `qa` subcommand that gives a judged "does it look right" read on a single component:

- `dazzle qa component-vision <component-name> [--model …] [--judges 3] [--out .dazzle/qa/component-vision]`.
- Pipeline: resolve `<component-name>` to a `component_showcase` surface → render its region HTML
  via the existing no-DB harness (`src/dazzle/testing/ux_catalogue.py` render path) → screenshot
  with Playwright (same capture approach as the vision pilot / `capture_sitespec_references.py`) →
  score the image with `taste_panel.score_image` against `taste_rubric` → print an advisory
  per-dimension score + write the JSON/MD report.
- **Advisory only** — exit 0 always (it is not a gate); subscription/API-billed; explicitly
  documented as on-demand. Components without a `component_showcase` surface return a clear
  "no showcase surface for <name> — add one to score it" message and exit non-zero (usage error,
  not a taste failure).
- Reuses `taste_panel` machinery wholesale; no new judging logic.

### Part E — authoring-workflow doc

A short **"Authoring a new Hyperpart"** section appended to `docs/reference/hm-design-context.md`
(the #1566 entry-point — keeps one HM-authoring home). Since that page is generated, the section
is emitted by `render_markdown()` as static prose (a constant appended after the rubric-sources
section). It says, terse and imperative:

1. Use HM tokens (`var(--dz-…)`), the `.dz-` namespace, and `--dz-transition*` — the
   **component-discipline floor** (`test_component_hygiene.py`) enforces this on every commit.
2. If your component renders a card/region, the **card-safety composite gate** covers its
   rendered DOM automatically.
3. For a judged "does it look right" read, run **`dazzle qa component-vision <name>`** (on-demand,
   advisory).

## Out of scope (deferred)

- **Affordance 2** — the new-property authoring path (family pick/author against exemplars +
  auto-score). Separate spec; #1567 stays open with a pointer to this slice + the deferred slice.
- No change to `taste_panel`, the vision rubric, or the card-safety scanners.
- No new MCP tool (doc-first, matching #1566's YAGNI stance).
- No auto-fix / auto-tokenization of a low-scoring component — the gate reports, the author fixes.

## Testing / verification

- `tests/unit/test_component_hygiene.py` — per-component floor + ratchet-band, `pytest.mark.gate`,
  DB-free.
- `tests/unit/test_design_context.py` — updated for the 4th rubric: filled matrix cell, 24
  dimensions, every component dimension claimed by exactly one concept (the existing hard gate
  now covers them for free).
- Regenerated `docs/reference/hm-design-context.md` (doc-drift gate stays green).
- `dazzle qa component-vision` — a light unit test on its render→score glue with a **mocked**
  judge (no real API call): assert it resolves a known showcase component, produces a report, and
  errors cleanly on an unknown component. The real vision path stays on-demand/manual.
- `mypy src/dazzle`, `ruff`, `pytest -m gate`, `mkdocs build --strict` all green.

## Ship

`/bump patch` + `/ship`. Patch release (adds a rubric + gate + advisory command; no breaking
change). Close scope-1 with a comment on #1567 noting slice 1 shipped and slice 2 (new-property
path) deferred to its own spec; leave #1567 **open** for slice 2.
