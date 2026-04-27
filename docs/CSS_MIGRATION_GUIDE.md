# CSS Migration Guide for Downstream Agents

**Status:** in-flight in worktree `css-refactor-2026-04-27`. This document is the source of truth for what changed and how to update.

**Migration shape:** hard cutover — no shim layer. When this branch merges to main, every downstream project's CSS overrides need to be updated in lockstep. There is no transition window. This guide is the entirety of the deprecation notice.

## What changed in one paragraph

Dazzle's styling layer was rebuilt from scratch on modern CSS — cascade layers, custom properties, container queries, OKLCH colour. Tailwind, DaisyUI, and the standalone Tailwind CLI binary are gone. The framework now ships **one** stylesheet (`dazzle.css`) that imports six files in cascade-layer order: reset → tokens → base → utilities → components → overrides. There is no build step beyond optional minification. UK English throughout.

## Token vocabulary (rename map)

If your project overrides Dazzle's design tokens directly (e.g. in a custom theme file), every name changes. The mapping:

### Spacing

| Was (Tailwind utility) | Now (CSS token) |
|---|---|
| `p-1`, `m-1`, `gap-1` | `var(--space-xs)` (4px) |
| `p-2`, `m-2`, `gap-2` | `var(--space-sm)` (8px) |
| `p-3`, `m-3`, `gap-3` | `var(--space-md)` (12px) |
| `p-4`, `m-4`, `gap-4` | `var(--space-lg)` (16px) |
| `p-6`, `m-6`, `gap-6` | `var(--space-xl)` (24px) |
| `p-8`, `m-8`, `gap-8` | `var(--space-2xl)` (32px) |

### Typography

| Was | Now |
|---|---|
| `text-xs` | `var(--text-xs)` (fluid, ~12-14px) |
| `text-sm` | `var(--text-sm)` (fluid, ~14-16px) |
| `text-base` | `var(--text-base)` (fluid, ~16-18px) |
| `text-lg` | `var(--text-lg)` |
| `text-xl` | `var(--text-xl)` |
| `text-[13px]` (arbitrary) | use the nearest scale token; 13px doesn't exist any more |
| `font-medium` | `var(--weight-medium)` (500) |
| `font-semibold` | `var(--weight-semibold)` (600) |
| `font-bold` | `var(--weight-bold)` (700) |
| `leading-tight` | `var(--leading-tight)` (1.2) |
| `leading-normal` | `var(--leading-normal)` (1.5) |

### Colour (the breaking change to know)

The old `--primary`, `--success`, `--destructive` etc. (US English) are renamed:

| Was | Now |
|---|---|
| `--primary` | `--colour-brand` |
| `--primary-foreground` | (use `--colour-text` against `--colour-brand`) |
| `--background` | `--colour-bg` |
| `--foreground` | `--colour-text` |
| `--muted` | `--colour-bg` (background) or `--colour-text-muted` (text) — was overloaded |
| `--muted-foreground` | `--colour-text-muted` |
| `--border` | `--colour-border` |
| `--success` | `--colour-success` |
| `--warning` | `--colour-warning` |
| `--destructive` | `--colour-danger` (renamed for symmetry with semantic vocabulary) |
| `--card` | `--colour-surface` |
| `--accent` | `--colour-accent` |
| `--success` (alpha tints like `hsl(var(--success)/0.10)`) | `var(--colour-success-soft)` for the standard 10% wash; otherwise compose with `oklch(from var(--colour-success) 95% 0.05 h)` |

**Migration step for a project theme override:**

```css
/* Before */
[data-theme="aegismark"] {
  --primary: 220 90% 56%;
  --success: 142 76% 36%;
}

/* After */
[data-theme="aegismark"] {
  --colour-brand: oklch(55% 0.18 260);
  --colour-success: oklch(65% 0.15 142);
}
```

Use OKLCH for new colour values — it's perceptually uniform, themes look better, and you can derive soft variants via `oklch(from var(--colour-brand) 95% 0.05 h)`.

### Radii / shadows / motion

| Was | Now |
|---|---|
| `rounded-[4px]`, `rounded-sm` | `var(--radius-sm)` (4px) |
| `rounded-[6px]`, `rounded-md` | `var(--radius-md)` (6px) |
| `rounded-lg`, `rounded-xl` | `var(--radius-lg)` (12px) |
| `rounded-full` | `var(--radius-full)` |
| `shadow-sm` | `var(--shadow-sm)` |
| `shadow-md` | `var(--shadow-md)` |
| `transition-colors duration-[80ms]` | `transition: <prop> var(--duration-fast) var(--ease-out)` |

## Class vocabulary

### Utility classes (semantic, not utility-utility)

