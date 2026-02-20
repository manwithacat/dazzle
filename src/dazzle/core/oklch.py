"""
Pure-Python OKLCH palette generation.

Generates a complete design-system color palette from a brand hue and chroma
using the OKLCH color space. No external color libraries required.
"""

from __future__ import annotations


def oklch_to_css(L: float, C: float, H: float, alpha: float = 1.0) -> str:
    """Format an OKLCH color as a CSS string.

    Args:
        L: Lightness (0-1).
        C: Chroma (0-0.4).
        H: Hue (0-360).
        alpha: Opacity (0-1).

    Returns:
        CSS oklch() string.
    """
    L_fmt = f"{L:.3f}"
    C_fmt = f"{C:.4f}"
    H_fmt = f"{H:.1f}"
    if alpha < 1.0:
        return f"oklch({L_fmt} {C_fmt} {H_fmt} / {alpha:.2f})"
    return f"oklch({L_fmt} {C_fmt} {H_fmt})"


# Curated lightness stops for a 10-step scale (50 through 950).
# These are perceptually balanced rather than linearly spaced.
_LIGHTNESS_STOPS: tuple[float, ...] = (
    0.97,  # 50  — very light
    0.93,  # 100
    0.87,  # 200
    0.78,  # 300
    0.67,  # 400
    0.55,  # 500 — mid
    0.45,  # 600
    0.35,  # 700
    0.25,  # 800
    0.15,  # 900/950 — very dark
)

_STEP_NAMES: tuple[str, ...] = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "950")


def _generate_scale(hue: float, chroma: float, *, invert: bool = False) -> dict[str, str]:
    """Generate a 10-step color scale for one hue.

    Args:
        hue: OKLCH hue.
        chroma: OKLCH chroma.
        invert: If True, invert lightness for dark mode.

    Returns:
        Dict mapping step names to CSS oklch() values.
    """
    stops = _LIGHTNESS_STOPS
    if invert:
        stops = list(reversed(stops))

    scale: dict[str, str] = {}
    for name, lightness in zip(_STEP_NAMES, stops, strict=True):
        # Reduce chroma at extremes for perceptual balance
        adj_chroma = chroma
        if lightness > 0.9 or lightness < 0.2:
            adj_chroma = chroma * 0.5
        elif lightness > 0.8 or lightness < 0.3:
            adj_chroma = chroma * 0.75
        scale[name] = oklch_to_css(lightness, adj_chroma, hue)
    return scale


def generate_palette(
    brand_hue: float,
    brand_chroma: float = 0.15,
    mode: str = "light",
    *,
    accent_hue_offset: float = 30.0,
    neutral_chroma: float = 0.02,
    semantic_overrides: dict[str, float] | None = None,
) -> dict[str, str]:
    """Generate a complete design-system palette.

    Args:
        brand_hue: Primary brand hue (0-360).
        brand_chroma: Primary brand chroma (0-0.4).
        mode: Color mode ("light" or "dark").
        accent_hue_offset: Hue offset for secondary color.
        neutral_chroma: Chroma for neutral tones.
        semantic_overrides: Override semantic hues (success_hue, warning_hue, etc.).

    Returns:
        Flat dict of token names to CSS oklch() values.
    """
    dark = mode == "dark"
    overrides = semantic_overrides or {}

    # Primary scale
    primary = _generate_scale(brand_hue, brand_chroma, invert=dark)

    # Secondary (offset from primary)
    secondary_hue = (brand_hue + accent_hue_offset) % 360
    secondary = _generate_scale(secondary_hue, brand_chroma * 0.8, invert=dark)

    # Accent (complementary)
    accent_hue = (brand_hue + 180) % 360
    accent = _generate_scale(accent_hue, brand_chroma * 0.7, invert=dark)

    # Neutral
    neutral = _generate_scale(brand_hue, neutral_chroma, invert=dark)

    # Semantic colors (fixed hues with overrides)
    semantic_hues = {
        "success": overrides.get("success_hue", 145.0),
        "warning": overrides.get("warning_hue", 85.0),
        "danger": overrides.get("danger_hue", 25.0),
        "info": overrides.get("info_hue", 240.0),
    }
    semantic_chroma = min(brand_chroma * 1.2, 0.2)

    # Build flat palette
    palette: dict[str, str] = {}

    # Add scales with prefixes
    for name, value in primary.items():
        palette[f"primary-{name}"] = value
    for name, value in secondary.items():
        palette[f"secondary-{name}"] = value
    for name, value in accent.items():
        palette[f"accent-{name}"] = value
    for name, value in neutral.items():
        palette[f"neutral-{name}"] = value

    # Semantic colors (just key stops: 500 for main, 100 for bg, 800 for text)
    for semantic_name, semantic_hue in semantic_hues.items():
        sem_scale = _generate_scale(semantic_hue, semantic_chroma, invert=dark)
        palette[f"{semantic_name}-bg"] = sem_scale["100"]
        palette[f"{semantic_name}"] = sem_scale["500"]
        palette[f"{semantic_name}-text"] = sem_scale["800"]

    # Background tokens
    if dark:
        palette["bg-primary"] = oklch_to_css(0.13, neutral_chroma * 0.5, brand_hue)
        palette["bg-secondary"] = oklch_to_css(0.17, neutral_chroma * 0.5, brand_hue)
        palette["bg-tertiary"] = oklch_to_css(0.21, neutral_chroma * 0.5, brand_hue)
    else:
        palette["bg-primary"] = oklch_to_css(0.99, neutral_chroma * 0.3, brand_hue)
        palette["bg-secondary"] = oklch_to_css(0.96, neutral_chroma * 0.3, brand_hue)
        palette["bg-tertiary"] = oklch_to_css(0.93, neutral_chroma * 0.3, brand_hue)

    # Text tokens
    if dark:
        palette["text-primary"] = oklch_to_css(0.93, 0.0, 0.0)
        palette["text-secondary"] = oklch_to_css(0.75, 0.0, 0.0)
        palette["text-muted"] = oklch_to_css(0.55, 0.0, 0.0)
    else:
        palette["text-primary"] = oklch_to_css(0.15, 0.0, 0.0)
        palette["text-secondary"] = oklch_to_css(0.35, 0.0, 0.0)
        palette["text-muted"] = oklch_to_css(0.55, 0.0, 0.0)

    # Border tokens
    if dark:
        palette["border-default"] = oklch_to_css(0.30, neutral_chroma * 0.5, brand_hue)
        palette["border-strong"] = oklch_to_css(0.45, neutral_chroma, brand_hue)
    else:
        palette["border-default"] = oklch_to_css(0.85, neutral_chroma * 0.5, brand_hue)
        palette["border-strong"] = oklch_to_css(0.70, neutral_chroma, brand_hue)

    return palette
