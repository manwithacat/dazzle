"""
DAZZLE Theme System.

Provides a unified theming system for both SiteSpec (public site pages)
and AppSpec (app workspaces) content.

Usage:
    from dazzle_dnr_ui.themes import (
        SAAS_DEFAULT_THEME,
        MINIMAL_THEME,
        get_theme_preset,
        generate_theme_css,
        resolve_theme,
    )

    # Get a preset theme
    theme = get_theme_preset("saas-default")

    # Generate CSS from theme
    css = generate_theme_css(theme)

    # Resolve theme with overrides
    theme = resolve_theme(
        preset_name="saas-default",
        manifest_overrides={"colors": {"hero-bg-from": "..."}},
    )
"""

from .css_generator import generate_theme_css
from .presets import (
    CORPORATE_THEME,
    DOCS_THEME,
    MINIMAL_THEME,
    SAAS_DEFAULT_THEME,
    STARTUP_THEME,
    get_theme_preset,
    list_theme_presets,
)
from .resolver import resolve_theme

__all__ = [
    # Presets
    "SAAS_DEFAULT_THEME",
    "MINIMAL_THEME",
    "CORPORATE_THEME",
    "STARTUP_THEME",
    "DOCS_THEME",
    "get_theme_preset",
    "list_theme_presets",
    # CSS Generation
    "generate_theme_css",
    # Resolution
    "resolve_theme",
]
