# HaTchi-MaXchi icon system + gallery pedagogy — design

**Date:** 2026-07-04
**Status:** design — approved shape, pending spec review
**Scope:** the HM package (`packages/hatchi-maxchi/`), its GitHub-Pages gallery, and
the Dazzle-side consumer (`src/dazzle/render/fragment/icon_*.py`).

## Why

Two distinct problems, deliberately kept separate:

1. **A modern icon approach for HM** — the render architecture: how an icon becomes
   markup, how it's sized, how it's made accessible.
2. **A pedagogically sound way to demonstrate it on the static Pages gallery** — so the
   copy-paste snippets teach *canonical, well-styled htmx4* rather than burying the lesson
   under SVG noise.

Prior art considered and rejected: **icon fonts** (lose inspectable DOM, correct-by-default
a11y, no-FOUT, and require a font-generation build step — the wrong trade for a system whose
pitch is inspectable htmx). We stay on inline SVG, and add a sprite *delivery* mode, which is
the SVG-native way to get the icon-font's snippet brevity without its costs.

The architecture below is close to what HM/Dazzle already ship (inline SVG from a vendored
Lucide registry, `currentColor`, `aria-hidden` by default). This spec ratifies that and adds
four upgrades + the gallery model.

## Problem 1 — the icon system

### Source of truth (unchanged)

`packages/hatchi-maxchi/icons/registry.py` — the vendored Lucide subset (`ICONS: dict[str,str]`
of inner markup, `# AUTO-GENERATED` from `lucide-static`, regenerated via `gen_registry.py`).
This is the trust boundary: pinned upstream + regeneration gate, **not** runtime sanitisation.

### Default output: inline SVG (unchanged)

