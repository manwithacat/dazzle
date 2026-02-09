"""
W3C Design Token Community Group (DTCG) tokens.json export.

Generates a DTCG-compliant tokens.json file from a ThemeSpecYAML.
See: https://design-tokens.github.io/community-group/format/
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ir.themespec import ThemeSpecYAML
from .oklch import generate_palette
from .theme_generators import (
    generate_shape_tokens,
    generate_spacing_scale,
    generate_type_scale,
)


def generate_dtcg_tokens(themespec: ThemeSpecYAML) -> dict[str, Any]:
    """Generate W3C DTCG format design tokens from a ThemeSpecYAML.

    Groups tokens into: color, dimension, fontFamily, fontSize, shadow.

    Args:
        themespec: ThemeSpecYAML configuration.

    Returns:
        DTCG-formatted dict suitable for writing as tokens.json.
    """
    # Generate raw tokens
    semantic_overrides = {}
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

    palette = generate_palette(
        themespec.palette.brand_hue,
        themespec.palette.brand_chroma,
        themespec.palette.mode.value if themespec.palette.mode != "auto" else "light",
        accent_hue_offset=themespec.palette.accent_hue_offset,
        neutral_chroma=themespec.palette.neutral_chroma,
        semantic_overrides=semantic_overrides or None,
    )

    type_scale = generate_type_scale(
        themespec.typography.base_size_px,
        themespec.typography.ratio,
        themespec.typography.line_height_body,
        themespec.typography.line_height_heading,
    )

    spacing = generate_spacing_scale(
        themespec.spacing.base_unit_px,
        themespec.spacing.density,
    )

    shape = generate_shape_tokens(
        themespec.shape.radius_preset,
        themespec.shape.shadow_preset,
        themespec.shape.border_width_px,
    )

    # Build DTCG structure
    dtcg: dict[str, Any] = {}

    # Color group
    color_group: dict[str, Any] = {}
    for name, value in palette.items():
        # Nest by prefix (primary-50 -> primary.50)
        parts = name.split("-", 1)
        if len(parts) == 2:
            prefix, suffix = parts
            if prefix not in color_group:
                color_group[prefix] = {}
            color_group[prefix][suffix] = {"$type": "color", "$value": value}
        else:
            color_group[name] = {"$type": "color", "$value": value}
    dtcg["color"] = color_group

    # Font size group (from type scale, excluding line heights)
    font_size_group: dict[str, Any] = {}
    for name, value in type_scale.items():
        if name.endswith("-lh"):
            continue
        font_size_group[name] = {"$type": "fontSize", "$value": value}
    dtcg["fontSize"] = font_size_group

    # Font family group
    font_stacks = themespec.typography.font_stacks
    dtcg["fontFamily"] = {
        "heading": {"$type": "fontFamily", "$value": font_stacks.heading},
        "body": {"$type": "fontFamily", "$value": font_stacks.body},
        "mono": {"$type": "fontFamily", "$value": font_stacks.mono},
    }

    # Dimension group (spacing + radii)
    dimension_group: dict[str, Any] = {}
    for name, value in spacing.items():
        dimension_group[name] = {"$type": "dimension", "$value": value}
    for name, value in shape.items():
        if name.startswith("radius-") or name == "border-width":
            dimension_group[name] = {"$type": "dimension", "$value": value}
    dtcg["dimension"] = dimension_group

    # Shadow group
    shadow_group: dict[str, Any] = {}
    for name, value in shape.items():
        if name.startswith("shadow-"):
            shadow_group[name] = {"$type": "shadow", "$value": value}
    dtcg["shadow"] = shadow_group

    return dtcg


def export_dtcg_file(themespec: ThemeSpecYAML, output_path: Path) -> Path:
    """Generate DTCG tokens and write to a JSON file.

    Args:
        themespec: ThemeSpecYAML configuration.
        output_path: Path to write tokens.json.

    Returns:
        Path to the written file.
    """
    tokens = generate_dtcg_tokens(themespec)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(tokens, indent=2),
        encoding="utf-8",
    )

    return output_path
