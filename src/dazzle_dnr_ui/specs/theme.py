"""
Theme specification types for UISpec.

Defines themes, variants, and design tokens.
"""

from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Typography
# =============================================================================


class TextStyle(BaseModel):
    """
    Text style specification.

    Example:
        TextStyle(
            font_family="Inter, sans-serif",
            font_size="16px",
            font_weight="400",
            line_height="1.5"
        )
    """

    font_family: str | None = Field(default=None, description="Font family")
    font_size: str | None = Field(default=None, description="Font size (px, rem, em)")
    font_weight: str | None = Field(default=None, description="Font weight")
    line_height: str | None = Field(default=None, description="Line height")
    letter_spacing: str | None = Field(default=None, description="Letter spacing")
    text_transform: str | None = Field(
        default=None, description="Text transform (uppercase, lowercase, etc.)"
    )

    class Config:
        frozen = True


# =============================================================================
# Theme Tokens
# =============================================================================


class ThemeTokens(BaseModel):
    """
    Design tokens for theming.

    Example:
        ThemeTokens(
            colors={
                "primary": "#0066cc",
                "secondary": "#6c757d",
                "background": "#ffffff",
                "text": "#212529",
            },
            spacing={
                "xs": 4,
                "sm": 8,
                "md": 16,
                "lg": 24,
                "xl": 32,
            },
            radii={
                "sm": 2,
                "md": 4,
                "lg": 8,
            },
            typography={
                "heading1": TextStyle(font_size="32px", font_weight="700"),
                "body": TextStyle(font_size="16px", font_weight="400"),
            }
        )
    """

    colors: dict[str, str] = Field(
        default_factory=dict, description="Color tokens (name -> hex/rgb)"
    )
    spacing: dict[str, int] = Field(
        default_factory=dict, description="Spacing tokens (name -> pixels)"
    )
    radii: dict[str, int] = Field(
        default_factory=dict, description="Border radius tokens (name -> pixels)"
    )
    typography: dict[str, TextStyle] = Field(
        default_factory=dict, description="Typography tokens (name -> style)"
    )
    shadows: dict[str, str] = Field(
        default_factory=dict, description="Shadow tokens (name -> CSS shadow)"
    )
    custom: dict[str, Any] = Field(
        default_factory=dict, description="Custom tokens"
    )

    class Config:
        frozen = True


# =============================================================================
# Variants
# =============================================================================


class VariantSpec(BaseModel):
    """
    Theme variant specification.

    Variants allow theming adjustments for specific contexts (dark mode, high contrast, etc.).

    Example:
        VariantSpec(
            name="dark",
            applies_to="*",
            tokens=ThemeTokens(
                colors={
                    "background": "#1a1a1a",
                    "text": "#ffffff",
                }
            )
        )
    """

    name: str = Field(description="Variant name (e.g., 'dark', 'compact')")
    description: str | None = Field(default=None, description="Variant description")
    applies_to: str = Field(
        default="*", description="Selector or '*' for global application"
    )
    tokens: ThemeTokens = Field(description="Token overrides for this variant")

    class Config:
        frozen = True


# =============================================================================
# Themes
# =============================================================================


class ThemeSpec(BaseModel):
    """
    Theme specification.

    A theme defines the visual design system for the UI.

    Example:
        ThemeSpec(
            name="default",
            tokens=ThemeTokens(
                colors={"primary": "#0066cc", "background": "#ffffff"},
                spacing={"sm": 8, "md": 16, "lg": 24},
                radii={"sm": 2, "md": 4, "lg": 8},
                typography={
                    "heading1": TextStyle(font_size="32px", font_weight="700"),
                    "body": TextStyle(font_size="16px", font_weight="400"),
                }
            ),
            variants=[
                VariantSpec(
                    name="dark",
                    tokens=ThemeTokens(
                        colors={"background": "#1a1a1a", "text": "#ffffff"}
                    )
                )
            ]
        )
    """

    name: str = Field(description="Theme name")
    description: str | None = Field(default=None, description="Theme description")
    tokens: ThemeTokens = Field(description="Base design tokens")
    variants: list[VariantSpec] = Field(
        default_factory=list, description="Theme variants"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    class Config:
        frozen = True

    def get_variant(self, name: str) -> VariantSpec | None:
        """Get variant by name."""
        for variant in self.variants:
            if variant.name == name:
                return variant
        return None
