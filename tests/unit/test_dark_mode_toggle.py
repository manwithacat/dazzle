"""
Unit tests for DAZZLE dark mode toggle (v0.16.0 - Issue #26).

Tests for site page dark mode toggle functionality.
"""

from pathlib import Path

import pytest


class TestDarkModeCSSClasses:
    """Tests for dark mode CSS classes in site-sections.css."""

    def test_dark_mode_toggle_button_styles(self):
        """Test that toggle button CSS classes are defined."""
        from pathlib import Path

        css_path = Path("src/dazzle/page/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        # Check toggle button styles exist
        assert ".dz-theme-toggle" in css_content
        assert ".dz-theme-toggle:hover" in css_content
        assert ".dz-theme-toggle__icon" in css_content
        assert ".dz-theme-toggle__sun" in css_content
        assert ".dz-theme-toggle__moon" in css_content

    def test_dark_mode_site_header_styles(self):
        """Test that dark mode header styles are defined via token overrides."""
        from pathlib import Path

        # Header/logo/nav dark mode is now handled by token overrides
        # in design-system.css rather than explicit selectors in site-sections.css
        ds_path = Path("packages/hatchi-maxchi/base/design-system.css")
        ds_content = ds_path.read_text()

        assert "--dz-header-bg:" in ds_content
        assert "--dz-logo-color:" in ds_content
        assert "--dz-text-body:" in ds_content

        # Base rules in site-sections.css consume these tokens
        css_path = Path("src/dazzle/page/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        assert "var(--dz-header-bg)" in css_content
        assert "var(--dz-logo-color)" in css_content
        assert "var(--dz-text-body)" in css_content

    def test_dark_mode_section_styles(self):
        """Test that dark mode section styles are defined."""
        from pathlib import Path

        css_path = Path("src/dazzle/page/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        # Check dark mode section styles
        assert '[data-theme="dark"] .dz-section-features' in css_content
        assert '[data-theme="dark"] .dz-section-pricing' in css_content
        assert '[data-theme="dark"] .dz-section-faq' in css_content
        assert '[data-theme="dark"] .dz-section-testimonials' in css_content

    def test_dark_mode_card_styles(self):
        """Test that dark mode card styles are defined."""
        from pathlib import Path

        css_path = Path("src/dazzle/page/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        # Check dark mode card styles (flat classes, not BEM)
        assert '[data-theme="dark"] .dz-feature-item' in css_content
        assert '[data-theme="dark"] .dz-testimonial-item' in css_content


class TestSitePageToggleButton:
    """Tests for toggle button in site pages."""

    @pytest.mark.parametrize(
        "path,tokens",
        [
            (
                "src/dazzle/http/runtime/site_routes.py",
                ["dz-theme-toggle", "Toggle dark mode"],
            ),
            (
                "src/dazzle/http/runtime/site_routes.py",
                ["dz-theme-toggle__sun", "dz-theme-toggle__moon"],
            ),
            (
                "src/dazzle/page/static/js/site.js",
                ["initTheme()", "toggleTheme()"],
            ),
            (
                "src/dazzle/page/static/js/site.js",
                ["prefers-color-scheme", "addEventListener"],
            ),
        ],
        ids=[
            "test_site_page_includes_toggle_button",
            "test_site_page_toggle_has_icons",
            "test_site_js_includes_theme_init",
            "test_site_js_listens_for_system_preference",
        ],
    )
    def test_file_contains_tokens(self, path: str, tokens: list[str]) -> None:
        # v0.67.69: theme_toggle.html retired; toggle button is now
        # inline-rendered in site_routes._render_site_inner_html.
        content = Path(path).read_text()
        for token in tokens:
            assert token in content

    def test_site_js_uses_storage_key(self):
        """Test that site.js uses the same storage key."""
        js_path = Path("src/dazzle/page/static/js/site.js")
        js_content = js_path.read_text()

        # Check for storage key in site.js
        assert "dz-theme-variant" in js_content
