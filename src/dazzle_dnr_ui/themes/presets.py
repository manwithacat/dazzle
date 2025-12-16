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
# Corporate Theme
# =============================================================================

CORPORATE_THEME = ThemeSpec(
    name="corporate",
    description="Professional blue/gray palette with refined typography for enterprise applications",
    tokens=ThemeTokens(
        colors={
            # Sidebar - professional navy gradient
            "sidebar-from": "oklch(0.25 0.04 245)",
            "sidebar-to": "oklch(0.22 0.05 240)",
            # Accent glow - subtle blue
            "accent-glow": "oklch(0.55 0.15 240 / 0.12)",
            # Hero section - clean corporate blue
            "hero-bg-from": "oklch(0.35 0.10 240)",
            "hero-bg-to": "oklch(0.45 0.12 235)",
            # Section backgrounds - neutral gray
            "section-alt-bg": "oklch(0.97 0.005 240)",
            # Pricing highlight - corporate blue
            "pricing-highlight-bg": "oklch(0.40 0.12 240)",
            # Feature card accent
            "feature-icon-bg": "oklch(0.94 0.02 240)",
        },
        shadows={
            "sm": "0 1px 2px oklch(0 0 0 / 0.04)",
            "md": "0 4px 6px -1px oklch(0 0 0 / 0.06), 0 2px 4px -2px oklch(0 0 0 / 0.04)",
            "lg": "0 10px 15px -3px oklch(0 0 0 / 0.07), 0 4px 6px -4px oklch(0 0 0 / 0.04)",
            "card": "0 1px 3px oklch(0 0 0 / 0.05), 0 1px 2px -1px oklch(0 0 0 / 0.05)",
            "hero": "0 20px 40px -10px oklch(0 0 0 / 0.20)",
        },
        spacing={
            "section-y": 72,
            "hero-y": 88,
            "card-padding": 28,
            "feature-gap": 28,
        },
        radii={
            "sm": 3,
            "md": 6,
            "lg": 10,
            "card": 10,
            "button": 6,
        },
        typography={
            "hero-headline": TextStyle(
                font_size="3.25rem",
                font_weight="700",
                line_height="1.15",
                letter_spacing="-0.015em",
            ),
            "section-headline": TextStyle(
                font_size="2rem",
                font_weight="600",
                line_height="1.25",
                letter_spacing="-0.01em",
            ),
            "body": TextStyle(
                font_size="1rem",
                font_weight="400",
                line_height="1.65",
            ),
            "subhead": TextStyle(
                font_size="1.125rem",
                font_weight="400",
                line_height="1.55",
            ),
        },
        custom={
            "transition-fast": "120ms ease",
            "transition-normal": "180ms ease",
            "transition-slow": "250ms ease",
        },
    ),
    variants=[
        VariantSpec(
            name="dark",
            description="Dark mode variant",
            tokens=ThemeTokens(
                colors={
                    "sidebar-from": "oklch(0.16 0.03 245)",
                    "sidebar-to": "oklch(0.13 0.04 240)",
                    "accent-glow": "oklch(0.50 0.18 240 / 0.18)",
                    "hero-bg-from": "oklch(0.22 0.08 240)",
                    "hero-bg-to": "oklch(0.28 0.10 235)",
                    "section-alt-bg": "oklch(0.14 0.01 240)",
                    "feature-icon-bg": "oklch(0.22 0.02 240)",
                },
                shadows={
                    "card": "0 1px 3px oklch(0 0 0 / 0.18), 0 1px 2px -1px oklch(0 0 0 / 0.12)",
                },
            ),
        )
    ],
)

# =============================================================================
# Startup Theme
# =============================================================================

