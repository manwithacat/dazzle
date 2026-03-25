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

Declared in both `base.html` and `site_base.html`:

```css
@layer base, framework, app, overrides;
```

| Layer | Content | Source |
|-------|---------|--------|
| `base` | Tailwind utilities + DaisyUI components | `dazzle-bundle.css` (Tailwind v4 emits `@layer` internally) |
| `framework` | Dazzle semantic CSS (5 files) | `dazzle-framework.css` entry point |
| `app` | Project-level CSS (e.g. `custom.css`) | Loaded via `<link>` after framework CSS |
| `overrides` | Design tokens (CSS custom properties) | Inline `<style>` block in template |

Design tokens use CSS custom properties which don't participate in cascade specificity, so the `overrides` layer is declared for completeness but tokens remain in an unlayered inline `<style>` block.

### New File: `dazzle-framework.css`

Location: `src/dazzle_ui/runtime/static/css/dazzle-framework.css`

```css
/* Dazzle framework semantic layer — load order is authoritative.
   This is the single source of truth for framework CSS ordering.
   build_dist.py and css_loader.py must use the same order. */
@import "dazzle-layer.css" layer(framework);
@import "design-system.css" layer(framework);
@import "dz.css" layer(framework);
@import "site-sections.css" layer(framework);
```

`feedback-widget.css` is excluded — it's conditionally loaded at `<body>` bottom when enabled in DSL. It gets a `@layer framework { ... }` wrapper in its own file.

**Note on `@import` round trips:** In local mode, the browser makes 4 additional HTTP requests (one per `@import`). This is acceptable for development. For production CDN users, the concatenated `dazzle.min.css` avoids this. A future optimisation could inline the imports at serve-time, but this is not needed now — the files total 72KB and are served from localhost with 1-hour cache headers.

### Canonical CSS Order

Three code paths serve the same CSS files. All must use this order:

1. `dazzle-layer.css` — semantic aliases
2. `design-system.css` — design system tokens + component overrides
3. `dz.css` — runtime utilities
4. `site-sections.css` — site section components

| Delivery path | Source of truth |
|---------------|-----------------|
| Local app pages | `dazzle-framework.css` (`@import` order) |
| Local site pages | `css_loader.py` (`CSS_SOURCE_FILES` order) |
| CDN | `build_dist.py` (`CSS_SOURCES` order) |

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
- `_use_cdn` default flips from `true` to `false` in all Jinja `default()` filters
- Local path loads `dazzle-framework.css` (replaces standalone `dz.css`)
- CDN path preserved for opt-in users
- Lucide icons block (lines 60-65) also uses `_use_cdn | default(false)` — this means local icons load by default, which is the correct local-first behaviour

**Scope expansion note:** Previously in local mode, `base.html` only loaded `dz.css`. Now it loads all 4 framework CSS files via `dazzle-framework.css`. This is intentional — local app pages were missing `dazzle-layer.css`, `design-system.css`, and `site-sections.css` which were only available via CDN.

### Template Changes: `site_base.html`

`src/dazzle_ui/templates/site/site_base.html` gets the same treatment:

```html
{# Layer order declaration #}
<style>@layer base, framework, app, overrides;</style>

{# ... Tailwind section unchanged ... #}

{# Dazzle framework CSS (framework layer) #}
{% if _use_cdn | default(false) %}
<link rel="stylesheet" href="{{ _cdn_base }}/dazzle.min.css">
{% else %}
<link rel="stylesheet" href="/styles/dazzle.css">
{% endif %}
```

