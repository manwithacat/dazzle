"""
Unit tests for DAZZLE theme presets.

Tests the theme system including presets, CSS generation, and resolution.
"""

import pytest

from dazzle_ui.themes import (
    CORPORATE_THEME,
    DOCS_THEME,
    MINIMAL_THEME,
    SAAS_DEFAULT_THEME,
    STARTUP_THEME,
    generate_theme_css,
    get_theme_preset,
    list_theme_presets,
    resolve_theme,
)


class TestThemePresets:
    """Tests for theme preset definitions."""

    def test_list_theme_presets(self):
        """Test listing available theme presets."""
        presets = list_theme_presets()
        assert len(presets) == 5
        assert "saas-default" in presets
        assert "minimal" in presets
        assert "corporate" in presets
        assert "startup" in presets
        assert "docs" in presets

    def test_get_theme_preset_saas_default(self):
        """Test getting saas-default preset."""
        theme = get_theme_preset("saas-default")
        assert theme is not None
        assert theme.name == "saas-default"
        assert theme is SAAS_DEFAULT_THEME

    def test_get_theme_preset_minimal(self):
        """Test getting minimal preset."""
        theme = get_theme_preset("minimal")
        assert theme is not None
        assert theme.name == "minimal"
        assert theme is MINIMAL_THEME

    def test_get_theme_preset_corporate(self):
        """Test getting corporate preset."""
        theme = get_theme_preset("corporate")
        assert theme is not None
        assert theme.name == "corporate"
        assert theme is CORPORATE_THEME

    def test_get_theme_preset_startup(self):
        """Test getting startup preset."""
        theme = get_theme_preset("startup")
        assert theme is not None
        assert theme.name == "startup"
        assert theme is STARTUP_THEME

    def test_get_theme_preset_docs(self):
        """Test getting docs preset."""
        theme = get_theme_preset("docs")
        assert theme is not None
        assert theme.name == "docs"
        assert theme is DOCS_THEME

    def test_get_theme_preset_unknown(self):
        """Test getting unknown preset returns None."""
        theme = get_theme_preset("nonexistent")
        assert theme is None


class TestThemeStructure:
    """Tests for theme structure and tokens."""

    @pytest.mark.parametrize("theme_name", list_theme_presets())
    def test_theme_has_required_tokens(self, theme_name):
        """Test that all themes have required token categories."""
        theme = get_theme_preset(theme_name)
        assert theme is not None

        # Check required color tokens
        assert "sidebar-from" in theme.tokens.colors
        assert "sidebar-to" in theme.tokens.colors
        assert "hero-bg-from" in theme.tokens.colors
        assert "hero-bg-to" in theme.tokens.colors
        assert "section-alt-bg" in theme.tokens.colors

        # Check required shadow tokens
        assert "sm" in theme.tokens.shadows
        assert "md" in theme.tokens.shadows
        assert "lg" in theme.tokens.shadows
        assert "card" in theme.tokens.shadows
        assert "hero" in theme.tokens.shadows

        # Check required spacing tokens
        assert "section-y" in theme.tokens.spacing
        assert "hero-y" in theme.tokens.spacing
        assert "card-padding" in theme.tokens.spacing

        # Check required radii tokens
        assert "sm" in theme.tokens.radii
        assert "md" in theme.tokens.radii
        assert "lg" in theme.tokens.radii
        assert "card" in theme.tokens.radii

        # Check required typography tokens
        assert "hero-headline" in theme.tokens.typography
        assert "section-headline" in theme.tokens.typography
        assert "body" in theme.tokens.typography

    @pytest.mark.parametrize("theme_name", list_theme_presets())
    def test_theme_has_dark_variant(self, theme_name):
        """Test that all themes have a dark mode variant."""
        theme = get_theme_preset(theme_name)
        assert theme is not None

        dark_variant = theme.get_variant("dark")
        assert dark_variant is not None
        assert dark_variant.name == "dark"

        # Dark variant should override key colors
        assert "sidebar-from" in dark_variant.tokens.colors
        assert "hero-bg-from" in dark_variant.tokens.colors

    @pytest.mark.parametrize("theme_name", list_theme_presets())
    def test_theme_has_description(self, theme_name):
        """Test that all themes have a description."""
        theme = get_theme_preset(theme_name)
        assert theme is not None
        assert theme.description is not None
        assert len(theme.description) > 10