STARTUP_THEME = ThemeSpec(
    name="startup",
    description="Bold, modern gradients with vibrant accent colors for dynamic brands",
    tokens=ThemeTokens(
        colors={
            # Sidebar - bold dark with purple undertone
            "sidebar-from": "oklch(0.22 0.04 300)",
            "sidebar-to": "oklch(0.18 0.05 280)",
            # Accent glow - vibrant purple/pink
            "accent-glow": "oklch(0.70 0.25 320 / 0.20)",
            # Hero section - dramatic gradient
            "hero-bg-from": "oklch(0.45 0.22 280)",
            "hero-bg-to": "oklch(0.55 0.25 320)",
            # Section backgrounds - subtle warm
            "section-alt-bg": "oklch(0.98 0.01 300)",
            # Pricing highlight - vibrant
            "pricing-highlight-bg": "oklch(0.50 0.24 300)",
            # Feature card accent
            "feature-icon-bg": "oklch(0.94 0.04 300)",
        },
        shadows={
            "sm": "0 1px 3px oklch(0 0 0 / 0.06)",
            "md": "0 4px 8px -2px oklch(0 0 0 / 0.10), 0 2px 4px -2px oklch(0 0 0 / 0.06)",
            "lg": "0 12px 20px -4px oklch(0 0 0 / 0.12), 0 4px 8px -4px oklch(0 0 0 / 0.06)",
            "card": "0 2px 4px oklch(0 0 0 / 0.08), 0 1px 2px -1px oklch(0 0 0 / 0.06)",
            "hero": "0 30px 60px -15px oklch(0 0 0 / 0.30)",
        },
        spacing={
            "section-y": 88,
            "hero-y": 112,
            "card-padding": 28,
            "feature-gap": 36,
        },
        radii={
            "sm": 6,
            "md": 10,
            "lg": 16,
            "card": 16,
            "button": 10,
        },
        typography={
            "hero-headline": TextStyle(
                font_size="4rem",
                font_weight="800",
                line_height="1.05",
                letter_spacing="-0.025em",
            ),
            "section-headline": TextStyle(
                font_size="2.5rem",
                font_weight="700",
                line_height="1.15",
                letter_spacing="-0.015em",
            ),
            "body": TextStyle(
                font_size="1.0625rem",
                font_weight="400",
                line_height="1.6",
            ),
            "subhead": TextStyle(
                font_size="1.25rem",
                font_weight="500",
                line_height="1.5",
            ),
        },
        custom={
            "transition-fast": "150ms ease-out",
            "transition-normal": "250ms ease-out",
            "transition-slow": "350ms ease-out",
        },
    ),
    variants=[
        VariantSpec(
            name="dark",
            description="Dark mode variant",
            tokens=ThemeTokens(
                colors={
                    "sidebar-from": "oklch(0.14 0.04 300)",
                    "sidebar-to": "oklch(0.11 0.05 280)",
                    "accent-glow": "oklch(0.65 0.28 320 / 0.25)",
                    "hero-bg-from": "oklch(0.28 0.18 280)",
                    "hero-bg-to": "oklch(0.35 0.20 320)",
                    "section-alt-bg": "oklch(0.12 0.01 300)",
                    "feature-icon-bg": "oklch(0.20 0.04 300)",
                },
                shadows={
                    "card": "0 2px 4px oklch(0 0 0 / 0.25), 0 1px 2px -1px oklch(0 0 0 / 0.15)",
                },
            ),
        )
    ],
)

# =============================================================================
# Docs Theme
# =============================================================================

DOCS_THEME = ThemeSpec(
    name="docs",
    description="Documentation-focused theme optimized for readability and code presentation",
    tokens=ThemeTokens(
        colors={
            # Sidebar - clean light gray (docs navigation)
            "sidebar-from": "oklch(0.98 0 0)",
            "sidebar-to": "oklch(0.96 0 0)",
            # Accent glow - subtle blue for links
            "accent-glow": "oklch(0.60 0.12 240 / 0.10)",
            # Hero section - subtle, readable
            "hero-bg-from": "oklch(0.99 0 0)",
            "hero-bg-to": "oklch(0.97 0.01 240)",
            # Section backgrounds - subtle alternation
            "section-alt-bg": "oklch(0.98 0.005 240)",
            # Pricing highlight - docs accent blue
            "pricing-highlight-bg": "oklch(0.55 0.15 240)",
            # Feature card accent - very subtle
            "feature-icon-bg": "oklch(0.96 0.01 240)",
        },
        shadows={
            "sm": "0 1px 2px oklch(0 0 0 / 0.03)",
            "md": "0 2px 4px oklch(0 0 0 / 0.05)",
            "lg": "0 4px 8px oklch(0 0 0 / 0.06)",
            "card": "0 1px 2px oklch(0 0 0 / 0.04), inset 0 0 0 1px oklch(0 0 0 / 0.05)",
            "hero": "none",
        },
        spacing={
            "section-y": 56,
            "hero-y": 64,
            "card-padding": 20,
            "feature-gap": 24,
        },
        radii={
            "sm": 4,
            "md": 6,
            "lg": 8,
            "card": 8,
            "button": 6,
        },
        typography={
            "hero-headline": TextStyle(
                font_size="2.75rem",
                font_weight="600",
                line_height="1.2",
                letter_spacing="-0.01em",
            ),
            "section-headline": TextStyle(
                font_size="1.75rem",
                font_weight="600",
                line_height="1.3",
            ),
            "body": TextStyle(
                font_size="1rem",
                font_weight="400",
                line_height="1.7",  # Optimized for reading
            ),
            "subhead": TextStyle(
                font_size="1.125rem",
                font_weight="400",
                line_height="1.6",
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
                    "sidebar-to": "oklch(0.13 0 0)",
                    "accent-glow": "oklch(0.55 0.15 240 / 0.15)",
                    "hero-bg-from": "oklch(0.13 0 0)",
                    "hero-bg-to": "oklch(0.15 0.01 240)",
                    "section-alt-bg": "oklch(0.14 0.005 240)",
                    "feature-icon-bg": "oklch(0.18 0.01 240)",
                },
                shadows={
                    "card": "0 1px 2px oklch(0 0 0 / 0.15), inset 0 0 0 1px oklch(1 0 0 / 0.05)",
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
    "corporate": CORPORATE_THEME,
    "startup": STARTUP_THEME,
    "docs": DOCS_THEME,
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
