"""
ShellSpec - Application shell configuration for DNR-UI.

The shell provides the chrome around workspace content:
- Navigation (sidebar, topbar, or tabs)
- Header with optional auth UI
- Footer with optional links and "Made with Dazzle"
- Static pages (privacy, terms, etc.)
"""

from typing import Literal

from pydantic import BaseModel, Field


class NavItemSpec(BaseModel):
    """A navigation item."""

    label: str = Field(description="Display label")
    route: str = Field(description="Route path (e.g., '/' or '/settings')")
    icon: str | None = Field(default=None, description="Optional icon name")
    workspace: str | None = Field(default=None, description="Workspace name this links to")


class NavSpec(BaseModel):
    """Navigation configuration."""

    style: Literal["sidebar", "topbar", "tabs"] = Field(
        default="sidebar", description="Navigation style"
    )
    items: list[NavItemSpec] = Field(
        default_factory=list, description="Navigation items (auto-generated from workspaces if empty)"
    )
    brand: str | None = Field(default=None, description="Brand text/name in nav")
    logo: str | None = Field(default=None, description="Logo URL")


class FooterLinkSpec(BaseModel):
    """A footer link."""

    label: str = Field(description="Link text")
    href: str = Field(description="Link URL")


class FooterSpec(BaseModel):
    """Footer configuration."""

    powered_by: bool = Field(default=True, description="Show 'Made with Dazzle' link")
    copyright: str | None = Field(default=None, description="Copyright text")
    links: list[FooterLinkSpec] = Field(default_factory=list, description="Footer links")


class HeaderSpec(BaseModel):
    """Header configuration."""

    show_auth: bool = Field(default=True, description="Show login/logout UI")
    title: str | None = Field(default=None, description="App title in header")


class StaticPageSpec(BaseModel):
    """Static page configuration."""

    route: str = Field(description="URL route (e.g., '/privacy')")
    title: str = Field(description="Page title")
    content: str | None = Field(default=None, description="Page content (HTML or Markdown)")
    src: str | None = Field(default=None, description="Source file path")


class ShellSpec(BaseModel):
    """
    Application shell specification.

    The shell wraps workspace content with navigation, header, and footer.
    It provides a consistent layout and navigation across the application.

    Example:
        ShellSpec(
            layout="app-shell",
            nav=NavSpec(
                style="sidebar",
                brand="My Task App",
                items=[
                    NavItemSpec(label="Tasks", route="/", workspace="dashboard"),
                    NavItemSpec(label="Settings", route="/settings", workspace="settings"),
                ]
            ),
            footer=FooterSpec(
                powered_by=True,
                links=[
                    FooterLinkSpec(label="Privacy", href="/privacy"),
                    FooterLinkSpec(label="Terms", href="/terms"),
                ]
            )
        )
    """

    layout: Literal["app-shell", "minimal"] = Field(
        default="app-shell", description="Shell layout type"
    )
    nav: NavSpec = Field(default_factory=NavSpec, description="Navigation configuration")
    header: HeaderSpec = Field(default_factory=HeaderSpec, description="Header configuration")
    footer: FooterSpec = Field(default_factory=FooterSpec, description="Footer configuration")
    pages: list[StaticPageSpec] = Field(
        default_factory=list, description="Static pages (privacy, terms, etc.)"
    )

    class Config:
        frozen = True
