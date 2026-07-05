"""Build distribution bundles for Dazzle CSS/JS assets.

Concatenates and minifies CSS/JS into dist/ bundles.
Run from repo root: python scripts/build_dist.py
"""

from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# #950: bundle outputs live UNDER the framework's static tree so the
# wheel ships them automatically (MANIFEST.in's static/*.{js,css} rule)
# and the existing `/static/` FastAPI mount serves them at
# `/static/dist/dazzle.min.{js,css}`. Pre-#950 these were at
# repo-root `dist/`, which the wheel didn't include — projects on
# `[ui] assets = "auto"` (default) hard-404'd in production once
# DAZZLE_ENV=production tipped them into bundled mode.
DIST_DIR = REPO_ROOT / "src" / "dazzle" / "page" / "runtime" / "static" / "dist"

STATIC = REPO_ROOT / "src" / "dazzle" / "page" / "runtime" / "static"
HM = REPO_ROOT / "packages" / "hatchi-maxchi"
SITE_STATIC = REPO_ROOT / "src" / "dazzle" / "page" / "static"

# Sentinels for the HaTchi-MaXchi bundle. HM publishes UNPREFIXED; Dazzle
# applies its own `dz-` namespace at ingest by building the bundle with
# prefix="dz-" (a no-op transform on the dz- source → byte-identical to the
# pre-flip artifact). These aren't read as files — the build loops detect
# them and call the package build.py.
HM_DIST_CSS = HM / "dist" / "hatchi-maxchi.css"
HM_DIST_JS = HM / "dist" / "hatchi-maxchi.js"


