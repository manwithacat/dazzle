"""
Theme token generators for typography, spacing, and shape.

Generates design tokens from ThemeSpec section models.
All outputs are flat dicts of token name -> CSS value string.
"""

from __future__ import annotations

from .ir.themespec import (
    TYPOGRAPHY_RATIO_VALUES,
    DensityEnum,
    ShadowPreset,
    ShapePreset,
    TypographyRatioPreset,
)

# =============================================================================
# Typography
# =============================================================================

# Type scale step names and their positions relative to base (0)
_TYPE_STEPS: list[tuple[str, int]] = [
    ("text-xs", -2),
    ("text-sm", -1),
    ("text-base", 0),
    ("text-lg", 1),
    ("text-xl", 2),
    ("text-2xl", 3),
    ("text-3xl", 4),
    ("text-4xl", 5),
    ("text-5xl", 6),
    ("text-6xl", 7),
]


def generate_type_scale(
    base_size_px: int = 16,
    ratio: TypographyRatioPreset = TypographyRatioPreset.MAJOR_THIRD,
    line_height_body: float = 1.6,
    line_height_heading: float = 1.2,
) -> dict[str, str]:
    """Generate a modular type scale.

    Args:
        base_size_px: Base font size in pixels.
        ratio: Modular scale ratio preset.
        line_height_body: Line height for body text (steps <= 0).
        line_height_heading: Line height for headings (steps > 0).

    Returns:
        Dict of token names to CSS values (rem sizes and line heights).
    """
    ratio_value = TYPOGRAPHY_RATIO_VALUES.get(ratio, 1.250)
    tokens: dict[str, str] = {}

    for name, step in _TYPE_STEPS:
        size_px = base_size_px * (ratio_value**step)
        size_rem = size_px / 16  # Convert to rem (based on 16px browser default)
        tokens[name] = f"{size_rem:.4f}rem"

        # Add corresponding line height
        lh = line_height_body if step <= 0 else line_height_heading
        tokens[f"{name}-lh"] = f"{lh}"

    return tokens


# =============================================================================
# Spacing
# =============================================================================

# Density multipliers
_DENSITY_MULTIPLIERS: dict[str, float] = {
    DensityEnum.COMPACT: 0.75,
    DensityEnum.COMFORTABLE: 1.0,
    DensityEnum.SPACIOUS: 1.5,
}

# Spacing scale multipliers (space-0 through space-16)
_SPACING_MULTIPLIERS: list[tuple[str, float]] = [
    ("space-0", 0),
    ("space-px", 0.25),
    ("space-0.5", 0.5),
    ("space-1", 1),
    ("space-1.5", 1.5),
    ("space-2", 2),
    ("space-2.5", 2.5),
    ("space-3", 3),
    ("space-3.5", 3.5),
    ("space-4", 4),
    ("space-5", 5),
    ("space-6", 6),
    ("space-7", 7),
    ("space-8", 8),
    ("space-9", 9),
    ("space-10", 10),
    ("space-11", 11),
    ("space-12", 12),
    ("space-14", 14),
    ("space-16", 16),
]


def generate_spacing_scale(
    base_unit_px: int = 4,
    density: DensityEnum = DensityEnum.COMFORTABLE,
) -> dict[str, str]:
    """Generate a spacing scale.

    Args:
        base_unit_px: Base spacing unit in pixels.
        density: Density preset affecting spacing multiplier.

    Returns:
        Dict of token names to CSS values (rem).
    """
    density_mult = _DENSITY_MULTIPLIERS.get(density, 1.0)
    tokens: dict[str, str] = {}

    for name, mult in _SPACING_MULTIPLIERS:
        px = base_unit_px * mult * density_mult
        rem = px / 16
        if px == 0:
            tokens[name] = "0"
        else:
            tokens[name] = f"{rem:.4f}rem"

    return tokens


# =============================================================================
# Shape
# =============================================================================

# Radius values per preset (sm, md, lg, full)
_RADIUS_PRESETS: dict[str, dict[str, str]] = {
    ShapePreset.SHARP: {
        "radius-sm": "0",
        "radius-md": "0",
        "radius-lg": "0.125rem",
        "radius-full": "9999px",
    },
    ShapePreset.SUBTLE: {
        "radius-sm": "0.125rem",
        "radius-md": "0.25rem",
        "radius-lg": "0.5rem",
        "radius-full": "9999px",
    },
    ShapePreset.ROUNDED: {
        "radius-sm": "0.25rem",
        "radius-md": "0.5rem",
        "radius-lg": "1rem",
        "radius-full": "9999px",
    },
    ShapePreset.PILL: {
        "radius-sm": "0.5rem",
        "radius-md": "1rem",
        "radius-lg": "1.5rem",
        "radius-full": "9999px",
    },
}

# Shadow values per preset (sm, md, lg, xl)
_SHADOW_PRESETS: dict[str, dict[str, str]] = {
    ShadowPreset.NONE: {
        "shadow-sm": "none",
        "shadow-md": "none",
        "shadow-lg": "none",
        "shadow-xl": "none",
    },
    ShadowPreset.SUBTLE: {
        "shadow-sm": "0 1px 2px oklch(0 0 0 / 0.04)",
        "shadow-md": "0 2px 4px oklch(0 0 0 / 0.06)",
        "shadow-lg": "0 4px 8px oklch(0 0 0 / 0.08)",
        "shadow-xl": "0 8px 16px oklch(0 0 0 / 0.10)",
    },
    ShadowPreset.MEDIUM: {
        "shadow-sm": "0 1px 3px oklch(0 0 0 / 0.08)",
        "shadow-md": "0 4px 6px oklch(0 0 0 / 0.10)",
        "shadow-lg": "0 8px 16px oklch(0 0 0 / 0.12)",
        "shadow-xl": "0 16px 32px oklch(0 0 0 / 0.16)",
    },
    ShadowPreset.DRAMATIC: {
        "shadow-sm": "0 2px 4px oklch(0 0 0 / 0.12)",
        "shadow-md": "0 6px 12px oklch(0 0 0 / 0.16)",
        "shadow-lg": "0 12px 24px oklch(0 0 0 / 0.20)",
        "shadow-xl": "0 24px 48px oklch(0 0 0 / 0.24)",
    },
}


def generate_shape_tokens(
    radius_preset: ShapePreset = ShapePreset.SUBTLE,
    shadow_preset: ShadowPreset = ShadowPreset.MEDIUM,
    border_width_px: int = 1,
) -> dict[str, str]:
    """Generate shape tokens (radii, shadows, borders).

    Args:
        radius_preset: Border radius preset.
        shadow_preset: Shadow depth preset.
        border_width_px: Default border width.

    Returns:
        Dict of token names to CSS values.
    """
    tokens: dict[str, str] = {}

    # Radii
    radii = _RADIUS_PRESETS.get(radius_preset, _RADIUS_PRESETS[ShapePreset.SUBTLE])
    tokens.update(radii)

    # Shadows
    shadows = _SHADOW_PRESETS.get(shadow_preset, _SHADOW_PRESETS[ShadowPreset.MEDIUM])
    tokens.update(shadows)

    # Border width
    tokens["border-width"] = f"{border_width_px}px"

    return tokens
