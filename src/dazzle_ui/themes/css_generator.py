"""
CSS generator for DAZZLE themes.

Generates CSS custom properties from ThemeSpec tokens, including
support for dark mode variants via [data-theme="dark"] selectors.
"""

from __future__ import annotations

from dazzle_ui.specs.theme import ThemeSpec, ThemeTokens


def generate_theme_css(theme: ThemeSpec) -> str:
    """
    Generate CSS from a ThemeSpec.

    Produces CSS custom properties for all tokens in the theme,
    including variant overrides for dark mode.

    Args:
        theme: Theme specification with tokens and variants

    Returns:
        CSS string with :root and variant selectors
    """
    lines: list[str] = []

    # Header comment
    lines.append(f"/* DAZZLE Theme: {theme.name} */")
    lines.append(f"/* {theme.description or 'No description'} */")
    lines.append("/* Auto-generated - do not edit */")
    lines.append("")

    # Base :root tokens
    lines.append(":root {")
    lines.extend(_generate_token_lines(theme.tokens, indent=2))
    lines.append("}")
    lines.append("")

    # Variant overrides
    for variant in theme.variants:
        selector = _variant_selector(variant.name)
        lines.append(f"{selector} {{")
        lines.extend(_generate_token_lines(variant.tokens, indent=2))
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def _generate_token_lines(tokens: ThemeTokens, indent: int = 0) -> list[str]:
    """
    Generate CSS custom property lines from ThemeTokens.

    Args:
        tokens: Token collection
        indent: Number of spaces for indentation

    Returns:
        List of CSS property lines
    """
    lines: list[str] = []
    prefix = " " * indent

    # Colors
    for name, value in tokens.colors.items():
        lines.append(f"{prefix}--dz-{name}: {value};")

    # Shadows
    for name, value in tokens.shadows.items():
        lines.append(f"{prefix}--dz-shadow-{name}: {value};")

    # Spacing (convert to rem)
    for spacing_name, spacing_value in tokens.spacing.items():
        # Convert px to rem (assuming 16px base)
        rem_value = spacing_value / 16
        lines.append(f"{prefix}--dz-spacing-{spacing_name}: {rem_value}rem;")

    # Radii (convert to rem)
    for radius_name, radius_value in tokens.radii.items():
        rem_value = radius_value / 16
        lines.append(f"{prefix}--dz-radius-{radius_name}: {rem_value}rem;")

    # Typography
    for name, style in tokens.typography.items():
        if style.font_size:
            lines.append(f"{prefix}--dz-font-size-{name}: {style.font_size};")
        if style.font_weight:
            lines.append(f"{prefix}--dz-font-weight-{name}: {style.font_weight};")
        if style.line_height:
            lines.append(f"{prefix}--dz-line-height-{name}: {style.line_height};")
        if style.letter_spacing:
            lines.append(f"{prefix}--dz-letter-spacing-{name}: {style.letter_spacing};")

    # Custom tokens
    for name, value in tokens.custom.items():
        lines.append(f"{prefix}--dz-{name}: {value};")

    return lines


def _variant_selector(variant_name: str) -> str:
    """
    Get CSS selector for a variant.

    Args:
        variant_name: Variant name (e.g., "dark")

    Returns:
        CSS selector string
    """
    if variant_name == "dark":
        return '[data-theme="dark"]'
    elif variant_name == "light":
        return '[data-theme="light"]'
    else:
        return f'[data-theme="{variant_name}"]'
