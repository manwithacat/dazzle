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
DIST_DIR = REPO_ROOT / "dist"

STATIC = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static"
SITE_STATIC = REPO_ROOT / "src" / "dazzle_ui" / "static"

# Order mirrors static/css/dazzle.css and css_loader.CSS_SOURCE_FILES.
# Each entry is (layer_name, path). Pre-#920 this list was stale and
# only emitted the three legacy files, so dist/dazzle.min.css shipped
# with zero .dz-button (and every other v0.62 component) rules.
CSS_SOURCES: list[tuple[str, Path]] = [
    ("reset", STATIC / "css" / "reset.css"),
    ("vendor", STATIC / "vendor" / "tom-select.css"),
    ("vendor", STATIC / "vendor" / "flatpickr.css"),
    ("vendor", STATIC / "vendor" / "quill.snow.css"),
    ("vendor", STATIC / "vendor" / "pickr.css"),
    ("tokens", STATIC / "css" / "tokens.css"),
    ("tokens", STATIC / "css" / "design-system.css"),
    ("base", STATIC / "css" / "base.css"),
    ("utilities", STATIC / "css" / "utilities.css"),
    ("components", STATIC / "css" / "components" / "badge.css"),
    ("components", STATIC / "css" / "components" / "button.css"),
    ("components", STATIC / "css" / "components" / "dashboard.css"),
    ("components", STATIC / "css" / "components" / "detail.css"),
    ("components", STATIC / "css" / "components" / "form.css"),
    ("components", STATIC / "css" / "components" / "fragments.css"),
    ("components", STATIC / "css" / "components" / "htmx-states.css"),
    ("components", STATIC / "css" / "components" / "pdf-viewer.css"),
    ("components", STATIC / "css" / "components" / "regions.css"),
    ("components", STATIC / "css" / "components" / "table.css"),
    ("components", STATIC / "css" / "dazzle-layer.css"),
    ("components", STATIC / "css" / "site-sections.css"),
]

# Unlayered files appended after every @layer block — cascade override.
CSS_UNLAYERED: list[Path] = [
    STATIC / "css" / "dz.css",
    STATIC / "css" / "dz-widgets.css",
    STATIC / "css" / "dz-tones.css",
]

JS_SOURCES = [
    STATIC / "vendor" / "htmx.min.js",
    STATIC / "vendor" / "htmx-ext-json-enc.js",
    STATIC / "vendor" / "idiomorph-ext.min.js",
    STATIC / "vendor" / "htmx-ext-preload.js",
    STATIC / "vendor" / "htmx-ext-response-targets.js",
    STATIC / "vendor" / "htmx-ext-loading-states.js",
    STATIC / "vendor" / "htmx-ext-sse.js",
    # Alpine.js + plugins + components (order matters: plugins before core)
    STATIC / "vendor" / "sortable.min.js",
    STATIC / "vendor" / "alpine-sort.min.js",
    STATIC / "vendor" / "alpine-persist.min.js",
    STATIC / "js" / "dz-alpine.js",
    STATIC / "js" / "workspace-editor.js",
    STATIC / "vendor" / "alpine.min.js",
    # Dazzle runtime (a11y + islands)
    STATIC / "js" / "dz-a11y.js",
    STATIC / "js" / "dz-islands.js",
    # #946: pdf-viewer bridge handler. Bundled (rather than loaded as
    # a standalone <script> tag) so projects using `dist/dazzle.min.js`
    # get the chrome wired automatically when they adopt the
    # `display: pdf_viewer` DSL hook or the `pdf_viewer.html` include.
    STATIC / "js" / "pdf-viewer.js",
    SITE_STATIC / "js" / "site.js",
]

ICONS_SOURCES = [
    STATIC / "vendor" / "lucide.min.js",
]

# Framework JS files get comment stripping; vendor files are left as-is.
FRAMEWORK_JS = {
    "dz-alpine.js",
    "workspace-editor.js",
    "dz-a11y.js",
    "dz-islands.js",
    "pdf-viewer.js",
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
        content = src.read_text()
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
