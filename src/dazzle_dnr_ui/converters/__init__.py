"""
AppSpec to UISpec Converters

Converts Dazzle AppSpec (IR) to UISpec.
"""

from dazzle.core import ir
from dazzle_dnr_ui.specs import UISpec, ThemeSpec, ThemeTokens
from dazzle_dnr_ui.converters.workspace_converter import convert_workspaces
from dazzle_dnr_ui.converters.surface_converter import convert_surfaces_to_components


def convert_appspec_to_ui(appspec: ir.AppSpec) -> UISpec:
    """
    Convert a complete Dazzle AppSpec to DNR UISpec.

    This is the main entry point for converting Dazzle's internal representation
    to the native UI specification.

    Args:
        appspec: Complete Dazzle application specification

    Returns:
        DNR UISpec with workspaces, components, and themes

    Example:
        >>> from dazzle.core.linker import build_appspec
        >>> appspec = build_appspec(modules, project_root)
        >>> ui_spec = convert_appspec_to_ui(appspec)
    """
    # Convert workspaces
    workspaces = convert_workspaces(appspec.workspaces)

    # Convert surfaces to components
    components = convert_surfaces_to_components(
        appspec.surfaces,
        appspec.domain,
    )

    # Create a default theme
    default_theme = ThemeSpec(
        name="default",
        description="Default application theme",
        tokens=ThemeTokens(
            colors={
                "primary": "#0066cc",
                "secondary": "#6c757d",
                "success": "#28a745",
                "danger": "#dc3545",
                "warning": "#ffc107",
                "info": "#17a2b8",
                "background": "#ffffff",
                "surface": "#f8f9fa",
                "text": "#212529",
                "text-secondary": "#6c757d",
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
        ),
    )

    # Build the UISpec
    return UISpec(
        name=f"{appspec.name}_ui",
        version=appspec.version,
        description=appspec.title,
        workspaces=workspaces,
        components=components,
        themes=[default_theme],
        default_theme="default",
        default_workspace=workspaces[0].name if workspaces else None,
    )


__all__ = [
    "convert_appspec_to_ui",
    "convert_workspaces",
    "convert_surfaces_to_components",
]
