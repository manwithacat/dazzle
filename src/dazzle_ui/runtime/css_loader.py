"""
CSS loader for Dazzle UI runtime.

Loads and concatenates CSS files from static/css/ to produce
the bundled stylesheet served at /styles/dazzle.css.

Uses CSS Cascade Layers (@layer) for explicit ordering.
Generates an inline source map for DevTools debugging.
"""

import base64
import json
from pathlib import Path

_STATIC_CSS_DIR = Path(__file__).parent / "static" / "css"

# Canonical CSS source order — must match dazzle-framework.css and build_dist.py.
CSS_SOURCE_FILES = (
    "dazzle-layer.css",
    "design-system.css",
    "site-sections.css",
)

# Files loaded unlayered (after framework layer) so they can override DaisyUI.
CSS_UNLAYERED_FILES = ("dz.css",)


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

    # Unlayered files — must come after the layer block so they can override
    # DaisyUI's unlayered drawer/sidebar base styles.
    for filename in CSS_UNLAYERED_FILES:
        parts.append(f"/* --- {filename} (unlayered — overrides DaisyUI) --- */")
        parts.append(_load_css_file(filename))
        parts.append("")

    # Inline source map (file-level, not line-level)
    all_sources = list(CSS_SOURCE_FILES) + list(CSS_UNLAYERED_FILES)
    source_map = {"version": 3, "sources": all_sources, "mappings": ""}
    map_b64 = base64.b64encode(json.dumps(source_map).encode()).decode()
    parts.append(f"/*# sourceMappingURL=data:application/json;base64,{map_b64} */")

    return "\n".join(parts)
