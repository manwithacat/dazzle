"""
Theme resolver for DAZZLE.

Resolves the final theme by merging:
1. Base preset (from theme name/kind)
2. Manifest custom tokens
3. SiteSpec theme overrides (highest precedence)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dazzle_ui.specs.theme import ThemeSpec, ThemeTokens, VariantSpec

if TYPE_CHECKING:
    from dazzle.core.ir.themespec import ThemeSpecYAML

from .presets import SAAS_DEFAULT_THEME, get_theme_preset


def resolve_theme(
    preset_name: str = "saas-default",
    manifest_overrides: dict[str, Any] | None = None,
    sitespec_overrides: dict[str, Any] | None = None,
) -> ThemeSpec:
    """
    Resolve the final theme by merging preset with overrides.

    Args:
        preset_name: Name of the base preset ("saas-default", "minimal")
        manifest_overrides: Token overrides from dazzle.toml [theme]
        sitespec_overrides: Token overrides from sitespec.yaml layout.theme_overrides

    Returns:
        Final ThemeSpec with all overrides applied
    """
    # Get base preset
    base_theme = get_theme_preset(preset_name)
    if base_theme is None:
        # Fall back to saas-default if unknown preset
        base_theme = SAAS_DEFAULT_THEME

    # If no overrides, return base theme as-is
    if not manifest_overrides and not sitespec_overrides:
        return base_theme

    # Merge overrides into base theme
    merged_tokens = _merge_tokens(
        base_theme.tokens,
        manifest_overrides or {},
        sitespec_overrides or {},
    )

    # Merge variant overrides
    merged_variants = _merge_variants(
        base_theme.variants,
        manifest_overrides or {},
        sitespec_overrides or {},
    )

    return ThemeSpec(
        name=base_theme.name,
        description=base_theme.description,
        tokens=merged_tokens,
        variants=merged_variants,
        metadata=base_theme.metadata,
    )


def _merge_tokens(
    base: ThemeTokens,
    manifest_overrides: dict[str, Any],
    sitespec_overrides: dict[str, Any],
) -> ThemeTokens:
    """
    Merge token overrides into base tokens.

    Precedence: sitespec > manifest > base
    """
    # Start with base values
    colors = dict(base.colors)
    shadows = dict(base.shadows)
    spacing = dict(base.spacing)
    radii = dict(base.radii)
    typography = dict(base.typography)
    custom = dict(base.custom)

    # Apply manifest overrides
    if "colors" in manifest_overrides:
        colors.update(manifest_overrides["colors"])
    if "shadows" in manifest_overrides:
        shadows.update(manifest_overrides["shadows"])
    if "spacing" in manifest_overrides:
        spacing.update(manifest_overrides["spacing"])
    if "radii" in manifest_overrides:
        radii.update(manifest_overrides["radii"])
    if "custom" in manifest_overrides:
        custom.update(manifest_overrides["custom"])

    # Apply sitespec overrides (highest precedence)
    if "colors" in sitespec_overrides:
        colors.update(sitespec_overrides["colors"])
    if "shadows" in sitespec_overrides:
        shadows.update(sitespec_overrides["shadows"])
    if "spacing" in sitespec_overrides:
        spacing.update(sitespec_overrides["spacing"])
    if "radii" in sitespec_overrides:
        radii.update(sitespec_overrides["radii"])
    if "custom" in sitespec_overrides:
        custom.update(sitespec_overrides["custom"])

    return ThemeTokens(
        colors=colors,
        shadows=shadows,
        spacing=spacing,
        radii=radii,
        typography=typography,
        custom=custom,
    )


def _merge_variants(
    base_variants: list[VariantSpec],
    manifest_overrides: dict[str, Any],
    sitespec_overrides: dict[str, Any],
) -> list[VariantSpec]:
    """
    Merge variant overrides.

    Currently just returns base variants - variant overrides
    are a future enhancement.
    """
    # For now, just return base variants unchanged
    # Future: support variant-specific overrides like:
    # [theme.variants.dark.colors]
    # sidebar-from = "..."
    return list(base_variants)


def resolve_theme_from_themespec(themespec: ThemeSpecYAML) -> ThemeSpec:
    """Convert a ThemeSpecYAML into a ThemeSpec for the existing CSS pipeline.

    This is the bridge between the declarative themespec.yaml and the
    existing theme/CSS generation system. It generates all tokens from
    the ThemeSpecYAML parameters and assembles them into a ThemeSpec
    that generate_theme_css() can consume directly.

    Args:
        themespec: ThemeSpecYAML from themespec.yaml.

    Returns:
        ThemeSpec ready for CSS generation.
    """
    from dazzle.core.oklch import generate_palette
    from dazzle.core.theme_generators import (
        generate_shape_tokens,
        generate_spacing_scale,
        generate_type_scale,
    )
    from dazzle_ui.specs.theme import TextStyle

    # 1. Generate color palette
    semantic_overrides: dict[str, float] = {}
    if themespec.palette.semantic_overrides:
        so = themespec.palette.semantic_overrides
        if so.success_hue is not None:
            semantic_overrides["success_hue"] = so.success_hue
        if so.warning_hue is not None:
            semantic_overrides["warning_hue"] = so.warning_hue
        if so.danger_hue is not None:
            semantic_overrides["danger_hue"] = so.danger_hue
        if so.info_hue is not None:
            semantic_overrides["info_hue"] = so.info_hue

    # For auto mode, generate light palette (dark variant added below)
    mode = themespec.palette.mode.value if themespec.palette.mode != "auto" else "light"
    colors = generate_palette(
        themespec.palette.brand_hue,
        themespec.palette.brand_chroma,
        mode,
        accent_hue_offset=themespec.palette.accent_hue_offset,
        neutral_chroma=themespec.palette.neutral_chroma,
        semantic_overrides=semantic_overrides or None,
    )

    # 2. Generate type scale
    type_tokens = generate_type_scale(
        themespec.typography.base_size_px,
        themespec.typography.ratio,
        themespec.typography.line_height_body,
        themespec.typography.line_height_heading,
    )

    # Build typography dict for ThemeTokens
    font_stacks = themespec.typography.font_stacks
    typography: dict[str, TextStyle] = {
        "heading": TextStyle(
            font_family=font_stacks.heading,
            font_size=type_tokens.get("text-3xl", "2rem"),
            font_weight="700",
            line_height=str(themespec.typography.line_height_heading),
        ),
        "body": TextStyle(
            font_family=font_stacks.body,
            font_size=type_tokens.get("text-base", "1rem"),
            font_weight="400",
            line_height=str(themespec.typography.line_height_body),
        ),
        "small": TextStyle(
            font_family=font_stacks.body,
            font_size=type_tokens.get("text-sm", "0.875rem"),
            font_weight="400",
            line_height=str(themespec.typography.line_height_body),
        ),
        "mono": TextStyle(
            font_family=font_stacks.mono,
            font_size=type_tokens.get("text-sm", "0.875rem"),
            font_weight="400",
            line_height=str(themespec.typography.line_height_body),
        ),
    }

    # 3. Generate spacing
    spacing_tokens = generate_spacing_scale(
        themespec.spacing.base_unit_px,
        themespec.spacing.density,
    )
    # Convert to int px values for ThemeTokens.spacing
    spacing: dict[str, int] = {}
    for name, value in spacing_tokens.items():
        if value == "0":
            spacing[name] = 0
        elif value.endswith("rem"):
            spacing[name] = round(float(value.replace("rem", "")) * 16)

    # 4. Generate shape tokens
    shape_tokens = generate_shape_tokens(
        themespec.shape.radius_preset,
        themespec.shape.shadow_preset,
        themespec.shape.border_width_px,
    )

    # Split into radii and shadows
    radii: dict[str, int] = {}
    shadows: dict[str, str] = {}
    for name, value in shape_tokens.items():
        if name.startswith("radius-"):
            if value == "0":
                radii[name] = 0
            elif value == "9999px":
                radii[name] = 9999
            elif value.endswith("rem"):
                radii[name] = round(float(value.replace("rem", "")) * 16)
            elif value.endswith("px"):
                radii[name] = int(value.replace("px", ""))
        elif name.startswith("shadow-"):
            shadows[name] = value
        elif name == "border-width":
            radii["border-width"] = int(value.replace("px", ""))

    # Add type scale to custom tokens for full access
    custom: dict[str, Any] = {}
    for name, value in type_tokens.items():
        custom[f"type-scale-{name}"] = value

    # 5. Assemble ThemeTokens
    tokens = ThemeTokens(
        colors=colors,
        spacing=spacing,
        radii=radii,
        typography=typography,
        shadows=shadows,
        custom=custom,
    )

    # 6. Build dark variant if mode is auto or dark
    variants: list[VariantSpec] = []
    if themespec.palette.mode in ("auto", "dark"):
        dark_colors = generate_palette(
            themespec.palette.brand_hue,
            themespec.palette.brand_chroma,
            "dark",
            accent_hue_offset=themespec.palette.accent_hue_offset,
            neutral_chroma=themespec.palette.neutral_chroma,
            semantic_overrides=semantic_overrides or None,
        )
        dark_tokens = ThemeTokens(colors=dark_colors)
        variants.append(
            VariantSpec(
                name="dark",
                description="Dark mode variant (auto-generated from themespec)",
                tokens=dark_tokens,
            )
        )

    return ThemeSpec(
        name="themespec-generated",
        description=f"Generated from themespec (hue={themespec.palette.brand_hue})",
        tokens=tokens,
        variants=variants,
        metadata={"source": "themespec.yaml"},
    )
