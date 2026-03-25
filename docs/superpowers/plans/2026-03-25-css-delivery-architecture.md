# CSS Delivery Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch CSS delivery to local-first with explicit cascade layer ordering, keeping CDN as opt-in.

**Architecture:** Flip `_use_cdn` default to `False` across templates + backend + manifest. Create `dazzle-framework.css` entry point with `@import ... layer()` for app pages. Update `css_loader.py` with `@layer` wrappers for site pages. Update `build_dist.py` for layer-aware CDN bundles. Add source maps for local mode.

**Tech Stack:** CSS Cascade Layers (`@layer`), Jinja2 templates, Python (FastAPI static serving), Tailwind CLI

**Spec:** `docs/superpowers/specs/2026-03-25-css-delivery-architecture-design.md`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/dazzle_ui/runtime/static/css/dazzle-framework.css` | Create | Entry point with `@import ... layer()` |
| `src/dazzle_ui/runtime/static/css/feedback-widget.css` | Modify | Wrap in `@layer framework {}` |
| `src/dazzle_ui/templates/base.html` | Modify | Layer declaration, local-first CSS, default flip |
| `src/dazzle_ui/templates/site/site_base.html` | Modify | Layer declaration, default flip |
| `src/dazzle_ui/runtime/template_renderer.py` | Modify | `_use_cdn = False` |
| `src/dazzle/core/manifest.py` | Modify | `cdn` default → `False` |
| `src/dazzle_ui/runtime/css_loader.py` | Modify | Canonical order, `dz.css`, `@layer` wrappers, source map |
| `scripts/build_dist.py` | Modify | Canonical order, `@layer` wrappers |
| `src/dazzle_ui/build_css.py` | Modify | `--sourcemap` flag (if supported) |
| `MANIFEST.in` | Modify | Add `global-exclude *.map` |
| `.github/workflows/publish-pypi.yml` | Modify | Add dist rebuild job |
| `tests/unit/test_template_rendering.py` | Modify | Fix `_use_cdn` assertion |
| `tests/unit/test_css_delivery.py` | Create | New tests for layer ordering + source maps |

---

### Task 1: Create `dazzle-framework.css` Entry Point

**Files:**
- Create: `src/dazzle_ui/runtime/static/css/dazzle-framework.css`
- Test: `tests/unit/test_css_delivery.py`

- [ ] **Step 1: Write the test for the new file**

Create `tests/unit/test_css_delivery.py`:

```python
"""Tests for CSS delivery architecture — cascade layers and local-first delivery."""

from __future__ import annotations

from pathlib import Path

STATIC_CSS = Path(__file__).resolve().parent.parent.parent / "src" / "dazzle_ui" / "runtime" / "static" / "css"

# Canonical order — must match dazzle-framework.css, css_loader.py, build_dist.py
CANONICAL_ORDER = ["dazzle-layer.css", "design-system.css", "dz.css", "site-sections.css"]


