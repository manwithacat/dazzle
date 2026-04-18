# Card-Safety Invariants

Canonical spec for what "a card" means in Dazzle templates and the
eight invariants every card-bearing surface must satisfy. Extracted
from the #794 post-mortem — a single bug that shipped three times
before the underlying class of risk was fully named.

This document is the contract the shape-nesting and duplicate-title
scanners enforce. A new region template, new dashboard layout, or
new fragment primitive that violates an invariant here is a
regression — CI will fail. When you're tempted to change one of
these rules, update this doc first and make the reasoning explicit.

---

## Background: the #794 class of risk

**Symptom**: a dashboard card shows a second card inside it, often
with the same title printed twice. User sees "a card within a card."

**Root cause, all variants**: two layers of the rendering pipeline
each independently decide to emit card chrome (rounded corners +
border + background) and/or the card title. Nothing in the pipeline
was asserting that exactly one layer is responsible for each.

**Why it kept shipping**: each isolated template looked fine on its
own. The bug only appeared when the dashboard slot and the HTMX-
loaded region fragment were concatenated in a real browser. Our QA
was testing each layer alone. Three fix attempts (2e9ca0cc,
b5e3ef85, v0.57.36) all addressed real sub-variants — wrapper chrome,
grid-item chrome, macro chrome — but the ones they missed were only
visible post-composite.

The remedy is structural:

1. **One layer owns card chrome**: the dashboard slot.
2. **One layer owns the card title**: the dashboard slot.
3. **Everything else renders bare content**.
4. **Tests assert the composite, not the layers**.

---

## What counts as "card chrome"

A DOM element is card chrome iff it is a **block container** AND has
**both**:

- a `rounded-*` class (any scale, including arbitrary values like
  `rounded-[6px]`, side-scoped like `rounded-t-md`), and
- a **full border** (`border`, `border-<shade>`, `border-<color>`)
  that is NOT side-scoped (`border-l-*`, `border-r-*`, `border-t-*`,
  `border-b-*`, `border-x-*`, `border-y-*` are accents, not card
  edges).

Block containers: `div`, `article`, `section`, `aside`, `nav`,
`main`, `header`, `footer`, `li`. Inline elements (`span`, `button`,
`a`, `input`, `td`) are explicitly excluded even when they carry
chrome-shaped classes — a status-badge `<span>` with `bg-primary
rounded-full` is a pill label, not a card.

A background colour alone (`bg-*` without border) is also **not**
chrome. Progress-bar tracks (`bg-muted rounded-full`), kanban column
backdrops (`bg-muted/0.4 rounded-[6px]`), and filled tiles are
decorative fills, not card surfaces. This rule was tightened in
v0.57.37 after the composite gate over-flagged them.

Enforcement: `_has_card_chrome()` in
`src/dazzle/testing/ux/contract_checker.py`.

---

## The eight invariants

### INV-1: No nested card chrome

**Rule**: No card chrome element may have an ancestor that is also
card chrome.

**Why**: Two nested card surfaces read as a card-within-a-card. The
eye can't distinguish "decorated section" from "child card" when
both have the same rounded + bordered + filled edge.

**Enforcement**:
- Scanner: `find_nested_chromes(html)` in `contract_checker.py`
  returns the list of `(outer_tag, inner_tag)` pairs.
- Applied during `check_contract()` for `WorkspaceContract` and
  `DetailViewContract`.
- Tests: `test_ux_contract_checker.py::TestFindNestedChromes::*`
- Composite test: `test_template_html.py::TestDashboardRegionCompositeShapes::test_composite_has_no_nested_chrome`

**Bad shape** (pre-v0.57.36):
```html
<article class="rounded-md border bg-[hsl(var(--card))]">        ← outer chrome
  <div class="bg-[hsl(var(--card))] border rounded-[6px]">       ← nested chrome ✗
    chart content
  </div>
</article>
```

**Good shape**:
```html
<article class="rounded-md border bg-[hsl(var(--card))]">
  <div data-dz-region id="region-x">                             ← bare hook
    chart content
  </div>
</article>
```

---

### INV-2: No duplicate title within a card

**Rule**: A card container may contain at most one heading (`<h1>`
through `<h6>`) with any given text.

**Why**: Duplicate titles are the symptom AegisMark reported for
#794 — `page.get_by_text("Grade Distribution").count() == 3`. Two
layers both rendering the title is the structural bug; the visible
shape is a card with its header text showing twice.

