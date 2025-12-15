"""
Theme presets for DAZZLE.

Defines predefined theme configurations that can be selected in dazzle.toml
or sitespec.yaml. Each preset is a ThemeSpec instance with complete token
definitions for colors, shadows, spacing, and typography.
"""

from __future__ import annotations

from dazzle_dnr_ui.specs.theme import TextStyle, ThemeSpec, ThemeTokens, VariantSpec

# =============================================================================
# SaaS Default Theme
# =============================================================================

SAAS_DEFAULT_THEME = ThemeSpec(
    name="saas-default",
    description="Modern SaaS styling with gradient sidebars, refined shadows, and accent highlights",
    tokens=ThemeTokens(
        colors={
            # Sidebar gradient
            "sidebar-from": "oklch(0.25 0.02 260)",
            "sidebar-to": "oklch(0.20 0.03 250)",
            # Accent glow for interactive elements
            "accent-glow": "oklch(0.65 0.20 250 / 0.15)",
            # Hero section backgrounds
            "hero-bg-from": "oklch(0.40 0.15 270)",
            "hero-bg-to": "oklch(0.55 0.18 290)",
            # Section backgrounds
            "section-alt-bg": "oklch(0.97 0.01 260)",
            # Pricing highlight
            "pricing-highlight-bg": "oklch(0.45 0.18 270)",
            # Feature card accent
            "feature-icon-bg": "oklch(0.92 0.03 260)",
        },
        shadows={
            "sm": "0 1px 2px oklch(0 0 0 / 0.05)",
            "md": "0 4px 6px -1px oklch(0 0 0 / 0.07), 0 2px 4px -2px oklch(0 0 0 / 0.05)",
            "lg": "0 10px 15px -3px oklch(0 0 0 / 0.08), 0 4px 6px -4px oklch(0 0 0 / 0.05)",
            "card": "0 1px 3px oklch(0 0 0 / 0.06), 0 1px 2px -1px oklch(0 0 0 / 0.06)",
            "hero": "0 25px 50px -12px oklch(0 0 0 / 0.25)",
        },
        spacing={
            "section-y": 80,
            "hero-y": 100,
            "card-padding": 24,
            "feature-gap": 32,
        },
        radii={
            "sm": 4,
            "md": 8,
            "lg": 12,
            "card": 12,
            "button": 8,
        },
        typography={
            "hero-headline": TextStyle(
                font_size="3.5rem",
                font_weight="800",
                line_height="1.1",
                letter_spacing="-0.02em",
            ),
            "section-headline": TextStyle(
                font_size="2.25rem",
                font_weight="700",
                line_height="1.2",
                letter_spacing="-0.01em",
            ),
            "body": TextStyle(
                font_size="1rem",
                font_weight="400",
                line_height="1.6",
            ),
            "subhead": TextStyle(
                font_size="1.25rem",
                font_weight="400",
                line_height="1.5",
            ),
        },
        custom={
            "transition-fast": "150ms ease",
            "transition-normal": "200ms ease",
            "transition-slow": "300ms ease",
        },
    ),
    variants=[
        VariantSpec(
            name="dark",
            description="Dark mode variant",
            tokens=ThemeTokens(
                colors={
                    "sidebar-from": "oklch(0.18 0.02 260)",
                    "sidebar-to": "oklch(0.14 0.025 255)",
                    "accent-glow": "oklch(0.60 0.22 250 / 0.20)",
                    "hero-bg-from": "oklch(0.25 0.12 270)",
                    "hero-bg-to": "oklch(0.35 0.15 290)",
                    "section-alt-bg": "oklch(0.15 0.01 260)",
                    "feature-icon-bg": "oklch(0.25 0.03 260)",
                },
                shadows={
                    "card": "0 1px 3px oklch(0 0 0 / 0.2), 0 1px 2px -1px oklch(0 0 0 / 0.15)",
                },
            ),
        )
    ],
)

# =============================================================================
# Minimal Theme
# =============================================================================

MINIMAL_THEME = ThemeSpec(
    name="minimal",
    description="Clean, minimal styling with subtle shadows and reduced visual weight",
    tokens=ThemeTokens(
        colors={
            # Sidebar - light solid color, no gradient
            "sidebar-from": "oklch(0.97 0 0)",
            "sidebar-to": "oklch(0.97 0 0)",
            # No accent glow
            "accent-glow": "transparent",
            # Hero - subtle gradient
            "hero-bg-from": "oklch(0.98 0.01 260)",
            "hero-bg-to": "oklch(0.96 0.02 260)",
            # Section backgrounds
            "section-alt-bg": "oklch(0.98 0 0)",
            # Pricing highlight - subtle
            "pricing-highlight-bg": "oklch(0.96 0.02 260)",
            # Feature card accent
            "feature-icon-bg": "oklch(0.95 0 0)",
        },
        shadows={
            "sm": "0 1px 2px oklch(0 0 0 / 0.03)",
            "md": "0 2px 4px oklch(0 0 0 / 0.04)",
            "lg": "0 4px 8px oklch(0 0 0 / 0.05)",
            "card": "0 1px 2px oklch(0 0 0 / 0.04)",
            "hero": "none",
        },
        spacing={
            "section-y": 64,
            "hero-y": 80,
            "card-padding": 20,
            "feature-gap": 24,
        },
        radii={
            "sm": 2,
            "md": 4,
            "lg": 8,
            "card": 8,
            "button": 4,
        },
        typography={
            "hero-headline": TextStyle(
                font_size="3rem",
                font_weight="700",
                line_height="1.15",
                letter_spacing="-0.01em",
            ),
            "section-headline": TextStyle(
                font_size="2rem",
                font_weight="600",
                line_height="1.25",
            ),
            "body": TextStyle(
                font_size="1rem",
                font_weight="400",
                line_height="1.6",
            ),
            "subhead": TextStyle(
                font_size="1.125rem",
                font_weight="400",
                line_height="1.5",
            ),
        },
        custom={
            "transition-fast": "100ms ease",
            "transition-normal": "150ms ease",
            "transition-slow": "200ms ease",
        },
    ),
    variants=[
        VariantSpec(
            name="dark",
            description="Dark mode variant",
            tokens=ThemeTokens(
                colors={
                    "sidebar-from": "oklch(0.15 0 0)",
                    "sidebar-to": "oklch(0.15 0 0)",
                    "hero-bg-from": "oklch(0.12 0.01 260)",
                    "hero-bg-to": "oklch(0.14 0.02 260)",
                    "section-alt-bg": "oklch(0.12 0 0)",
                    "feature-icon-bg": "oklch(0.18 0 0)",
                },
                shadows={
                    "card": "0 1px 2px oklch(0 0 0 / 0.15)",
                },
            ),
        )
    ],
)

# =============================================================================
# Theme Registry
# =============================================================================

_THEME_PRESETS: dict[str, ThemeSpec] = {
    "saas-default": SAAS_DEFAULT_THEME,
    "minimal": MINIMAL_THEME,
}


def get_theme_preset(name: str) -> ThemeSpec | None:
    """
    Get a theme preset by name.

    Args:
        name: Theme preset name ("saas-default", "minimal")

    Returns:
        ThemeSpec if found, None otherwise
    """
    return _THEME_PRESETS.get(name)


def list_theme_presets() -> list[str]:
    """
    List available theme preset names.

    Returns:
        List of preset names
    """
    return list(_THEME_PRESETS.keys())
