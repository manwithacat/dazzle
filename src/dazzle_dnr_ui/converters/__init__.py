"""
AppSpec to UISpec Converters

Converts Dazzle AppSpec (IR) to UISpec.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.core import ir
from dazzle_dnr_ui.converters.surface_converter import (
    _generate_component_name,
    convert_surfaces_to_components,
)
from dazzle_dnr_ui.converters.template_compiler import (
    compile_appspec_to_templates,
    compile_surface_to_context,
)
from dazzle_dnr_ui.converters.workspace_converter import (
    compute_persona_default_routes,
    convert_workspaces,
)
from dazzle_dnr_ui.specs import (
    FooterLinkSpec,
    FooterSpec,
    HeaderSpec,
    NavItemSpec,
    NavSpec,
    ShellSpec,
    StaticPageSpec,
    ThemeSpec,
    ThemeTokens,
    UISpec,
    WorkspaceSpec,
)

if TYPE_CHECKING:
    from dazzle.core.manifest import ShellConfig


def convert_shell_config(
    shell_config: ShellConfig | None,
    workspaces: list[WorkspaceSpec],
    app_name: str,
) -> ShellSpec:
    """
    Convert manifest shell config to UISpec ShellSpec.

    If shell_config is None, generates sensible defaults from workspaces.

    Args:
        shell_config: Shell config from dazzle.toml (optional)
        workspaces: List of workspaces for auto-generating nav
        app_name: Application name for branding

    Returns:
        ShellSpec with navigation, header, and footer config
    """
    # Auto-generate nav items from workspaces
    # First workspace gets "/" route, others get "/workspace_name" route
    nav_items = []
    for i, ws in enumerate(workspaces):
        if i == 0:
            # First workspace is the default - gets root route
            root_route = "/"
        else:
            # Other workspaces get their own base route
            root_route = f"/{ws.name.replace('_', '-')}"
        nav_items.append(
            NavItemSpec(
                label=ws.label or ws.name.replace("_", " ").title(),
                route=root_route,
                workspace=ws.name,
            )
        )

    # If we have manifest config, use it
    if shell_config is not None:
        nav = NavSpec(
            style=shell_config.nav.style,  # type: ignore[arg-type]
            items=nav_items,  # Auto-generated from workspaces
            brand=app_name.replace("_", " ").title(),
        )

        footer_links = [
            FooterLinkSpec(label=link.label, href=link.href) for link in shell_config.footer.links
        ]

        # Add static page links to footer (skip if already linked)
        existing_hrefs = {link.href for link in footer_links}
        for page in shell_config.pages:
            if page.route not in existing_hrefs:
                title = page.title or page.route.strip("/").replace("-", " ").title()
                footer_links.append(FooterLinkSpec(label=title, href=page.route))

        footer = FooterSpec(
            powered_by=shell_config.footer.powered_by,
            links=footer_links,
        )

        header = HeaderSpec(
            show_auth=shell_config.header.show_auth,
            title=app_name.replace("_", " ").title(),
        )

        pages = [
            StaticPageSpec(
                route=page.route,
                title=page.title or page.route.strip("/").replace("-", " ").title(),
                content=page.content,
                src=page.src,
            )
            for page in shell_config.pages
        ]

        return ShellSpec(
            layout=shell_config.layout,  # type: ignore[arg-type]
            nav=nav,
            header=header,
            footer=footer,
            pages=pages,
        )

    # Generate defaults
    return ShellSpec(
        layout="app-shell",
        nav=NavSpec(
            style="sidebar",
            items=nav_items,
            brand=app_name.replace("_", " ").title(),
        ),
        header=HeaderSpec(
            show_auth=True,
            title=app_name.replace("_", " ").title(),
        ),
        footer=FooterSpec(
            powered_by=True,
            links=[],
        ),
        pages=[],
    )


def convert_appspec_to_ui(
    appspec: ir.AppSpec,
    shell_config: ShellConfig | None = None,
) -> UISpec:
    """
    Convert a complete Dazzle AppSpec to DNR UISpec.

    This is the main entry point for converting Dazzle's internal representation
    to the native UI specification.

    Args:
        appspec: Complete Dazzle application specification
        shell_config: Optional shell config from dazzle.toml manifest

    Returns:
        DNR UISpec with shell, workspaces, components, and themes

    Example:
        >>> from dazzle.core.linker import build_appspec
        >>> appspec = build_appspec(modules, project_root)
        >>> ui_spec = convert_appspec_to_ui(appspec)
    """
    # Convert surfaces to components first so we can reference them in workspaces
    components = convert_surfaces_to_components(
        appspec.surfaces,
        appspec.domain,
    )

    # Build surface name -> component name mapping for workspace routing
    surface_component_map = {
        surface.name: _generate_component_name(surface) for surface in appspec.surfaces
    }

    # Convert workspaces, passing surfaces for intelligent route generation
    workspaces = convert_workspaces(
        appspec.workspaces,
        appspec.surfaces,
        surface_component_map,
        entities=appspec.domain.entities if appspec.domain else [],
    )

    # Convert shell config (or generate defaults)
    shell = convert_shell_config(shell_config, workspaces, appspec.name)

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
        shell=shell,
        workspaces=workspaces,
        components=components,
        themes=[default_theme],
        default_theme="default",
        default_workspace=workspaces[0].name if workspaces else None,
    )


__all__ = [
    "convert_appspec_to_ui",
    "convert_shell_config",
    "convert_workspaces",
    "convert_surfaces_to_components",
    "compute_persona_default_routes",
    "compile_appspec_to_templates",
    "compile_surface_to_context",
]