class TestThemeCSSGeneration:
    """Tests for CSS generation from themes."""

    @pytest.mark.parametrize("theme_name", list_theme_presets())
    def test_generate_css_for_preset(self, theme_name):
        """Test CSS generation for each preset."""
        theme = get_theme_preset(theme_name)
        assert theme is not None

        css = generate_theme_css(theme)
        assert isinstance(css, str)
        assert len(css) > 0

        # Check for header comment
        assert f"/* DAZZLE Theme: {theme_name} */" in css

        # Check for :root selector
        assert ":root {" in css

        # Check for custom properties
        assert "--dz-sidebar-from:" in css
        assert "--dz-shadow-card:" in css
        assert "--dz-spacing-section-y:" in css
        assert "--dz-radius-card:" in css

    @pytest.mark.parametrize("theme_name", list_theme_presets())
    def test_generate_css_includes_dark_variant(self, theme_name):
        """Test that CSS includes dark mode variant."""
        theme = get_theme_preset(theme_name)
        assert theme is not None

        css = generate_theme_css(theme)

        # Check for dark mode selector
        assert '[data-theme="dark"]' in css


class TestThemeResolution:
    """Tests for theme resolution with overrides."""

    def test_resolve_theme_no_overrides(self):
        """Test resolving theme without overrides."""
        theme = resolve_theme("corporate")
        assert theme.name == "corporate"
        assert theme.tokens.colors == CORPORATE_THEME.tokens.colors

    def test_resolve_theme_with_manifest_overrides(self):
        """Test resolving theme with manifest overrides."""
        theme = resolve_theme(
            preset_name="minimal",
            manifest_overrides={"colors": {"hero-bg-from": "oklch(0.50 0.18 280)"}},
        )
        assert theme.tokens.colors["hero-bg-from"] == "oklch(0.50 0.18 280)"
        # Other colors should remain from base
        assert theme.tokens.colors["sidebar-from"] == MINIMAL_THEME.tokens.colors["sidebar-from"]

    def test_resolve_theme_with_sitespec_overrides(self):
        """Test resolving theme with sitespec overrides (highest precedence)."""
        theme = resolve_theme(
            preset_name="startup",
            manifest_overrides={"colors": {"hero-bg-from": "from-manifest"}},
            sitespec_overrides={"colors": {"hero-bg-from": "from-sitespec"}},
        )
        # Sitespec should win
        assert theme.tokens.colors["hero-bg-from"] == "from-sitespec"

    def test_resolve_theme_unknown_preset_fallback(self):
        """Test that unknown preset falls back to saas-default."""
        theme = resolve_theme("nonexistent-theme")
        assert theme.name == "saas-default"


class TestThemeCharacteristics:
    """Tests for specific theme characteristics."""

    def test_corporate_theme_is_professional(self):
        """Test corporate theme has professional characteristics."""
        theme = CORPORATE_THEME

        # Corporate should use blue hues (hue around 240)
        assert "240" in theme.tokens.colors["hero-bg-from"]

        # Smaller radii than startup (more conservative)
        assert theme.tokens.radii["card"] < STARTUP_THEME.tokens.radii["card"]

    def test_startup_theme_is_bold(self):
        """Test startup theme has bold characteristics."""
        theme = STARTUP_THEME

        # Larger typography
        assert "4rem" in theme.tokens.typography["hero-headline"].font_size

        # Larger border radii
        assert theme.tokens.radii["card"] >= 16

        # More dramatic shadows
        assert "30px" in theme.tokens.shadows["hero"]

    def test_docs_theme_is_readable(self):
        """Test docs theme is optimized for readability."""
        theme = DOCS_THEME

        # Higher line height for body text
        assert theme.tokens.typography["body"].line_height == "1.7"

        # Minimal hero shadow (clean look)
        assert theme.tokens.shadows["hero"] == "none"

        # Light sidebar (docs navigation)
        assert "0.98" in theme.tokens.colors["sidebar-from"]

    def test_minimal_theme_is_subtle(self):
        """Test minimal theme has subtle characteristics."""
        theme = MINIMAL_THEME

        # No accent glow
        assert theme.tokens.colors["accent-glow"] == "transparent"

        # Subtle shadows
        assert "0.03" in theme.tokens.shadows["sm"]

        # Smaller radii
        assert theme.tokens.radii["sm"] == 2
