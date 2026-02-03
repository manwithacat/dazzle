"""
Engine variants for layout customization.

Engine variants provide different visual density and spacing configurations
for the same archetype. This allows the same logical layout to be rendered
with different information density levels.

Available variants:
- classic: Default balanced layout (1.0x spacing)
- dense: Higher information density for power users (0.75x spacing)
- comfortable: More whitespace for readability (1.25x spacing)
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EngineVariant(StrEnum):
    """Available engine variants for layout rendering."""

    CLASSIC = "classic"  # Default, balanced spacing
    DENSE = "dense"  # Higher density, less whitespace
    COMFORTABLE = "comfortable"  # More whitespace, larger elements


@dataclass(frozen=True)
class VariantConfig:
    """Configuration for an engine variant.

    All scale values are relative to CLASSIC (1.0).
    """

    name: str
    description: str
    spacing_scale: float  # Multiplier for padding/margins
    font_scale: float  # Multiplier for font sizes
    items_per_row_modifier: int  # Added to base items per row in grids
    border_radius_scale: float  # Multiplier for border radius
    min_element_height: str  # CSS value for minimum element height
    tailwind_classes: dict[str, str]  # Tailwind overrides by context


# Variant configurations
CLASSIC_CONFIG = VariantConfig(
    name="classic",
    description="Balanced layout with standard spacing",
    spacing_scale=1.0,
    font_scale=1.0,
    items_per_row_modifier=0,
    border_radius_scale=1.0,
    min_element_height="auto",
    tailwind_classes={
        "container": "p-4 sm:p-6",
        "card": "p-4 sm:p-6 rounded-lg",
        "grid": "gap-4 sm:gap-6",
        "text_sm": "text-sm",
        "text_base": "text-base",
        "text_lg": "text-lg",
        "heading": "text-2xl font-bold",
    },
)

DENSE_CONFIG = VariantConfig(
    name="dense",
    description="Higher density for power users and experts",
    spacing_scale=0.75,
    font_scale=0.9,
    items_per_row_modifier=1,  # One more column
    border_radius_scale=0.75,
    min_element_height="2rem",
    tailwind_classes={
        "container": "p-2 sm:p-3",
        "card": "p-2 sm:p-3 rounded",
        "grid": "gap-2 sm:gap-3",
        "text_sm": "text-xs",
        "text_base": "text-sm",
        "text_lg": "text-base",
        "heading": "text-xl font-semibold",
    },
)

COMFORTABLE_CONFIG = VariantConfig(
    name="comfortable",
    description="More whitespace for readability and casual use",
    spacing_scale=1.25,
    font_scale=1.1,
    items_per_row_modifier=-1,  # One fewer column
    border_radius_scale=1.25,
    min_element_height="4rem",
    tailwind_classes={
        "container": "p-6 sm:p-8",
        "card": "p-6 sm:p-8 rounded-xl",
        "grid": "gap-6 sm:gap-8",
        "text_sm": "text-base",
        "text_base": "text-lg",
        "text_lg": "text-xl",
        "heading": "text-3xl font-bold",
    },
)


# Variant lookup
VARIANT_CONFIGS: dict[EngineVariant, VariantConfig] = {
    EngineVariant.CLASSIC: CLASSIC_CONFIG,
    EngineVariant.DENSE: DENSE_CONFIG,
    EngineVariant.COMFORTABLE: COMFORTABLE_CONFIG,
}


def get_variant_config(variant: EngineVariant | str) -> VariantConfig:
    """Get configuration for a variant.

    Args:
        variant: Variant enum or string name

    Returns:
        VariantConfig for the specified variant

    Examples:
        >>> config = get_variant_config(EngineVariant.DENSE)
        >>> config.spacing_scale
        0.75

        >>> config = get_variant_config("comfortable")
        >>> config.font_scale
        1.1
    """
    if isinstance(variant, str):
        try:
            variant = EngineVariant(variant.lower())
        except ValueError:
            # Default to classic for unknown variants
            variant = EngineVariant.CLASSIC

    return VARIANT_CONFIGS.get(variant, CLASSIC_CONFIG)


def get_variant_for_persona(
    proficiency_level: str | None,
    session_style: str | None,
) -> EngineVariant:
    """Suggest a variant based on persona characteristics.

    Args:
        proficiency_level: "novice", "intermediate", or "expert"
        session_style: "glance" or "deep_work"

    Returns:
        Suggested EngineVariant

    Examples:
        >>> get_variant_for_persona("expert", "deep_work")
        <EngineVariant.DENSE: 'dense'>

        >>> get_variant_for_persona("novice", "glance")
        <EngineVariant.COMFORTABLE: 'comfortable'>
    """
    # Experts doing deep work prefer dense layouts
    if proficiency_level == "expert" and session_style == "deep_work":
        return EngineVariant.DENSE

    # Novices or glancers prefer comfortable layouts
    if proficiency_level == "novice" or session_style == "glance":
        return EngineVariant.COMFORTABLE

    # Default to classic
    return EngineVariant.CLASSIC


def get_grid_columns(
    base_columns: int,
    variant: EngineVariant,
    breakpoint: str = "default",
) -> int:
    """Calculate grid columns for a variant.

    Args:
        base_columns: Number of columns in CLASSIC variant
        variant: Engine variant
        breakpoint: CSS breakpoint ("default", "sm", "md", "lg", "xl")

    Returns:
        Adjusted number of columns

    Examples:
        >>> get_grid_columns(3, EngineVariant.DENSE)
        4

        >>> get_grid_columns(3, EngineVariant.COMFORTABLE)
        2
    """
    config = get_variant_config(variant)
    adjusted = base_columns + config.items_per_row_modifier

    # Apply breakpoint-specific limits
    min_columns = 1
    max_columns = {
        "default": 2,
        "sm": 3,
        "md": 4,
        "lg": 6,
        "xl": 8,
    }.get(breakpoint, 4)

    return max(min_columns, min(adjusted, max_columns))


def apply_variant_to_style(
    base_style: dict[str, Any],
    variant: EngineVariant,
) -> dict[str, Any]:
    """Apply variant scaling to a style dictionary.

    Args:
        base_style: Base CSS-like style dictionary
        variant: Engine variant

    Returns:
        Style dictionary with variant scaling applied
    """
    config = get_variant_config(variant)
    result = base_style.copy()

    # Scale spacing values
    spacing_keys = ["padding", "margin", "gap"]
    for key in spacing_keys:
        if key in result:
            # Try to scale numeric values
            value = result[key]
            if isinstance(value, int | float):
                result[key] = value * config.spacing_scale
            elif isinstance(value, str) and value.endswith("rem"):
                try:
                    num = float(value[:-3])
                    result[key] = f"{num * config.spacing_scale}rem"
                except ValueError:
                    pass

    # Scale font sizes
    if "fontSize" in result:
        value = result["fontSize"]
        if isinstance(value, int | float):
            result["fontSize"] = value * config.font_scale

    return result


__all__ = [
    "EngineVariant",
    "VariantConfig",
    "VARIANT_CONFIGS",
    "get_variant_config",
    "get_variant_for_persona",
    "get_grid_columns",
    "apply_variant_to_style",
    "CLASSIC_CONFIG",
    "DENSE_CONFIG",
    "COMFORTABLE_CONFIG",
]
