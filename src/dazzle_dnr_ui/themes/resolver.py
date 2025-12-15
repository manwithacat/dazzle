"""
Theme resolver for DAZZLE.

Resolves the final theme by merging:
1. Base preset (from theme name/kind)
2. Manifest custom tokens
3. SiteSpec theme overrides (highest precedence)
"""

from __future__ import annotations

from typing import Any

from dazzle_dnr_ui.specs.theme import ThemeSpec, ThemeTokens, VariantSpec

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