**Enforcement**:
- Scanner: `find_duplicate_titles_in_cards(html)` in
  `contract_checker.py`.
- Tests: `test_ux_contract_checker.py::TestFindDuplicateTitlesInCards::*`
- Composite test: `test_template_html.py::TestDashboardRegionCompositeShapes::test_composite_has_no_duplicate_titles`

**Bad shape**:
```html
<div data-card-id="card-0">
  <article>
    <h3>Grade Distribution</h3>       ← dashboard header
    <div data-dz-region>
      <h3>Grade Distribution</h3>     ← region renders title too ✗
      ...
```

**Good shape**: only the dashboard slot renders the title. Regions
never render a `<h3>` containing the region's title.

---

### INV-3: Side borders are accents, not card edges

**Rule**: `border-l-*`, `border-r-*`, `border-t-*`, `border-b-*`,
`border-x-*`, `border-y-*` are permitted alongside card chrome and
do not themselves constitute chrome.

**Why**: Dazzle uses left-border accents for attention states
(critical/warning/notice) on items inside a region. An accent stripe
on a queue row or timeline event must not falsely trigger the
nested-chrome gate — it's a visual cue, not a bounded surface.

**Enforcement**: `_is_side_border_class()` in
`contract_checker.py`. Test: `test_ux_contract_checker.py::
TestFindNestedChromes::test_side_border_is_not_chrome`.

---

### INV-4: Bg-only rounded is not chrome

**Rule**: An element with `rounded-*` and `bg-*` but no full border
is not card chrome.

**Why**: Progress-bar tracks (`bg-muted rounded-full`), kanban
column backdrops (`bg-muted/0.4 rounded-[6px]`), and filled tiles
are decorative fills — they don't draw a card edge. Before this
tightening (v0.57.37) the scanner over-flagged them as
card-in-card, producing false positives in bar_chart and kanban
regions.

**Enforcement**: `_has_card_chrome()` requires `has_full_border`.
Test: `test_ux_contract_checker.py::TestFindNestedChromes::
test_ignores_bg_only_rounded`.

---

### INV-5: Inline tags are never cards

**Rule**: Only block containers (`div`, `article`, `section`,
`aside`, `nav`, `main`, `header`, `footer`, `li`) may be classified
as chrome. Inline tags (`span`, `button`, `a`, `input`, `td`, etc.)
are ignored by the scanner.

**Why**: Pills, badges, and buttons frequently have rounded-plus-bg
classes (`bg-primary rounded-full`) because that's how they look
like pills. They are not cards. Scoping chrome detection to block
tags eliminates this false-positive source.

**Enforcement**:
`_NestedChromeScanner._CARD_CANDIDATE_TAGS` + `_DuplicateTitle
Scanner._is_card`.

---

### INV-6: Region templates emit zero chrome

**Rule**: Every template under
`src/dazzle_ui/templates/workspace/regions/*.html`, and the shared
`macros/region_wrapper.html::region_card`, must emit **no** card
chrome (no rounded + full border + bg on any block container).
Items inside a region (rows, tiles, events) must also be bare —
padding + optional hover bg + optional side-border accent are
fine; a full border turns them into nested cards.

**Why**: Regions are always rendered into a dashboard card slot
which already owns chrome. Any chrome a region adds is necessarily
nested chrome. This is the root cause of three-out-of-three
pre-v0.57.37 follow-ups to #794.

**Enforcement**:
- Single render site verification: regions are rendered ONLY via
  `_fetch_region_html()` in `src/dazzle_back/runtime/
  workspace_rendering.py:879`. If a new render site is added,
  re-validate the invariant there.
- Jinja test: `test_template_html.py::TestWorkspaceRegionRendering::
  test_grid_region_does_not_nest_card_chrome`.
- Composite test (all regions × sample contexts):
  `TestDashboardRegionCompositeShapes::test_composite_has_no_nested_chrome`.
- Macro gate: `TestDashboardRegionCompositeShapes::
  test_bare_region_card_macro_stays_bare` pins that `region_card`'s
  source file contains none of the banned class strings.

---

### INV-7: Region templates emit zero title

**Rule**: Region templates must not render a `<h1>`–`<h6>`
containing the region's title. Other headings (subsection labels,
metric group names) are permitted but must be unique text within
the card.

**Why**: Companion to INV-2. The dashboard card header already
renders the card title from Alpine state. A region that also
renders the title produces the three-copies-in-DOM symptom.