def _hm_build():  # type: ignore[no-untyped-def]
    """Load packages/hatchi-maxchi/build.py by explicit path (not `import
    build`, which would clobber other `build` modules)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_hm_build_dist", HM / "build.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Order mirrors static/css/dazzle.css and css_loader.CSS_SOURCE_FILES.
# Each entry is (layer_name, path). Pre-#920 this list was stale and
# only emitted the three legacy files, so dist/dazzle.min.css shipped
# with zero .dz-button (and every other v0.62 component) rules.
# Layer name None = pre-layered artifact, appended raw (HM dist carries
# its own @layer blocks using the same layer names as ours).
CSS_SOURCES: list[tuple[str | None, Path]] = [
    ("reset", STATIC / "css" / "reset.css"),
    ("vendor", STATIC / "vendor" / "tom-select.css"),
    ("vendor", STATIC / "vendor" / "flatpickr.css"),
    # HaTchi-MaXchi — built at ingest with prefix="dz-" (see _hm_build /
    # HM_DIST_CSS). After editing package CSS, rebuild the package
    # (`python packages/hatchi-maxchi/build.py`) then this bundle.
    (None, HM_DIST_CSS),
    # quill.snow.css removed in #977 cycle 4 — replaced by dz-richtext.
    # pickr.css removed in #976 — `widget=color` uses native <input type="color">,
    # no vendor CSS required (mirrors css_loader.CSS_SOURCE_FILES).
    ("utilities", STATIC / "css" / "utilities.css"),
    ("components", STATIC / "css" / "components" / "dashboard.css"),
    ("components", STATIC / "css" / "components" / "detail.css"),
    ("components", STATIC / "css" / "components" / "fragments.css"),
    ("components", STATIC / "css" / "components" / "pdf-viewer.css"),
    ("components", STATIC / "css" / "components" / "regions.css"),
    ("components", STATIC / "css" / "components" / "mobile-scroll.css"),
    # #977 cycle 1 — Dazzle-native rich-text editor.
    ("components", STATIC / "css" / "components" / "richtext.css"),
    # v0.71.x guided onboarding (overlay primitives for the eight step kinds).
    ("components", STATIC / "css" / "components" / "onboarding.css"),
    ("components", STATIC / "css" / "dazzle-layer.css"),
    ("components", STATIC / "css" / "site-sections.css"),
]

# Unlayered files appended after every @layer block — cascade override.
CSS_UNLAYERED: list[Path] = [
    STATIC / "css" / "dz.css",
    STATIC / "css" / "dz-widgets.css",
    STATIC / "css" / "dz-tones.css",
]

# JS_SOURCES order MUST match base.html's individual-branch script order
# so the bundled execution order is identical to the unbundled. Any new
# script added to base.html must also land here. The drift gate in
# tests/unit/test_asset_bundle.py::TestBundleListParity catches omissions.
JS_SOURCES = [
    # HTMX core + extensions (vendored). Order: core first, then extensions.
    STATIC / "vendor" / "htmx.min.js",
    # 2b preload-drill (#1491): hover-preload the detail page for a perceived-
    # instant drill. htmx 4 activates an extension by inclusion (no hx-ext); the
    # `hx-preload="mouseover"` attribute on clickable rows does the rest.
    STATIC / "vendor" / "hx-preload.min.js",
    # Alpine plugins + Alpine core (order matters: plugins before core).
    # SortableJS + alpine-sort were removed in #948 cycle 1 — pointer-event
    # drag in dashboard-builder.js replaced them. workspace-editor.js was
    # similarly retired. Keep the list tight; the drift gate in
    # tests/unit/test_asset_bundle.py catches both stale entries (files
    # in JS_SOURCES that no longer exist on disk OR aren't referenced
    # from base.html) and missing entries (scripts in base.html that
    # aren't bundled).
    STATIC / "vendor" / "alpine-persist.min.js",
    STATIC / "vendor" / "alpine-anchor.min.js",
    STATIC / "vendor" / "alpine-collapse.min.js",
    STATIC / "vendor" / "alpine-focus.min.js",
    STATIC / "js" / "dz-alpine.js",
    STATIC / "js" / "dashboard-builder.js",
    STATIC / "vendor" / "alpine.min.js",
    # Dazzle runtime (csrf + a11y + islands + bridge + widget registry)
    # #1337: dz-csrf.js wires the htmx:configRequest CSRF echo. Bundled (not a
    # standalone <script>) so it loads on every app page the dist bundle does —
    # which is all of them, since app_chrome.js_scripts always points at the
    # bundle. Ordered first in the runtime block so the listener is registered
    # before any other runtime code can trigger an htmx request.
    # HaTchi-MaXchi controllers — the published dist artifact (Phase 2).
    HM_DIST_JS,
    STATIC / "js" / "dz-csrf.js",
    STATIC / "js" / "dz-a11y.js",
    STATIC / "js" / "dz-islands.js",
    STATIC / "js" / "dz-component-bridge.js",
    STATIC / "js" / "dz-widget-registry.js",
    # #977 cycle 1 — Dazzle-native rich-text editor (registers as
    # "richtext-native" alongside the Quill bridge until cycle 4).
    STATIC / "js" / "dz-richtext.js",
    # #946: pdf-viewer bridge handler. Bundled (rather than loaded as
    # a standalone <script> tag) so projects using `dist/dazzle.min.js`
    # get the chrome wired automatically when they adopt the
    # `display: pdf_viewer` DSL hook or the `pdf_viewer.html` include.
    STATIC / "js" / "pdf-viewer.js",
    # #947: dz-debug introspection helper for the Alpine × HTMX bridge.
    # Exposes window.dzDebug for tests (proxy identity, last settle
    # timestamp, component root listing). Bundle cost ~1KB; methods
    # only do work when called.
    STATIC / "js" / "dz-debug.js",
    # htmx 4 migration: auto-dismiss bridge for OOB toasts (replaces the
    # dropped htmx-2 remove-me extension).
    STATIC / "js" / "dz-toast.js",
    # ADR-0050 Phase 5 / 1a: first-party form-field engagement beacon. Fires a
    # sendBeacon on a field's first focus so the 1a widget inferer can adapt to
    # real usage. Zero-dep, best-effort, same-origin.
    STATIC / "js" / "dz-usage.js",
    # Convergence C2.1: column-visibility as a delegated extension on the HM
    # grid primitive's seams (replaces dzTable's Alpine implementation).
    STATIC / "js" / "dz-grid-cols.js",
    # Convergence C2.2: column resize as a delegated extension (net-new as a
    # reachable feature — the dzTable code was never wired to any markup).
    STATIC / "js" / "dz-grid-resize.js",
    # Convergence C2.3: inline cell editing as a delegated extension (the
    # dzTable commit URL never matched the mounted field route — silent 404).
    STATIC / "js" / "dz-grid-edit.js",
    SITE_STATIC / "js" / "site.js",
]

ICONS_SOURCES = [
    STATIC / "vendor" / "lucide.min.js",
]

# Framework JS files get comment stripping; vendor files are left as-is.
FRAMEWORK_JS = {
    "dz-alpine.js",
    "workspace-editor.js",
    "dz-csrf.js",
    "dz-a11y.js",
    "dz-islands.js",
    "pdf-viewer.js",
    "dz-debug.js",
    "dz-toast.js",
    "dz-grid-cols.js",
    "dz-grid-resize.js",
    "dz-grid-edit.js",
    "site.js",
}


def read_version() -> str:
    pyproject = REPO_ROOT / "pyproject.toml"
    for line in pyproject.read_text().splitlines():
        m = re.match(r'^version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    print("ERROR: could not find version in pyproject.toml", file=sys.stderr)
    sys.exit(1)


def banner(version: str) -> str:
    return f"/* dazzle v{version} | MIT License | https://github.com/manwithacat/dazzle */\n"


def minify_css(text: str) -> str:
    """Strip block comments, collapse whitespace, remove blank lines."""
    # Strip block comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Process line by line: strip leading/trailing whitespace, drop blank lines
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            # Collapse runs of whitespace to single space
            stripped = re.sub(r"\s+", " ", stripped)
            lines.append(stripped)
    return "\n".join(lines) + "\n"


def strip_js_comments(text: str) -> str:
    """Strip single-line comment lines and blank lines from framework JS."""
    lines = []
    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        if trimmed.startswith("//"):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def process_js(path: Path) -> str:
    """Read a JS file, stripping comments if it's a framework file."""
    content = path.read_text()
    if path.name in FRAMEWORK_JS:
        return strip_js_comments(content)
    return content


