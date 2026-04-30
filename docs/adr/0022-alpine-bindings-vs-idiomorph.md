# ADR-0022: Alpine Bindings on Idiomorph-Morphed Elements

**Status:** Accepted
**Date:** 2026-04-30
**Related:** ADR-0011 (SSR + HTMX), [#963](https://github.com/manwithacat/dazzle/issues/963), [#964](https://github.com/manwithacat/dazzle/issues/964), [#968](https://github.com/manwithacat/dazzle/issues/968), [#970](https://github.com/manwithacat/dazzle/issues/970)

## Context

Dazzle's UI runtime stack is HTMX + idiomorph + Alpine.js (see ADR-0011). Each layer has clean semantics in isolation:

- **HTMX** swaps server-rendered HTML fragments into the page on demand
- **idiomorph** (htmx's morph extension) does smart in-place DOM updates — preserves stable nodes, mutates only what changed
- **Alpine.js** binds reactive state to DOM via `x-data`, `x-init`, `x-for`, `@click`, `:value`, etc.

The three layers interact at the moment of a morph swap. idiomorph walks the new HTML and, for each element, iterates `newElement.attributes` calling `target.setAttribute(name, value)` to bring the existing DOM node into alignment. This is where the abstractions leak: idiomorph treats Alpine attributes as opaque HTML, but Alpine attributes have semantics that browsers and idiomorph don't understand.

Four bugs in 30 days, all the same shape:

| Issue | Symptom | Mechanism |
|-------|---------|-----------|
| #963 | `InvalidCharacterError` on `data-card-catalog` morph | Attribute value contained `"` from `tojson`, closed the HTML attribute prematurely; browser parsed JSON keys as separate attributes |
| #964 | `InvalidCharacterError: '@click' is not a valid attribute name` | idiomorph called `setAttribute('@click', ...)`; Chromium enforces HTML attribute-name production strictly, rejects `@` |
| #968 | `Unexpected token '}'` Alpine error | Same as #963 but on `@dblclick`; `tojson` output's `"` closed the attribute, Alpine evaluated the truncated expression |
| #970 | `Alpine Expression Error: opt is not defined` | `<template x-for="opt in options">` with `:value`/`x-text` on cloned children; idiomorph evaluated child bindings before Alpine re-established the x-for scope |

Each fix was sound but local. The pattern is general enough to memorialise as policy: **Alpine and idiomorph have a structural disagreement about who owns morphed-element attributes, and the safe default is to keep Alpine off those elements.**

## Decision

When an element will be inside an htmx-morphed region, **prefer server-rendered static HTML over Alpine bindings** wherever possible. When Alpine reactivity is genuinely needed, prefer **direct DOM manipulation in `x-init`** over declarative bindings on morphable children.

Specifically, in framework templates (`src/dazzle_ui/templates/**`):

| Pattern | Status | Rationale |
|---------|--------|-----------|
| `<template x-for="X in Y">` rendering Alpine-bound children | ❌ Forbidden | idiomorph evaluates child bindings before x-for scope rebinds — #970 class |
| `<element :value="..." x-text="...">` inside a morphed region | ⚠ Use sparingly | Reactive bindings on morphed elements work, but each adds an attribute idiomorph will iterate; the more bindings, the more chances for the #963/#968 attribute-value-escape bug class |
| `<element @click="..." @keyup="...">` inside a morphed region | ⚠ Tolerated only with the framework idiomorph patch | The `beforeAttributeUpdated` callback installed in `dz-alpine.js` (post-#964) skips `@`-prefixed attrs during morph. Without that patch, every `@`-attribute on a morphed element throws InvalidCharacterError on Chromium |
| `<element :data-foo="X | tojson">` (double-quoted attr with tojson) | ❌ Forbidden | Attribute terminates on the inner `"` — #963/#968. Drift gate: `TestNoDoubleQuotedTojsonAcrossTemplates` |
| `<element :data-foo='X | tojson'>` (single-quoted attr with tojson) | ✅ Allowed | The single-quoted attr survives JSON's inner double-quotes |
| Server-rendered `<option value="...">{{ label }}</option>` (no Alpine) | ✅ Preferred | No Alpine attributes for idiomorph to mishandle |
| `x-init="dzPopulateSelect($el)"` with helper that does `createElement` / `appendChild` | ✅ Preferred for dynamic | Children added imperatively carry no Alpine bindings; morph sees plain DOM |

### The two exceptions where Alpine on morphed elements IS fine

1. **The element itself owns its `x-data` scope.** A `<div x-data="dzWizard()">` inside a morphed region works because Alpine's `destroyTree` + `initTree` (already wired in `dz-alpine.js` post-#945/#948) re-establishes the scope on every morph. The risk is purely on *children* whose scope binds via parent context (`x-for`, inherited `x-data`).

2. **Static utility classes via `:class`.** Bindings whose value is a constant or depends only on `this` (e.g. `:class="loading ? 'opacity-50' : ''"`) don't have the scope-rebind problem. They evaluate cleanly. Still subject to attribute-value escaping rules.

When in doubt, **render the static case server-side and reach for Alpine only when reactivity is required**. Server-rendered HTML is the default; Alpine is the escape hatch.

### Why this ordering

Each of the four bugs cost a release cycle to fix and shipped a new drift gate to prevent regression. The drift gates are individually narrow:

- `TestNoDoubleQuotedTojsonAcrossTemplates` — catches #963/#968
- `test_idiomorph_alpine_patch.py` — catches #964 patch removal
- `test_filter_bar_no_xfor.py` — catches #970-shape regressions in filter_bar specifically

But the same shape can recur in any new template. The drift gates protect the *known* surfaces; the policy protects the *future* ones. Without the policy, a well-intentioned author writing a new region template will reach for `<template x-for>` because Alpine docs encourage it, and the bug class repeats.

## Consequences

### Positive

- One bug class structurally retired (well, four bugs retired and a fifth prevented)
- New region templates default to the safe pattern without per-author research
- Server-rendered HTML is faster to first paint than Alpine-rendered HTML — performance side-effect
- The "x-for + Alpine bindings on children" anti-pattern stops appearing in framework code

### Negative

- Some genuinely reactive needs become more verbose. `dzPopulateSelect`-style helpers in `dz-alpine.js` are 30 lines where `<template x-for>` was 5
- New developers who know Alpine well may push back when their idiomatic solution is rejected. The pushback is correct (Alpine's idiomatic solution doesn't survive idiomorph) but uncomfortable
- The framework now prescribes a specific stack-adapter pattern, not just "use HTMX + Alpine"

### Neutral

- Project code (`# dazzle:route-override` handlers) is bound by the same policy when those handlers render markup that lands in a morphable region. Project-side templates that render fragments returned to htmx are subject to the rules
- The drift gate count keeps growing — at 54 tests now, expected to grow as the framework's surface does

## Implementation

### Existing controls

- `dz-alpine.js:patchIdiomorphForAlpineDirectives` (post-#964) installs a `beforeAttributeUpdated` callback on `Idiomorph.defaults.callbacks` that returns `false` for any `@`-prefixed attribute name. Required for any framework or project code using `@click` etc. inside a morphable region.
- `TestNoDoubleQuotedTojsonAcrossTemplates` walks every `*.html` under `src/dazzle_ui/templates/` and fails if any double-quoted attribute interpolates `tojson`.
- Per-bug drift gates listed above.

### New work this ADR implies

- A linter or drift gate that flags `<template x-for>` in framework templates **whose direct children carry any Alpine attribute** (not just `:value`/`x-text` — also `:class`, `:disabled`, `@click`, etc.). Filed as a follow-up.
- Documentation in `docs/guides/marketing-conformance.md` (and a future `htmx-stack-adapter.md`) pointing to this ADR.
- Pre-1.0 audit: every existing `<template x-for>` in the framework reviewed against this ADR, migrated to a `dz*` helper if children carry any Alpine attrs.

### Helper convention

Helpers that populate DOM imperatively in `x-init` should:

- Live in `dz-alpine.js` under the `window.dz` namespace
- Be exposed as `window.dz<Name>` AND `window.dz.<name>` (Alpine reads bare names from global; the namespaced form is for direct JS use)
- Take an `$el` reference as the first argument
- Read all server-side state from `data-*` attributes on `$el`, never from inline JS-string interpolation
- Return synchronously even if the population is async (helper handles async internally)

Example (canonical, from `dzFilterRefSelect`):

```js
window.dz.filterRefSelect = function (selectEl) {
  if (!selectEl || selectEl.tagName !== "SELECT") return;
  const refApi = selectEl.dataset.refApi;
  if (!refApi) return;
  const selectedValue = selectEl.dataset.selectedValue || "";
  // ... fetch + createElement + appendChild ...
};
window.dzFilterRefSelect = window.dz.filterRefSelect;
```

Template usage:

```html
<select data-ref-api="{{ api }}"
        data-selected-value="{{ value }}"
        x-init="dzFilterRefSelect($el)">
  <option value="">All</option>
</select>
```

## Alternatives Considered

### 1. Patch idiomorph more aggressively

Extend the `beforeAttributeUpdated` callback to skip every Alpine-prefixed attribute (`x-*`, `:`, `@`, `&`, etc.). Idiomorph would no longer evaluate any Alpine binding during morph; Alpine would handle them via its own re-init.

**Rejected.** Skipping `:value` / `:class` / `x-text` would leave morphed elements with stale state until Alpine re-runs init, which produces visible flicker. Worse, the skip would mask legitimate state-mutation paths where idiomorph SHOULD update the attribute (e.g. server pushes a fresh `:disabled="true"` state for the same element). The current narrow skip (`@`-only) is correct because Alpine event listeners are managed via `addEventListener` not attribute state, so skipping their morph is safe.

### 2. Replace idiomorph with a simpler diff algorithm

Some morph libraries don't iterate `attributes` at all; they replace whole elements when any attribute differs. That avoids the per-attribute setAttribute call entirely.

**Rejected.** Whole-element replacement breaks Alpine's `x-data` scope on every morph (the element is gone), defeating the purpose of using a morph extension. idiomorph's stability is what makes Alpine + HTMX work at all. The fix is to not put fragile Alpine attributes on morphable children, not to swap morph engines.

### 3. Server-render everything; abandon Alpine

The simplest answer to "Alpine has structural problems with idiomorph" is "don't use Alpine." For pages with no client-side state, this works.

**Rejected as a general policy** (kept as the *preferred default* for non-reactive content). Some surfaces genuinely need client-side reactivity: dashboards with live filters, drag-and-drop, debounced search. Alpine is the right tool for those — just not as a child of a morphable parent.

## See also

- ADR-0011 — SSR + HTMX architecture
- `src/dazzle_ui/runtime/static/js/dz-alpine.js` — patched idiomorph callback (#964) and `dzFilterRefSelect` (#970) helper
- `tests/unit/test_idiomorph_alpine_patch.py` — drift gate for the `@`-attribute skip
- `tests/unit/test_filter_bar_no_xfor.py` — drift gate for the `<template x-for>` ban in filter_bar
- `tests/unit/test_card_picker_attributes.py::TestNoDoubleQuotedTojsonAcrossTemplates` — drift gate for tojson-in-double-quoted-attribute pattern
- [#963](https://github.com/manwithacat/dazzle/issues/963), [#964](https://github.com/manwithacat/dazzle/issues/964), [#968](https://github.com/manwithacat/dazzle/issues/968), [#970](https://github.com/manwithacat/dazzle/issues/970) — the four bugs this ADR codifies