**Enforcement**:
- Composite test: `TestDashboardRegionCompositeShapes::
  test_composite_has_no_duplicate_titles`.
- Manual grep: `grep "{{ title }}" src/dazzle_ui/templates/workspace/
  regions/*.html` should return empty.

---

### INV-8: Tests must run on the composite, not the layers

**Rule**: Any shape-safety test intended to gate regressions in
dashboard output must feed the scanner the **post-HTMX-hydration
DOM** — the initial page + each fetched region stitched in — not
individual templates in isolation.

**Why**: Every pre-v0.57.37 attempt to fix #794 was validated by a
passing isolated-template test. The bug lived in the concatenation.
Isolated-template tests are useful for regressing sub-invariants,
but the gate of record is the composite.

**Enforcement**:
- Jinja-level: `TestDashboardRegionCompositeShapes` renders the
  dashboard-slot shell + each region template and runs both
  scanners on the composite.
- HTTP-level: `HtmxClient.get_workspace_composite(path)` in
  `htmx_client.py` follows the HTMX boot sequence and returns the
  real post-hydration DOM. Used by `dazzle ux verify --contracts`
  for every `WorkspaceContract`.
- Stitcher: `assemble_workspace_composite(initial_html,
  region_htmls)` — pure function, unit-tested in
  `test_htmx_workspace_composite.py`.

---

### INV-9: Primary actions are reachable without pointer hover

**Rule**: Any button (or `<a role="button">`) whose `aria-label`
names a destructive/state-changing action — Remove, Delete,
Dismiss, Close, Archive, Unarchive, Disable, Deactivate, Revoke —
must not live inside an `opacity-0 group-hover:opacity-100` (or
equivalent hover-only reveal) ancestor without also having a
non-hover reveal (`focus-within:opacity-*`, `focus:opacity-*`,
`peer-focus:opacity-*`, `group-focus:opacity-*`,
`group-focus-within:opacity-*`).

**Why**: Touch devices have no hover state — a hover-only reveal
is permanently invisible. Keyboard users must know to move the
pointer into the card before Tab can reach the action. Issue #799
shipped this exact shape on every dashboard card.

**Enforcement**:
- Scanner: `find_hidden_primary_actions(html)` in
  `contract_checker.py`.
- Applied inside `check_contract` for `WorkspaceContract` and
  `DetailViewContract` — same dispatch point as INV-1 / INV-2.
- Tests: `test_ux_contract_checker.py::TestFindHiddenPrimaryActions::*`
  (10 cases covering opacity-0 detection, focus-within reveal,
  always-visible, Alpine conditional skip, non-primary-action
  label, link-button role, missing aria-label, button-level
  opacity-0, post-fix shape pass, multiple hidden actions).

**Bad shape** (pre-v0.57.46):
```html
<div class="opacity-0 group-hover:opacity-100">
  <button aria-label="Remove card">×</button>   <!-- invisible on touch ✗ -->
</div>
```

**Good shape** (post-v0.57.46):
```html
<div class="opacity-60 group-hover:opacity-100 group-focus-within:opacity-100">
  <button aria-label="Remove card">×</button>
</div>
```

Notes on the detection rule:
- **Alpine conditional ancestors** (`x-show` / `x-if` / `x-cloak`)
  are treated as orchestrated reveals and skipped. A "Close panel"
  button inside `x-show="open"` is perfectly valid.
- **Non-primary-action labels** (Submit, Save, Continue) are not
  targets of this gate — hover-only reveal on those is a separate
  design concern.
- **Missing `aria-label`** means the button can't be classified;
  the gate is silent (absent accessibility-label is handled by a
  separate concern).

---

## Adding a new invariant

If you find a new class of card-safety regression:

1. Give it a name (INV-N) and add a section here.
2. Add a named test that reproduces the bad shape and verifies the
   fix. Prefer a regression test inside
   `tests/unit/test_ux_contract_checker.py` (scanner-level) or
   `tests/unit/test_template_html.py::
   TestDashboardRegionCompositeShapes` (composite-level).
3. Update the relevant scanner in
   `src/dazzle/testing/ux/contract_checker.py`.
4. Ship.

Avoid inventing a new scanner just for one case — the existing
`find_nested_chromes` and `find_duplicate_titles_in_cards` cover the
class well. A new invariant usually tightens or relaxes the input
heuristic rather than adding new machinery.