def gzip_size(data: bytes) -> int:
    return len(gzip.compress(data, compresslevel=9))


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    return f"{n / 1024:.1f} KB"


def build() -> None:
    version = read_version()
    DIST_DIR.mkdir(exist_ok=True)
    hdr = banner(version)

    results: list[tuple[str, int, int]] = []

    # --- CSS bundle ---
    # Layer order matches static/css/dazzle.css. Each layered file
    # gets wrapped in `@layer <name> { ... }`; unlayered files are
    # appended last so they win the cascade.
    css_parts = ["@layer reset, vendor, tokens, base, utilities, components, overrides;\n"]
    for layer, src in CSS_SOURCES:
        if not src.exists():
            print(f"WARNING: missing {src}", file=sys.stderr)
            continue
        if src == HM_DIST_CSS:
            # HM publishes UNPREFIXED; Dazzle applies its `dz-` namespace at
            # ingest by building the bundle with prefix="dz-" (byte-identical
            # to the pre-flip artifact — the production test of the prefix
            # mechanism). Pre-layered; font URLs rewritten to /static/fonts/.
            content = _hm_build().build_css("dz-").replace('url("fonts/', 'url("/static/fonts/')
            css_parts.append(content + "\n")
            continue
        content = src.read_text()
        if layer is None:
            # Pre-layered HM artifact; its font URLs are standalone-relative —
            # rewrite to Dazzle's static mount (mirrors css_loader).
            css_parts.append(content.replace('url("fonts/', 'url("/static/fonts/') + "\n")
        else:
            css_parts.append(f"@layer {layer} {{\n{content}\n}}\n")
    for src in CSS_UNLAYERED:
        if not src.exists():
            print(f"WARNING: missing {src}", file=sys.stderr)
            continue
        css_parts.append(src.read_text())
    css_combined = "\n".join(css_parts)
    css_minified = hdr + minify_css(css_combined)
    css_out = DIST_DIR / "dazzle.min.css"
    css_out.write_text(css_minified)
    raw = len(css_minified.encode())
    results.append((css_out.name, raw, gzip_size(css_minified.encode())))

    # --- JS bundle ---
    js_parts = []
    for src in JS_SOURCES:
        if src == HM_DIST_JS:
            js_parts.append(_hm_build().build_js("dz-"))  # apply Dazzle's namespace at ingest
            continue
        if not src.exists():
            print(f"WARNING: missing {src}", file=sys.stderr)
            continue
        js_parts.append(process_js(src))
    js_combined = hdr + ";\n".join(js_parts)
    js_out = DIST_DIR / "dazzle.min.js"
    js_out.write_text(js_combined)
    raw = len(js_combined.encode())
    results.append((js_out.name, raw, gzip_size(js_combined.encode())))

    # --- Icons bundle ---
    icons_parts = []
    for src in ICONS_SOURCES:
        if not src.exists():
            print(f"WARNING: missing {src}", file=sys.stderr)
            continue
        icons_parts.append(src.read_text())
    icons_combined = hdr + "\n".join(icons_parts)
    icons_out = DIST_DIR / "dazzle-icons.min.js"
    icons_out.write_text(icons_combined)
    raw = len(icons_combined.encode())
    results.append((icons_out.name, raw, gzip_size(icons_combined.encode())))

    # --- Size report ---
    print()
    print(f"  dazzle v{version} dist build")
    print(f"  {'─' * 48}")
    print(f"  {'File':<24} {'Raw':>10} {'Gzip':>10}")
    print(f"  {'─' * 48}")
    for name, raw_size, gz_size in results:
        print(f"  {name:<24} {fmt_size(raw_size):>10} {fmt_size(gz_size):>10}")
    print(f"  {'─' * 48}")
    print()


if __name__ == "__main__":
    build()