Known name → inline `<svg>` wrapping the registry inner markup, `stroke="currentColor"`,
`aria-hidden="true"`. Self-contained, no JS, renders with scripting disabled. This is what a
single isolated render (and Dazzle's default server render) emits.

### Upgrade 1 — a unified `.icon` CSS contract

Replace the scattered per-slot sizing (`.dz-card-delta svg { width: 0.875rem }`, badge svg
sizing, alert/empty-state boxes, …) with one base class + size modifiers:

```css
.icon {
  width: 1em; height: 1em;           /* scales with font-size */
  display: inline-block;
  vertical-align: -0.125em;          /* optical alignment with text */
  flex-shrink: 0;
  color: inherit; stroke: currentColor; fill: none;
}
.icon-solid { fill: currentColor; stroke: none; }
.icon-xs { width: .75rem;  height: .75rem;  }
.icon-sm { width: .875rem; height: .875rem; }
.icon-md { width: 1rem;    height: 1rem;    }
.icon-lg { width: 1.25rem; height: 1.25rem; }
.icon-xl { width: 1.5rem;  height: 1.5rem;  }
```

Blast radius: component CSS that currently sizes `svg` directly (badge, card, alert,
empty-state, menu, nav) migrates to the `.icon` class on the element. Same visual result;
one contract instead of N ad-hoc rules.

### Upgrade 2 — an accessibility escape hatch

Today both helpers *always* emit `aria-hidden="true"` — there is no way to render a meaningful
standalone icon. The helper gains a `label` option:

- `icon("search")` → `<svg class="icon icon-search" aria-hidden="true" …>` (decorative, default).
- `icon("trash", label="Delete")` → `<svg class="icon icon-trash" role="img" aria-label="Delete" …>`.

HM's convention stays "never icon alone" (WCAG 1.4.1) — icon+text everywhere, accessible name
on the button (`<button aria-label="…" class="icon-btn">`), icon `aria-hidden`. The `label`
option is the correct expression for the genuinely icon-only case, not the common path.

### Upgrade 3 — fail loud on an unknown name (dev)

Current helpers silently substitute (`fallback="inbox"`, or a `data-lucide` client span). A
typo renders the wrong icon and nobody notices. New behaviour:

- **Dev:** unknown name → raise (explicit error naming the missing icon).
- **Prod:** icons are preloaded at startup; startup fails fast if a referenced name is missing.
- The `data-lucide` client-hydration span stays available but becomes an *explicit opt-in* for
  the deliberately-grow-the-registry workflow, not a silent default.

A fitness/drift gate asserts every name referenced in HM markup + Dazzle emission exists in the
registry.

### Upgrade 4 — sprite mode, promoted to first-class

Emit a `<symbol>` sheet from the same registry; `mode="sprite"` renders
`<svg class="icon"><use href="#name"/></svg>`. `currentColor` and `.icon` sizing flow through
`<use>` into the symbol normally.

- **Same-document** `<use href="#id">` renders on Pages *and* local `file://` preview.
  (Only *external-file* `<use href="sheet.svg#id">` breaks on `file://` — we avoid it.)
- Recommended production form for any page with repeated icons (e.g. a table of row actions,
  which inlines one SVG copy per row today).
- Off by default; inline stays the default for isolated/self-contained renders.

### The helper API (converges the two existing helpers)

```
icon(name, *, class=None, label=None, decorative=True, mode="inline") -> str
```

- `class` — extra classes appended after `icon icon-{name}`.
- `label` — presence flips decorative→meaningful (see Upgrade 2).
- `mode` — `"inline"` (default) | `"sprite"`.
- Replaces `lucide_icon_html` / `lucide_svg_html`; callers migrate in the same change (no shim,
  per ADR-0003). The HM twin and the Dazzle vendored copy stay byte-mirrored (drift-gated).

### Explicitly out of scope

- **Icon fonts** — not the default, not now. (A `mode="font"` compatibility adapter is a
  possible far-future migration aid only; not built here.)
- **Runtime SVG sanitisation allowlist** — solves a threat we don't have; our SVGs come from a
  pinned trusted package behind the regeneration gate. Not built.

## Problem 2 — pedagogically sound gallery demonstration

**Decision:** we accept that a sprite snippet is **not self-contained** — pasting it without the
sheet yields a blank icon. That is the same class of prerequisite as "include the CSS bundle,"
and it is the right trade for a *teaching* gallery where legibility beats isolated-paste. No
dual-view / expand toggle.

### Three layers of disclosure

**1. A Setup section, stated once.** Next to the existing "include `hatchi-maxchi.css`,"
document a second one-time include: the icon sheet. This establishes the prerequisite *model* —
HM snippets assume two includes (styles + icons), like any real app — so a `<use href="#name"/>`
in a snippet reads as a documented dependency, not a mystery.

**2. Component snippets show the quiet sprite form.** Every badge/menu/button/empty-state
snippet renders the icon as one clean line:

```html
<span class="badge" data-tone="success">
  <svg class="icon"><use href="#circle-check"/></svg>
  Approved
</span>
```

The lesson — badge structure, `data-tone`, hx- wiring — stays front and centre; the icon does
not dominate. The live demo above the code always renders because the page carries the sheet.
Copy copies exactly what is shown.

**3. A dedicated Icon Hyperpart page teaches the substrate in full** — inline-SVG anatomy, the
`.icon` contract and sizes, decorative-vs-`label` a11y, and explicit
inline-vs-sprite guidance (inline when you need isolation/self-containment; sprite when you have
repetition or want light pages). This is where the verbose truth lives, on purpose.

### The mechanic (one source, no drift)

Extend `gen_registry.py` to also emit a `<symbol>` sheet from the registry, and inline it
(hidden `<svg style="display:none">…symbols…</svg>`) into the gallery base layout `<head>`.
Every gallery page then resolves `<use href="#name">` same-document — works on Pages and in
local `file://` preview, no external fetch, no CORS.

One registry → (a) the inline-SVG renderer, (b) the symbol sheet, (c) the Dazzle vendored copy.
The sprite view, the inline view, and the live demo cannot disagree.

### Why this is pedagogically sound

- **Truthful** — the snippet you read is the snippet you copy; the live demo is that same
  markup, rendered.
- **Legible by default** — the sprite line keeps the canonical-htmx4 lesson in focus, which is
  the stated goal.
- **Honest about its one cost** — the sheet include is surfaced as an explicit setup step, and
  the Icon page shows the self-contained inline form for readers who want no sheet dependency.
- **Teaches the real architecture** — the two forms map exactly onto Dazzle's two production
  modes (inline default, sprite opt-in), not a docs-only fiction.

## Build / delivery notes

- HM CSS change (the `.icon` contract + per-component migration) runs through the package
  `build.py`; Dazzle consumes via the existing `@hm-build:dz-` seam (byte-identical namespace
  application). Rebuild dist after the CSS change.
- The `.icon` contract ships unprefixed in HM; Dazzle's ingest re-prefixes to `.dz-icon`
  (existing prefix-flip machinery — no per-file special-casing).
- Sheet generation is a new `gen_registry.py` output; the Dazzle-side sprite endpoint/asset is a
  follow-on (server inline is the default, so Dazzle can adopt sprite mode after HM lands).

## Non-goals

- No icon font (default or otherwise) in this work.
- No runtime SVG sanitiser.
- No client-side framework/hydration for icon rendering (the `data-lucide` span stays an
  explicit opt-in only).
- No change to the Lucide subset curation policy (registry still grows via `gen_registry.py`).

## Open questions / follow-ons

- Dazzle sprite-mode delivery: inline the sheet into the app shell vs. serve one cached
  `/static/icons.svg` (hosted, so external `<use>` is fine there). Decide when Dazzle adopts
  sprite mode.
- Whether the fail-loud dev behaviour should also cover the Dazzle DSL path (icon names
  referenced from DSL) or only framework-internal emission.