| Was (Tailwind soup) | Now (semantic class) |
|---|---|
| `flex flex-col gap-3` | `.stack` |
| `flex flex-col gap-2` | `.stack-sm` |
| `flex flex-col gap-4` | `.stack-lg` |
| `flex flex-row gap-3 items-center flex-wrap` | `.row` |
| `flex flex-wrap gap-2 items-baseline` | `.cluster` |
| `flex items-center justify-between` | `.between` |
| `grid place-items-center` | `.centre` (UK English) |
| `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3` | `.grid-auto` (auto-fills based on container width) |
| `space-y-3` (Tailwind) / `> * + * { margin-top: ... }` | `.flow` (set `--flow-space` to tune) |
| `sr-only` | `.visually-hidden` |

### Component classes

Every component now has a single semantic root class plus modifiers via `data-dz-*` attributes or chained classes. Examples:

```html
<!-- Was -->
<span class="inline-flex items-center rounded-[3px] font-medium px-2 h-5 text-[11px]
             bg-[hsl(var(--success)/0.12)] text-[hsl(var(--success))]">Done</span>

<!-- Now -->
<span class="dz-badge" data-dz-tone="success">Done</span>
```

Component CSS lives in `src/dazzle_ui/runtime/static/css/components/<family>.css`. One file per family.

## Container queries (responsive strategy)

We default to container queries on component roots:

```css
.dz-card {
  container-type: inline-size;
}

@container (width > 32rem) {
  .dz-card-body {
    grid-template-columns: 1fr 1fr;
  }
}
```

If you're writing project-side CSS that needs to respond to its parent container's width, use container queries too. Reach for `@media` only for genuinely page-level concerns (`prefers-color-scheme`, `prefers-reduced-motion`, top-level navigation switches).

**Foot guns:**
- `container-type: inline-size` triggers containment — the container becomes a containing block for absolute-positioned descendants.
- A container can't query its own width and adapt itself. Self-referential layouts need an outer container.
- Container queries don't fire in print stylesheets.

## HTMX classes

The runtime classes HTMX applies (`htmx-request`, `htmx-indicator`, `htmx-swapping`, `htmx-settling`) are now styled in `components/htmx-states.css`. Custom indicators in your project should target the same vocabulary; no migration needed for the class names themselves, but if you styled them via Tailwind utilities those utilities are gone.

## Vendored widget libraries

Audit completed 2026-04-27 in this worktree. All four widget libraries are KEPT — replacing them is out of scope for a CSS migration and they each solve genuine problems (combobox accessibility, date-picker localisation, rich text contenteditable plumbing, colour picker UX) that don't have lighter-weight alternatives in 2026.

| Library | Status | Used by | CSS surface |
|---|---|---|---|
| **Tom Select** (combobox) | KEEP | `macros/form_field.html`, `base.html` | `vendor/tom-select.css`, ~30KB minified |
| **Flatpickr** (date / datetime picker) | KEEP | `macros/form_field.html`, `base.html` | `vendor/flatpickr.css`, ~12KB minified |
| **Quill** (rich text editor) | KEEP | `macros/form_field.html` | `vendor/quill.snow.css`, ~22KB minified |
| **Pickr** (colour picker) | KEEP | `macros/form_field.html` | `vendor/pickr.css`, ~8KB minified |
| **HTMX** | KEEP | every dashboard region | runtime classes styled in `components/htmx-states.css` |
| **Alpine.js** | KEEP | dashboard builder, wizards, gates | no CSS surface |

Vendored CSS is loaded inside its own cascade layer (`@layer vendor`) so framework component CSS in the higher `components` layer can override per-instance styling without specificity wars. Project-side CSS in the `overrides` layer (highest priority) can override vendor styles outright if needed.

The vendor layer is appended to the cascade order in `dazzle.css`:

```css
@layer reset, vendor, tokens, base, utilities, components, overrides;
```

(`vendor` is between `reset` and `tokens` so vendor stylesheets get the basic reset but can't override our design tokens or component CSS.)

## Migration checklist for a downstream project

1. **Update theme override files** — every `--primary` → `--colour-brand`, etc. See the rename map above.
2. **Update any CSS that uses Dazzle's old slot names directly** — same rename map applies.
3. **Remove any Tailwind config that scanned Dazzle's templates** — Dazzle no longer ships utility classes for you to pick up.
4. **Audit your own project for arbitrary Tailwind classes referencing Dazzle slots** — `bg-[hsl(var(--primary))]` becomes `background: var(--colour-brand)` in component CSS.
5. **Re-test the visual layer** — automated screenshot diffs are recommended.
6. **Confirm dark mode + theme switching still work** — should "just work" if step 1 is done correctly.

## What you DON'T need to do

- Reinstall anything. There's no `npm install` step that changed.
- Refactor your own component HTML/templates that use generic Dazzle macros (e.g. `render_status_badge`). The macros are unchanged at the call site — only their internals changed.
- Worry about `dist/dazzle.min.css`. The framework still ships a single bundled CSS file; the file's contents differ but the URL is the same.

## Where to find help

- This guide.
- `dev_docs/css-refactor-2026-04-27.md` (root project plan, in the AegisMark repo for historical reasons).
- The cascade-layer order in `src/dazzle_ui/runtime/static/css/dazzle.css`.
- `tokens.css` — the design system. Read it first before debugging any colour or spacing question.
