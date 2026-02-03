"""
CSS loader for Dazzle UI runtime.

Loads and concatenates CSS files from static/css/ to produce
the bundled stylesheet served at /styles/dazzle.css.

Extracted from vite_generator.py to decouple CSS bundling
from the deprecated Vite pipeline.
"""

from __future__ import annotations

from pathlib import Path

_STATIC_CSS_DIR = Path(__file__).parent / "static" / "css"

# CSS source files to concatenate for the bundled stylesheet.
# With DaisyUI loaded via CDN, we only need the DAZZLE semantic layer
# plus the design system overrides.
CSS_SOURCE_FILES = [
    "dazzle-layer.css",  # Semantic aliases on top of DaisyUI + Tailwind
    "site-sections.css",  # Site section components (v0.16.0)
    "design-system.css",  # Design system tokens + component overrides (v0.22.0)
]


def _load_css_file(filename: str) -> str:
    """Load a CSS file from the static/css directory."""
    path = _STATIC_CSS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"CSS file not found: {path}")
    return path.read_text(encoding="utf-8")


def get_bundled_css(theme_css: str | None = None) -> str:
    """
    Load and concatenate CSS files from static/css/.

    With DaisyUI loaded via CDN, this only includes the thin DAZZLE
    semantic layer that provides app structure and semantic aliases.

    Args:
        theme_css: Optional generated theme CSS to prepend (from ThemeSpec)

    Returns:
        Concatenated CSS content
    """
    parts = [
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
        parts.append(theme_css)
        parts.append("")

    for filename in CSS_SOURCE_FILES:
        parts.append(f"/* --- {filename} --- */")
        parts.append(_load_css_file(filename))
        parts.append("")
    return "\n".join(parts)