class TestFrameworkCssEntryPoint:
    def test_file_exists(self) -> None:
        assert (STATIC_CSS / "dazzle-framework.css").exists()

    def test_imports_in_canonical_order(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        positions = []
        for filename in CANONICAL_ORDER:
            pos = content.find(filename)
            assert pos != -1, f"{filename} not found in dazzle-framework.css"
            positions.append(pos)
        assert positions == sorted(positions), f"Import order does not match canonical: {CANONICAL_ORDER}"

    def test_all_imports_use_layer_framework(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        for filename in CANONICAL_ORDER:
            assert f'@import "{filename}" layer(framework)' in content

    def test_no_feedback_widget_import(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        assert "feedback-widget" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_css_delivery.py::TestFrameworkCssEntryPoint -v`
Expected: FAIL — file does not exist

- [ ] **Step 3: Create the entry point file**

Create `src/dazzle_ui/runtime/static/css/dazzle-framework.css`:

```css
/* Dazzle framework semantic layer — load order is authoritative.
   This is the single source of truth for framework CSS ordering.
   build_dist.py and css_loader.py must use the same order. */
@import "dazzle-layer.css" layer(framework);
@import "design-system.css" layer(framework);
@import "dz.css" layer(framework);
@import "site-sections.css" layer(framework);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_css_delivery.py::TestFrameworkCssEntryPoint -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_ui/runtime/static/css/dazzle-framework.css tests/unit/test_css_delivery.py
git commit -m "feat(css): create dazzle-framework.css entry point with cascade layers (#671)"
```

---

### Task 2: Wrap `feedback-widget.css` in `@layer framework`

**Files:**
- Modify: `src/dazzle_ui/runtime/static/css/feedback-widget.css`
- Test: `tests/unit/test_css_delivery.py`

- [ ] **Step 1: Write the test**

Append to `tests/unit/test_css_delivery.py`:

```python
class TestFeedbackWidgetLayer:
    def test_wrapped_in_layer_framework(self) -> None:
        content = (STATIC_CSS / "feedback-widget.css").read_text()
        assert "@layer framework {" in content

    def test_still_contains_feedback_btn_class(self) -> None:
        content = (STATIC_CSS / "feedback-widget.css").read_text()
        assert ".dz-feedback-btn" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_css_delivery.py::TestFeedbackWidgetLayer -v`
Expected: FAIL — no `@layer framework {` in file

- [ ] **Step 3: Wrap the file content**

In `src/dazzle_ui/runtime/static/css/feedback-widget.css`, wrap the entire content:

```css
@layer framework {
/* Feedback Widget — framework-level in-app feedback collection.
 * Uses DaisyUI oklch colour tokens for theme consistency. */

/* ... existing content unchanged ... */

} /* end @layer framework */
```

The wrapper goes around everything after the opening comment. Read the file first to get exact content.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_css_delivery.py::TestFeedbackWidgetLayer -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_ui/runtime/static/css/feedback-widget.css tests/unit/test_css_delivery.py
git commit -m "feat(css): wrap feedback-widget.css in @layer framework (#671)"
```

---

### Task 3: Flip `_use_cdn` Default in Backend

**Files:**
- Modify: `src/dazzle_ui/runtime/template_renderer.py:287`
- Modify: `src/dazzle/core/manifest.py:341,540`
- Modify: `tests/unit/test_template_rendering.py:807-809`
- Test: `tests/unit/test_css_delivery.py`

- [ ] **Step 1: Write the test**

Append to `tests/unit/test_css_delivery.py`:

```python
class TestCdnDefault:
    def test_manifest_cdn_default_is_false(self) -> None:
        from dazzle.core.manifest import ProjectManifest
        m = ProjectManifest()
        assert m.cdn is False

    def test_manifest_parser_cdn_default_is_false(self) -> None:
        from dazzle.core.manifest import parse_manifest
        m = parse_manifest({})  # empty TOML
        assert m.cdn is False

    def test_manifest_explicit_cdn_true_preserved(self) -> None:
        from dazzle.core.manifest import parse_manifest
        m = parse_manifest({"ui": {"cdn": True}})
        assert m.cdn is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_css_delivery.py::TestCdnDefault -v`
Expected: FAIL — `m.cdn` is `True`

- [ ] **Step 3: Update `manifest.py` dataclass default**

In `src/dazzle/core/manifest.py:341`, change:

```python
cdn: bool = True  # Serve assets from jsDelivr CDN; set [ui] cdn = false for air-gapped
```

to:

```python
cdn: bool = False  # Local-first; opt-in via [ui] cdn = true in dazzle.toml
```

- [ ] **Step 4: Update `manifest.py` parser default**

In `src/dazzle/core/manifest.py:540`, change:

```python
cdn_enabled = ui_data.get("cdn", True)
```

to:

```python
cdn_enabled = ui_data.get("cdn", False)
```

- [ ] **Step 5: Update `template_renderer.py` default**

In `src/dazzle_ui/runtime/template_renderer.py:287`, change:

```python
env.globals["_use_cdn"] = True  # default; overridden from [ui] cdn in dazzle.toml
```

to:

```python
env.globals["_use_cdn"] = False  # local-first; opt-in via [ui] cdn = true
```

- [ ] **Step 6: Fix existing test**

In `tests/unit/test_template_rendering.py:809`, change:

```python
assert env.globals["_use_cdn"] is True
```

to:

```python
assert env.globals["_use_cdn"] is False
```

- [ ] **Step 7: Run all affected tests**

Run: `pytest tests/unit/test_css_delivery.py::TestCdnDefault tests/unit/test_template_rendering.py::TestEnvironmentSetup::test_use_cdn_global -v`
Expected: PASS (4 tests)

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/core/manifest.py src/dazzle_ui/runtime/template_renderer.py tests/unit/test_template_rendering.py tests/unit/test_css_delivery.py
git commit -m "feat(css): flip _use_cdn default to False — local-first delivery (#671)"
```

---

### Task 4: Update `base.html` Template

**Files:**
- Modify: `src/dazzle_ui/templates/base.html`

- [ ] **Step 1: Add layer declaration and update CSS section**

In `src/dazzle_ui/templates/base.html`, replace lines 14-47 (the CSS + JS loading section between the Inter font link and the CSRF block) with:

```html
  {# CSS Cascade Layer order — defines priority: base < framework < app < overrides #}
  <style>@layer base, framework, app, overrides;</style>

  {# Tailwind CSS + DaisyUI — compiled bundle replaces both CDNs (#377) #}
  {% if _tailwind_bundled | default(false) %}
  <link rel="stylesheet" href="/static/css/dazzle-bundle.css">
  {% else %}
  <link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.14/dist/full.min.css" rel="stylesheet" type="text/css" />
  <script src="https://cdn.tailwindcss.com"></script>
  {% endif %}

  {% set _cdn_base = "https://cdn.jsdelivr.net/gh/manwithacat/dazzle@v" ~ _dazzle_version ~ "/dist" %}
  {% if _use_cdn | default(false) %}
  {# Dazzle framework CSS + JS — jsDelivr CDN (opt-in) #}
  <link rel="stylesheet" href="{{ _cdn_base }}/dazzle.min.css">
  <script defer src="{{ _cdn_base }}/dazzle.min.js"></script>
  {% else %}
  {# Dazzle framework CSS (local — framework layer via @import) #}
  <link rel="stylesheet" href="/static/css/dazzle-framework.css">
  {# HTMX + extensions (vendored) #}
  <script src="/static/vendor/htmx.min.js"></script>
  <script src="/static/vendor/htmx-ext-json-enc.js"></script>
  <script src="/static/vendor/idiomorph-ext.min.js"></script>
  <script src="/static/vendor/htmx-ext-preload.js"></script>
  <script src="/static/vendor/htmx-ext-response-targets.js"></script>
  <script src="/static/vendor/htmx-ext-loading-states.js"></script>
  <script src="/static/vendor/htmx-ext-sse.js"></script>
  {# Alpine.js + plugins #}
  <script defer src="/static/vendor/sortable.min.js"></script>
  <script defer src="/static/vendor/alpine-sort.min.js"></script>
  <script defer src="/static/vendor/alpine-persist.min.js"></script>
  <script defer src="/static/js/dz-alpine.js"></script>
  <script defer src="/static/js/workspace-editor.js"></script>
  <script defer src="/static/vendor/alpine.min.js"></script>
  {# Dazzle runtime (a11y + islands only — UI state managed by Alpine) #}
  <script defer src="/static/js/dz-a11y.js"></script>
  <script defer src="/static/js/dz-islands.js"></script>
  {% endif %}
```

Key differences from current:
- Added `<style>@layer ...</style>` before everything
- `_use_cdn | default(false)` (was `default(true)`)
- Local path loads `dazzle-framework.css` instead of just `dz.css`
- Removed standalone `<link rel="stylesheet" href="/static/css/dz.css">` (now in framework entry point)

- [ ] **Step 2: Update Lucide icons block**

In the same file, update the icons section (currently lines 59-65) — change `_use_cdn | default(true)` to `_use_cdn | default(false)`:

```html
  {# Lucide icons (v0.38.0: nav group icons) #}
  {% if not _use_cdn | default(false) %}
  <script defer src="/static/vendor/lucide.min.js"></script>
  {% else %}
  <script defer src="{{ _cdn_base }}/dazzle-icons.min.js"
          onerror="this.onerror=null;this.src='/static/vendor/lucide.min.js'"></script>
  {% endif %}
```

- [ ] **Step 3: Verify template renders**

Run: `pytest tests/unit/test_template_rendering.py -v -x`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/templates/base.html
git commit -m "feat(css): update base.html with cascade layers + local-first delivery (#671)"
```

---

### Task 5: Update `site_base.html` Template

**Files:**
- Modify: `src/dazzle_ui/templates/site/site_base.html`

- [ ] **Step 1: Add layer declaration**

After line 11 (the Inter font `<link>`), add:

```html
  {# CSS Cascade Layer order #}
  <style>@layer base, framework, app, overrides;</style>
```

- [ ] **Step 2: Flip `_use_cdn` defaults**

Change both instances of `_use_cdn | default(true)` (lines 21 and 31) to `_use_cdn | default(false)`.

Line 21:
```html
  {% if _use_cdn | default(false) %}
```

Line 31:
```html
  {% if _use_cdn | default(false) %}
```

- [ ] **Step 3: Commit**

```bash
git add src/dazzle_ui/templates/site/site_base.html
git commit -m "feat(css): update site_base.html with cascade layers + local-first (#671)"
```

---

### Task 6: Update `css_loader.py` — Canonical Order + Layer Wrappers + Source Map

**Files:**
- Modify: `src/dazzle_ui/runtime/css_loader.py`
- Test: `tests/unit/test_css_delivery.py`

- [ ] **Step 1: Write the tests**

Append to `tests/unit/test_css_delivery.py`:

```python
class TestCssLoader:
    def test_canonical_order(self) -> None:
        from dazzle_ui.runtime.css_loader import CSS_SOURCE_FILES
        assert CSS_SOURCE_FILES == CANONICAL_ORDER

    def test_output_contains_layer_declaration(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css
        css = get_bundled_css()
        assert "@layer base, framework, app, overrides;" in css

    def test_output_wraps_files_in_layer_framework(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css
        css = get_bundled_css()
        assert css.count("@layer framework {") == len(CANONICAL_ORDER)

    def test_output_contains_source_map(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css
        css = get_bundled_css()
        assert "sourceMappingURL=data:application/json;base64," in css

    def test_source_map_lists_all_sources(self) -> None:
        import base64
        import json
        from dazzle_ui.runtime.css_loader import get_bundled_css
        css = get_bundled_css()
        # Extract base64 source map from the comment
        marker = "sourceMappingURL=data:application/json;base64,"
        start = css.index(marker) + len(marker)
        end = css.index(" */", start)
        b64 = css[start:end]
        source_map = json.loads(base64.b64decode(b64))
        assert source_map["version"] == 3
        for f in CANONICAL_ORDER:
            assert f in source_map["sources"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_css_delivery.py::TestCssLoader -v`
Expected: FAIL — `CSS_SOURCE_FILES` is different, no `@layer` wrappers

- [ ] **Step 3: Update `css_loader.py`**

Replace the entire content of `src/dazzle_ui/runtime/css_loader.py`:

```python
"""
CSS loader for Dazzle UI runtime.

Loads and concatenates CSS files from static/css/ to produce
the bundled stylesheet served at /styles/dazzle.css.

Uses CSS Cascade Layers (@layer) for explicit ordering.
Generates an inline source map for DevTools debugging.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

_STATIC_CSS_DIR = Path(__file__).parent / "static" / "css"

# Canonical CSS source order — must match dazzle-framework.css and build_dist.py.
CSS_SOURCE_FILES = [
    "dazzle-layer.css",
    "design-system.css",
    "dz.css",
    "site-sections.css",
]


def _load_css_file(filename: str) -> str:
    """Load a CSS file from the static/css directory."""
    path = _STATIC_CSS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"CSS file not found: {path}")
    return path.read_text(encoding="utf-8")


def get_bundled_css(theme_css: str | None = None) -> str:
    """
    Load and concatenate CSS files with @layer framework wrappers.

    Returns the DAZZLE semantic layer wrapped in cascade layer blocks.
    Tailwind + DaisyUI are built separately by build_css().

    Args:
        theme_css: Optional generated theme CSS to prepend (from ThemeSpec)

    Returns:
        Concatenated CSS content with @layer wrappers and inline source map
    """
    parts: list[str] = [
        "@layer base, framework, app, overrides;",
        "",
        "/* =============================================================================",
        "   DAZZLE Semantic Layer",
        "   Thin aliases on top of DaisyUI (loaded via CDN) + Tailwind",
        "   DO NOT EDIT - regenerate using dazzle init or dazzle serve",
        "   ============================================================================= */",
        "",
    ]

    # Prepend generated theme CSS if provided
    if theme_css:
        parts.append("/* --- theme.css (generated) --- */")
        parts.append(f"@layer framework {{\n{theme_css}\n}}")
        parts.append("")

    for filename in CSS_SOURCE_FILES:
        parts.append(f"/* --- {filename} --- */")
        parts.append(f"@layer framework {{\n{_load_css_file(filename)}\n}}")
        parts.append("")

    # Inline source map (file-level, not line-level)
    source_map = {"version": 3, "sources": list(CSS_SOURCE_FILES), "mappings": ""}
    map_b64 = base64.b64encode(json.dumps(source_map).encode()).decode()
    parts.append(f"/*# sourceMappingURL=data:application/json;base64,{map_b64} */")

    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_css_delivery.py::TestCssLoader -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_ui/runtime/css_loader.py tests/unit/test_css_delivery.py
git commit -m "feat(css): update css_loader with canonical order, @layer wrappers, source map (#671)"
```

---

### Task 7: Update `build_dist.py` — Layer-Aware Concatenation

**Files:**
- Modify: `scripts/build_dist.py`
- Test: `tests/unit/test_css_delivery.py`

- [ ] **Step 1: Write the test**

Append to `tests/unit/test_css_delivery.py`:

```python
import subprocess
import sys

class TestBuildDist:
    def test_dist_css_contains_layer_declaration(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        result = subprocess.run(
            [sys.executable, "scripts/build_dist.py"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"build_dist.py failed: {result.stderr}"
        css = (repo_root / "dist" / "dazzle.min.css").read_text()
        assert "@layer base, framework, app, overrides;" in css

    def test_dist_css_wraps_files_in_layer(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        css = (repo_root / "dist" / "dazzle.min.css").read_text()
        assert css.count("@layer framework {") >= 4  # at least the 4 canonical files
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_css_delivery.py::TestBuildDist -v`
Expected: FAIL — no `@layer` in current dist output

- [ ] **Step 3: Update `build_dist.py`**

In `scripts/build_dist.py`, replace `CSS_SOURCES` (lines 20-26) with canonical order:

```python
CSS_SOURCES = [
    STATIC / "css" / "dazzle-layer.css",
    STATIC / "css" / "design-system.css",
    STATIC / "css" / "dz.css",
    STATIC / "css" / "site-sections.css",
    STATIC / "css" / "feedback-widget.css",
]
```

Replace the CSS bundle section in `build()` (lines 125-136) with layer-aware concatenation:

```python
    # --- CSS bundle ---
    css_parts = ["@layer base, framework, app, overrides;\n"]
    for src in CSS_SOURCES:
        if not src.exists():
            print(f"WARNING: missing {src}", file=sys.stderr)
            continue
        content = src.read_text()
        css_parts.append(f"@layer framework {{\n{content}\n}}\n")
    css_combined = "\n".join(css_parts)
    css_minified = hdr + minify_css(css_combined)
    css_out = DIST_DIR / "dazzle.min.css"
    css_out.write_text(css_minified)
    raw = len(css_minified.encode())
    results.append((css_out.name, raw, gzip_size(css_minified.encode())))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_css_delivery.py::TestBuildDist -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Rebuild dist and commit**

```bash
python scripts/build_dist.py
git add scripts/build_dist.py dist/ tests/unit/test_css_delivery.py
git commit -m "feat(css): layer-aware build_dist.py with canonical order (#671)"
```

---

### Task 8: Tailwind Source Map in `build_css.py`

**Files:**
- Modify: `src/dazzle_ui/build_css.py:191-202`

- [ ] **Step 1: Check if `--sourcemap` is supported**

Run: `python -c "from dazzle_ui.build_css import _find_or_download_tailwind; tw = _find_or_download_tailwind(); print(tw)"` to get the binary path, then run it with `--help` to check for `--sourcemap` support.

If `--sourcemap` is NOT supported, skip this task and commit a note.

- [ ] **Step 2: Add `--sourcemap` flag**

In `src/dazzle_ui/build_css.py`, after the `--minify` append (line 202), add:

```python
        if minify:
            cmd.append("--minify")

        # Source map for local DevTools debugging
        cmd.append("--sourcemap")
```

- [ ] **Step 3: Verify the build still works**

Run: `python -c "from dazzle_ui.build_css import build_css; result = build_css(); print(result)"`
Expected: Path to output CSS file, no errors. Check if `.map` file was created alongside it.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/build_css.py
git commit -m "feat(css): add --sourcemap to Tailwind CLI build (#671)"
```

If `--sourcemap` is not supported, commit:
```bash
git commit --allow-empty -m "chore(css): skip Tailwind sourcemap — not supported by tailwind-cli-extra v2.8.1 (#671)"
```

---

### Task 9: Update `MANIFEST.in`

**Files:**
- Modify: `MANIFEST.in`

- [ ] **Step 1: Add explicit `.map` exclusion**

In `MANIFEST.in`, after line 26 (`global-exclude *.so`), add:

```
global-exclude *.map
```

- [ ] **Step 2: Commit**

```bash
git add MANIFEST.in
git commit -m "chore: explicitly exclude .map files from pip package (#671)"
```

---

### Task 10: Update CI — Release-Time Dist Build

**Files:**
- Modify: `.github/workflows/publish-pypi.yml`

- [ ] **Step 1: Add dist rebuild job**

In `.github/workflows/publish-pypi.yml`, add a new job before `build` that rebuilds dist and pushes it. Replace the top-level `permissions` and add the new job:

```yaml
permissions:
  contents: write  # needed for dist rebuild push

jobs:
  rebuild-dist:
    name: Rebuild dist bundles for CDN
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.12'

      - name: Rebuild dist
        run: python scripts/build_dist.py

      - name: Commit dist if changed
        run: |
          if git diff --quiet dist/; then
            echo "dist/ is up to date"
            exit 0
          fi
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add dist/
          git commit -m "chore: rebuild dist bundles for $(git describe --tags --always)"
          git push

  build:
    name: Build sdist and wheel
    needs: rebuild-dist
    runs-on: ubuntu-latest
```

Also update the `publish` job permissions to keep `id-token: write`:

```yaml
  publish:
    name: Publish to PyPI
    needs: [build, test-install]
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
      contents: read
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/publish-pypi.yml
git commit -m "ci: rebuild dist bundles at release time for CDN freshness (#671)"
```

---

### Task 11: Run Full Test Suite

- [ ] **Step 1: Run all CSS delivery tests**

Run: `pytest tests/unit/test_css_delivery.py -v`
Expected: ALL PASS

- [ ] **Step 2: Run template rendering tests**

Run: `pytest tests/unit/test_template_rendering.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full unit suite to check for regressions**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: ALL PASS, no regressions

- [ ] **Step 4: Lint**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: Clean

- [ ] **Step 5: Type check**

Run: `mypy src/dazzle`
Expected: Clean or no new errors

- [ ] **Step 6: Rebuild dist one final time**

Run: `python scripts/build_dist.py`
Expected: Clean build with layer wrappers in output

- [ ] **Step 7: Final commit if any lint/format fixes**

```bash
git add -u
git commit -m "chore: lint + format fixes for CSS delivery (#671)"
```
