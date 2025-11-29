"""
DDT (Dazzle Design Tokens) - LLM-first design system.

This package provides:
- Design tokens in JSON schema format
- CSS variable compilation
- Semantic component styles
- Minimal utility classes

Usage:
    from dazzle_dnr_ui.tokens import compile_tokens, generate_css_bundle

    # Generate complete CSS bundle
    css = generate_css_bundle()

    # Write CSS files
    from dazzle_dnr_ui.tokens.compiler import write_css_bundle
    write_css_bundle(Path("./static/css"))
"""

from dazzle_dnr_ui.tokens.compiler import (
    compile_tokens_to_variables,
    generate_component_styles,
    generate_css_bundle,
    generate_dark_theme,
    generate_utility_styles,
    load_tokens,
    write_css_bundle,
)

__all__ = [
    "load_tokens",
    "compile_tokens_to_variables",
    "generate_dark_theme",
    "generate_component_styles",
    "generate_utility_styles",
    "generate_css_bundle",
    "write_css_bundle",
]
