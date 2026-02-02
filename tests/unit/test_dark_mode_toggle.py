"""
Unit tests for DAZZLE dark mode toggle (v0.16.0 - Issue #26).

Tests for site page dark mode toggle functionality.
"""


class TestDarkModeCSSClasses:
    """Tests for dark mode CSS classes in site-sections.css."""

    def test_dark_mode_toggle_button_styles(self):
        """Test that toggle button CSS classes are defined."""
        from pathlib import Path

        css_path = Path("src/dazzle_ui/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        # Check toggle button styles exist
        assert ".dz-theme-toggle" in css_content
        assert ".dz-theme-toggle:hover" in css_content
        assert ".dz-theme-toggle__icon" in css_content
        assert ".dz-theme-toggle__sun" in css_content
        assert ".dz-theme-toggle__moon" in css_content

    def test_dark_mode_site_header_styles(self):
        """Test that dark mode header styles are defined."""
        from pathlib import Path

        css_path = Path("src/dazzle_ui/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        # Check dark mode header styles
        assert '[data-theme="dark"] .dz-site-header' in css_content
        assert '[data-theme="dark"] .dz-site-logo' in css_content
        assert '[data-theme="dark"] .dz-nav-link' in css_content

    def test_dark_mode_section_styles(self):
        """Test that dark mode section styles are defined."""
        from pathlib import Path

        css_path = Path("src/dazzle_ui/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        # Check dark mode section styles
        assert '[data-theme="dark"] .dz-section-features' in css_content
        assert '[data-theme="dark"] .dz-section-pricing' in css_content
        assert '[data-theme="dark"] .dz-section-faq' in css_content
        assert '[data-theme="dark"] .dz-section-testimonials' in css_content

    def test_dark_mode_card_styles(self):
        """Test that dark mode card styles are defined."""
        from pathlib import Path

        css_path = Path("src/dazzle_ui/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        # Check dark mode card styles
        assert '[data-theme="dark"] .dz-feature-card' in css_content
        assert '[data-theme="dark"] .dz-feature-item' in css_content
        assert '[data-theme="dark"] .dz-testimonial-item' in css_content

    def test_dark_mode_auth_styles(self):
        """Test that dark mode auth page styles are defined."""
        from pathlib import Path

        css_path = Path("src/dazzle_ui/runtime/static/css/site-sections.css")
        css_content = css_path.read_text()

        # Check dark mode auth styles
        assert '[data-theme="dark"] .dz-auth-card' in css_content
        assert '[data-theme="dark"] .dz-auth-field input' in css_content


class TestSitePageToggleButton:
    """Tests for toggle button in site pages."""

    def test_site_page_includes_toggle_button(self):
        """Test that site page HTML includes toggle button."""
        from pathlib import Path

        # Toggle button HTML is in site_renderer.py (extracted from combined_server.py)
        py_path = Path("src/dazzle_ui/runtime/site_renderer.py")
        py_content = py_path.read_text()

        # Check toggle button is included
        assert "dz-theme-toggle" in py_content
        assert "Toggle dark mode" in py_content

    def test_site_page_toggle_has_icons(self):
        """Test that toggle button has sun and moon icons."""
        from pathlib import Path

        # Toggle button HTML is in site_renderer.py (extracted from combined_server.py)
        py_path = Path("src/dazzle_ui/runtime/site_renderer.py")
        py_content = py_path.read_text()

        # Check for sun and moon SVG icons
        assert "dz-theme-toggle__sun" in py_content
        assert "dz-theme-toggle__moon" in py_content

    def test_site_js_includes_theme_init(self):
        """Test that site.js includes theme initialization."""
        from pathlib import Path

        py_path = Path("src/dazzle_ui/runtime/combined_server.py")
        py_content = py_path.read_text()

        # Check for theme initialization in site.js
        assert "initTheme()" in py_content
        assert "toggleTheme()" in py_content

    def test_site_js_uses_storage_key(self):
        """Test that site.js uses the same storage key."""
        from pathlib import Path

        py_path = Path("src/dazzle_ui/runtime/combined_server.py")
        py_content = py_path.read_text()

        # Check for storage key in site.js
        assert "dz-theme-variant" in py_content

    def test_site_js_listens_for_system_preference(self):
        """Test that site.js listens for system preference changes."""
        from pathlib import Path

        py_path = Path("src/dazzle_ui/runtime/combined_server.py")
        py_content = py_path.read_text()

        # Check for system preference listener
        assert "prefers-color-scheme" in py_content
        assert "addEventListener" in py_content
