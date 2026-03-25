# CSS Delivery Architecture: Local-First + Cascade Layers

**Issue:** #671 — CDN tag lag causes stale styles on deployed sites
**Date:** 2026-03-25
**Status:** Approved

## Problem

CSS fixes committed after a version tag are never delivered to deployed sites until the next tag + dist rebuild. The CDN URL (`cdn.jsdelivr.net/gh/manwithacat/dazzle@vX.Y.Z/dist/dazzle.min.css`) is pinned to the git tag, but pip-installed code runs ahead of it. This creates a "fix is deployed but doesn't work" confusion.

Secondary concern: no explicit cascade ordering between Tailwind/DaisyUI (base), Dazzle semantic CSS (framework), and project CSS (app). Specificity conflicts are possible and ordering is implicit.

## Decision

**Approach B: Pipeline-Aware — Single Entry Point CSS with Cascade Layers.**

- Default to local asset delivery (`_use_cdn = False`)
- Keep CDN as opt-in via `[ui] cdn = true` in `dazzle.toml`
- Introduce CSS Cascade Layers (`@layer`) for explicit ordering
- Create a `dazzle-framework.css` entry point that manages framework CSS load order
- Rebuild `dist/` at release-tag time so CDN users also get correct assets

## Design

### Layer Order

Declared once in `base.html`:

```css
@layer base, framework, app, overrides;
```

| Layer | Content | Source |
|-------|---------|--------|
| `base` | Tailwind utilities + DaisyUI components | `dazzle-bundle.css` (Tailwind v4 emits `@layer` internally) |
| `framework` | Dazzle semantic CSS (5 files) | `dazzle-framework.css` entry point |
| `app` | Project-level CSS | Loaded via `<link>` after framework CSS |
| `overrides` | Design tokens (CSS custom properties) | Inline `<style>` block in template |

Design tokens use CSS custom properties which don't participate in cascade specificity, so the `overrides` layer is declared for completeness but tokens remain in an unlayered inline `<style>` block.

### New File: `dazzle-framework.css`

Location: `src/dazzle_ui/runtime/static/css/dazzle-framework.css`

```css
/* Dazzle framework semantic layer — load order is authoritative */
@import "dazzle-layer.css" layer(framework);
@import "design-system.css" layer(framework);
@import "dz.css" layer(framework);
@import "site-sections.css" layer(framework);
```

`feedback-widget.css` is excluded — it's conditionally loaded at `<body>` bottom when enabled in DSL. It gets a `@layer framework { ... }` wrapper in its own file.

### Template Changes: `base.html`

CSS section of `<head>` becomes:

```html
{# Layer order declaration — defines cascade priority #}
<style>@layer base, framework, app, overrides;</style>

{# Tailwind + DaisyUI (base layer) #}
{% if _tailwind_bundled | default(false) %}
<link rel="stylesheet" href="/static/css/dazzle-bundle.css">
{% else %}
<link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.14/dist/full.min.css" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
{% endif %}

{# Dazzle framework CSS (framework layer) #}
{% if _use_cdn | default(false) %}
<link rel="stylesheet" href="{{ _cdn_base }}/dazzle.min.css">
{% else %}
<link rel="stylesheet" href="/static/css/dazzle-framework.css">
{% endif %}
```

Key changes:
- `_use_cdn` default flips from `true` to `false`
- Local path loads `dazzle-framework.css` (replaces standalone `dz.css`)
- CDN path preserved for opt-in users
- JS section unchanged (already has both CDN and local paths)

### Backend Change: `template_renderer.py`

Line 287:

```python
env.globals["_use_cdn"] = False  # local-first; opt-in via [ui] cdn = true
```

### Build Change: `build_dist.py`

CSS concatenation becomes layer-aware:

```python
CSS_SOURCES = [
    (STATIC / "css" / "dazzle-layer.css", "framework"),
    (STATIC / "css" / "design-system.css", "framework"),
    (STATIC / "css" / "dz.css", "framework"),
    (STATIC / "css" / "site-sections.css", "framework"),
    (STATIC / "css" / "feedback-widget.css", "framework"),
]
```

Output in `dazzle.min.css`:

```css
/* dazzle vX.Y.Z | MIT License | ... */
@layer base, framework, app, overrides;
@layer framework { /* dazzle-layer.css */ }
@layer framework { /* design-system.css */ }
@layer framework { /* dz.css */ }
@layer framework { /* site-sections.css */ }
@layer framework { /* feedback-widget.css */ }
```

CDN users get layer ordering too.

### CI Change: Release-Time Dist Build

Add `python scripts/build_dist.py` step to the tag/release workflow so `dist/` is rebuilt when a version is tagged. jsDelivr always serves assets matching the tag.

The weekly `update-vendors.yml` keeps its dist rebuild step (vendor JS updates change the bundle).

### Feedback Widget Layer Wrapper

`feedback-widget.css` gets a `@layer framework { ... }` wrapper around its entire content, since it's loaded conditionally and outside the `dazzle-framework.css` import chain.

## Files Changed

| File | Change |
|------|--------|
| `src/dazzle_ui/runtime/static/css/dazzle-framework.css` | **New** — entry point with `@import` + layer assignments |
| `src/dazzle_ui/runtime/static/css/feedback-widget.css` | Wrap content in `@layer framework { }` |
| `src/dazzle_ui/templates/base.html` | Layer declaration, simplified CSS loading, `_use_cdn` default flip |
| `src/dazzle_ui/runtime/template_renderer.py` | `_use_cdn` default → `False` |
| `scripts/build_dist.py` | Layer-aware concatenation with `@layer` wrappers |
| `.github/workflows/` | Add dist build step to release/tag workflow |

## Testing

- `dazzle serve --local` — verify all CSS loads locally, no CDN requests in network tab
- `dazzle serve` (default) — same result (default is now local)
- Set `[ui] cdn = true` in `dazzle.toml` — verify CDN path still works
- Inspect computed styles — confirm framework CSS overrides Tailwind defaults
- Check `feedback-widget.css` loads in correct layer when enabled
- Run `python scripts/build_dist.py` — verify `dazzle.min.css` contains layer wrappers

## Browser Support

CSS `@layer` is supported in all browsers Dazzle targets (Chrome 99+, Firefox 97+, Safari 15.4+, Edge 99+). `@import ... layer()` has the same support matrix.