Key changes:
- Layer declaration added
- `_use_cdn | default(true)` → `_use_cdn | default(false)` in both CSS and icons blocks
- Local path continues to use `/styles/dazzle.css` (served by `css_loader.py`) since site pages support theme CSS prepending. `css_loader.py` is updated to include `dz.css` for consistency with the canonical order (the runtime selectors are inert on pages that don't use `data-dz-*` attributes)

### Backend Changes

**`template_renderer.py`** — line 287:

```python
env.globals["_use_cdn"] = False  # local-first; opt-in via [ui] cdn = true
```

**`manifest.py`** — `ProjectManifest.cdn` default flips to match:

```python
cdn: bool = False  # Local-first; opt-in via [ui] cdn = true in dazzle.toml
```

And the parser default in `manifest.py` line 540:

```python
cdn_enabled = ui_data.get("cdn", False)
```

**`combined_server.py`** — line 278 already sets `_use_cdn = False` for `--local-assets`. This becomes a no-op for CDN toggling but remains useful as documentation of intent. No change needed.

### `css_loader.py` Changes

Update `CSS_SOURCE_FILES` to match the canonical order and add `dz.css`:

```python
CSS_SOURCE_FILES = [
    "dazzle-layer.css",
    "design-system.css",
    "dz.css",
    "site-sections.css",
]
```

Wrap each file's content in `@layer framework { ... }` during concatenation in `get_bundled_css()`:

```python
for filename in CSS_SOURCE_FILES:
    parts.append(f"/* --- {filename} --- */")
    parts.append(f"@layer framework {{")
    parts.append(_load_css_file(filename))
    parts.append(f"}}")
    parts.append("")
```

Prepend the layer order declaration:

```python
parts.insert(0, "@layer base, framework, app, overrides;")
```

### Build Change: `build_dist.py`

CSS source list reordered to canonical order. All framework files share the same layer, so the list stays flat and the loop wraps each file in `@layer framework { }`:

```python
CSS_SOURCES = [
    STATIC / "css" / "dazzle-layer.css",
    STATIC / "css" / "design-system.css",
    STATIC / "css" / "dz.css",
    STATIC / "css" / "site-sections.css",
    STATIC / "css" / "feedback-widget.css",
]

# In build():
for src in CSS_SOURCES:
    content = src.read_text()
    css_parts.append(f"@layer framework {{\n{content}\n}}")
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

### CI Change: Release-Time Dist Build

Add `python scripts/build_dist.py` step to `publish-pypi.yml`. The workflow must:

1. Checkout the tagged commit
2. Run `python scripts/build_dist.py`
3. Commit rebuilt `dist/` and push to the tag branch

**Permission change required:** `publish-pypi.yml` currently has `permissions: contents: read`. The dist rebuild job needs `contents: write` to push the rebuilt dist files. Add a separate job with write permissions that runs before the publish job.

Since jsDelivr resolves tags to commits, the dist files on the tagged commit must be up to date.

The weekly `update-vendors.yml` keeps its dist rebuild step (vendor JS updates change the bundle).

### Feedback Widget Layer Wrapper

`feedback-widget.css` gets a `@layer framework { ... }` wrapper around its entire content, since it's loaded conditionally and outside the `dazzle-framework.css` import chain.

## Files Changed

| File | Change |
|------|--------|
| `src/dazzle_ui/runtime/static/css/dazzle-framework.css` | **New** — entry point with `@import` + layer assignments |
| `src/dazzle_ui/runtime/static/css/feedback-widget.css` | Wrap content in `@layer framework { }` |
| `src/dazzle_ui/templates/base.html` | Layer declaration, simplified CSS loading, `_use_cdn` default flip |
| `src/dazzle_ui/templates/site/site_base.html` | Layer declaration, `_use_cdn` default flip |
| `src/dazzle_ui/runtime/template_renderer.py` | `_use_cdn` default → `False` |
| `src/dazzle_ui/runtime/css_loader.py` | Canonical file order, add `dz.css`, `@layer` wrappers |
| `src/dazzle/core/manifest.py` | `cdn` default → `False` (both dataclass and parser) |
| `scripts/build_dist.py` | Layer-aware concatenation with `@layer` wrappers, canonical order |
| `.github/workflows/publish-pypi.yml` | Add dist build step before publish |
| `src/dazzle_ui/build_css.py` | Add `--sourcemap` flag to Tailwind CLI invocation |
| `tests/unit/test_template_rendering.py` | Update `test_use_cdn_global` assertion to `False` |

## Testing

### Automated
- Update `test_use_cdn_global` to assert `_use_cdn is False`
- Add test: `dazzle-framework.css` exists in static directory
- Add test: `build_dist.py` output contains `@layer` declarations
- Add test: `css_loader.py` output contains `@layer framework` wrappers
- Add test: template renders local CSS path (`dazzle-framework.css`) by default

### Manual
- `dazzle serve` — verify all CSS loads locally, no CDN requests in network tab
- Set `[ui] cdn = true` in `dazzle.toml` — verify CDN path still works
- Inspect computed styles — confirm framework CSS overrides Tailwind defaults
- Check `feedback-widget.css` loads in correct layer when enabled
- Run `python scripts/build_dist.py` — verify `dazzle.min.css` contains layer wrappers
- Test site pages (`site_base.html`) — verify `/styles/dazzle.css` includes layer wrappers

## Browser Support

CSS `@layer` is supported in all browsers Dazzle targets (Chrome 99+, Firefox 97+, Safari 15.4+, Edge 99+). `@import ... layer()` has the same support matrix.

## Source Maps in Local Mode

When serving assets locally (the new default), source maps improve the developer experience by mapping compiled/concatenated CSS back to source files in browser DevTools.

### What gets source maps

| Asset | Source map strategy |
|-------|-------------------|
| `dazzle-framework.css` | Not needed — `@import` preserves individual files; DevTools already shows `dazzle-layer.css`, `design-system.css`, etc. natively |
| `dazzle-bundle.css` (Tailwind) | Pass `--sourcemap` to Tailwind CLI in `build_css.py`. Outputs `dazzle-bundle.css.map` alongside the bundle |
| `/styles/dazzle.css` (css_loader) | Generate an inline source map during concatenation in `get_bundled_css()`, mapping byte offsets back to source filenames |
| `dist/dazzle.min.css` (CDN) | No source maps — CDN users get minified bundles; DevTools debugging is a local-mode benefit |
| `feedback-widget.css` | Not needed — served as a single unmodified file |

### Tailwind source map: `build_css.py`

Add `--sourcemap` flag to the Tailwind CLI invocation. The static file server already serves `*.map` files from the same directory.

**Verification required at implementation time:** The project uses `tailwind-cli-extra` v2.8.1 (a Tailwind v4 standalone CLI fork). The `--sourcemap` flag may not be supported. At implementation time, test with `tailwind-cli-extra --help` or a trial run. If unsupported, skip this source map and note it as blocked on upstream CLI support.

```python
cmd = [cli_path, "--input", input_css, "--output", output_css, "--content", ..., "--minify", "--sourcemap"]
```

The `.map` file is only generated during `dazzle serve` (local build). It is not included in pip packages or dist builds.

### css_loader source map

`get_bundled_css()` generates a `sourceMappingURL` comment appending an inline source map (base64-encoded v3 JSON). The map records which byte ranges in the concatenated output correspond to which source file. This is lightweight — the mapping is file-level, not line-level, since the source files are included verbatim.

```python
# At end of get_bundled_css():
import json, base64
mappings = {"version": 3, "sources": CSS_SOURCE_FILES, "mappings": ""}
map_b64 = base64.b64encode(json.dumps(mappings).encode()).decode()
parts.append(f"/*# sourceMappingURL=data:application/json;base64,{map_b64} */")
```

### Files affected

| File | Source map change |
|------|-----------------|
| `src/dazzle_ui/build_css.py` | Add `--sourcemap` to Tailwind CLI args |
| `src/dazzle_ui/runtime/css_loader.py` | Generate inline source map in `get_bundled_css()` |
| `MANIFEST.in` | Add `global-exclude *.map` (currently excluded by omission; make explicit) |
