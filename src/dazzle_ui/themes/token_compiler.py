"""
Design token compiler.

Converts constrained design token presets into CSS custom properties
that are injected into base.html. The token system ensures all valid
combinations produce acceptable designs — the LLM cannot choose a
wrong combination.

Token axes:
- spacing: compact | normal | relaxed
- density: data-heavy | balanced | spacious
- tone: corporate | friendly | minimal
- palette: blue | green | purple | neutral
"""

from __future__ import annotations

from typing import Any

# Spacing presets
_SPACING = {
    "compact": {
        "space-xs": "0.125rem",
        "space-sm": "0.25rem",
        "space-md": "0.5rem",
        "space-lg": "0.75rem",
        "space-xl": "1rem",
    },
    "normal": {
        "space-xs": "0.25rem",
        "space-sm": "0.5rem",
        "space-md": "1rem",
        "space-lg": "1.5rem",
        "space-xl": "2rem",
    },
    "relaxed": {
        "space-xs": "0.5rem",
        "space-sm": "0.75rem",
        "space-md": "1.25rem",
        "space-lg": "2rem",
        "space-xl": "3rem",
    },
}

# Density presets (affects table row height, card padding)
_DENSITY = {
    "data-heavy": {
        "row-height": "2rem",
        "card-padding": "0.75rem",
        "font-size-base": "0.8125rem",
    },
    "balanced": {
        "row-height": "2.5rem",
        "card-padding": "1.25rem",
        "font-size-base": "0.875rem",
    },
    "spacious": {
        "row-height": "3rem",
        "card-padding": "1.5rem",
        "font-size-base": "1rem",
    },
}

# Tone presets (affects border radius, font weight)
_TONE = {
    "corporate": {
        "radius": "0.25rem",
        "radius-lg": "0.375rem",
        "font-weight-heading": "700",
        "shadow": "0 1px 3px rgba(0,0,0,0.12)",
    },
    "friendly": {
        "radius": "0.5rem",
        "radius-lg": "0.75rem",
        "font-weight-heading": "600",
        "shadow": "0 2px 8px rgba(0,0,0,0.08)",
    },
    "minimal": {
        "radius": "0.125rem",
        "radius-lg": "0.25rem",
        "font-weight-heading": "500",
        "shadow": "0 1px 2px rgba(0,0,0,0.05)",
    },
}

# Palette presets (primary, accent, surface colors)
_PALETTE = {
    "blue": {
        "primary": "#3b82f6",
        "primary-focus": "#2563eb",
        "accent": "#06b6d4",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "danger": "#ef4444",
    },
    "green": {
        "primary": "#22c55e",
        "primary-focus": "#16a34a",
        "accent": "#14b8a6",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "danger": "#ef4444",
    },
    "purple": {
        "primary": "#8b5cf6",
        "primary-focus": "#7c3aed",
        "accent": "#ec4899",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "danger": "#ef4444",
    },
    "neutral": {
        "primary": "#6b7280",
        "primary-focus": "#4b5563",
        "accent": "#9ca3af",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "danger": "#ef4444",
    },
}


def compile_design_tokens(
    spacing: str = "normal",
    density: str = "balanced",
    tone: str = "corporate",
    palette: str = "blue",
) -> dict[str, str]:
    """
    Compile design tokens from axis selections into CSS custom properties.

    All combinations are valid and produce acceptable designs.

    Args:
        spacing: compact | normal | relaxed
        density: data-heavy | balanced | spacious
        tone: corporate | friendly | minimal
        palette: blue | green | purple | neutral

    Returns:
        Dictionary of CSS custom property name → value (without --dz- prefix).
    """
    tokens: dict[str, str] = {}

    tokens.update(_SPACING.get(spacing, _SPACING["normal"]))
    tokens.update(_DENSITY.get(density, _DENSITY["balanced"]))
    tokens.update(_TONE.get(tone, _TONE["corporate"]))
    tokens.update(_PALETTE.get(palette, _PALETTE["blue"]))

    return tokens


def tokens_to_css(tokens: dict[str, str]) -> str:
    """
    Convert design tokens dict to a CSS :root block.

    Args:
        tokens: Token name → value mapping.

    Returns:
        CSS string with :root custom properties.
    """
    lines = [":root {"]
    for key, value in sorted(tokens.items()):
        lines.append(f"  --dz-{key}: {value};")
    lines.append("}")
    return "\n".join(lines)


def compile_tokens_from_manifest(theme_config: dict[str, Any]) -> dict[str, str]:
    """
    Compile tokens from a dazzle.toml [theme] section.

    Args:
        theme_config: Theme configuration dict with optional keys:
            spacing, density, tone, palette.

    Returns:
        Design tokens dictionary.
    """
    return compile_design_tokens(
        spacing=theme_config.get("spacing", "normal"),
        density=theme_config.get("density", "balanced"),
        tone=theme_config.get("tone", "corporate"),
        palette=theme_config.get("palette", "blue"),
    )
