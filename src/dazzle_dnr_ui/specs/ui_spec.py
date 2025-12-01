"""
UISpec - Main UI specification aggregate.

This is the root type that contains all UI specifications.
"""

from typing import Any

from pydantic import BaseModel, Field

from dazzle_dnr_ui.specs.component import ComponentSpec
from dazzle_dnr_ui.specs.shell import ShellSpec
from dazzle_dnr_ui.specs.theme import ThemeSpec
from dazzle_dnr_ui.specs.workspace import WorkspaceSpec


class UISpec(BaseModel):
    """
    Complete UI specification.

    This is the aggregate root for all UI specifications, containing:
    - Shell (app chrome: nav, header, footer)
    - Workspaces (logical sections of the UI)
    - Components (reusable UI elements)
    - Themes (visual design systems)

    Example:
        UISpec(
            name="invoice_system_ui",
            version="1.0.0",
            shell=ShellSpec(
                nav=NavSpec(style="sidebar", brand="Invoice System"),
                footer=FooterSpec(powered_by=True)
            ),
            workspaces=[
                WorkspaceSpec(name="dashboard", layout=AppShellLayout(...), routes=[...]),
                WorkspaceSpec(name="settings", layout=SingleColumnLayout(...)),
            ],
            components=[
                ComponentSpec(name="ClientCard", ...),
                ComponentSpec(name="InvoiceTable", ...),
            ],
            themes=[
                ThemeSpec(name="default", tokens=ThemeTokens(...)),
            ]
        )
    """

    # Metadata
    name: str = Field(description="UI name")
    version: str = Field(default="1.0.0", description="UI version")
    description: str | None = Field(default=None, description="UI description")

    # Shell (app chrome)
    shell: ShellSpec = Field(default_factory=ShellSpec, description="Application shell config")

    # Core specifications
    workspaces: list[WorkspaceSpec] = Field(
        default_factory=list, description="Workspace specifications"
    )
    components: list[ComponentSpec] = Field(
        default_factory=list, description="Component specifications"
    )
    themes: list[ThemeSpec] = Field(default_factory=list, description="Theme specifications")

    # Default selections
    default_workspace: str | None = Field(default=None, description="Default workspace to show")
    default_theme: str | None = Field(default=None, description="Default theme to apply")

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        frozen = True

    # =========================================================================
    # Query methods
    # =========================================================================

    def get_workspace(self, name: str) -> WorkspaceSpec | None:
        """Get workspace by name."""
        for workspace in self.workspaces:
            if workspace.name == name:
                return workspace
        return None

    def get_component(self, name: str) -> ComponentSpec | None:
        """Get component by name."""
        for component in self.components:
            if component.name == name:
                return component
        return None

    def get_theme(self, name: str) -> ThemeSpec | None:
        """Get theme by name."""
        for theme in self.themes:
            if theme.name == name:
                return theme
        return None

    def get_primitives(self) -> list[ComponentSpec]:
        """Get all primitive components."""
        return [c for c in self.components if c.is_primitive]

    def get_patterns(self) -> list[ComponentSpec]:
        """Get all pattern components."""
        return [c for c in self.components if c.is_pattern]

    def get_custom_components(self) -> list[ComponentSpec]:
        """Get all custom components."""
        return [c for c in self.components if c.is_custom]

    # =========================================================================
    # Validation
    # =========================================================================

    def validate_references(self) -> list[str]:
        """
        Validate all references between specs.

        Returns list of error messages (empty if valid).
        """
        errors = []

        # Check that default workspace exists
        if self.default_workspace and not self.get_workspace(self.default_workspace):
            errors.append(f"Default workspace '{self.default_workspace}' does not exist")

        # Check that default theme exists
        if self.default_theme and not self.get_theme(self.default_theme):
            errors.append(f"Default theme '{self.default_theme}' does not exist")

        # Check that workspace layout components exist
        for workspace in self.workspaces:
            layout = workspace.layout
            component_names: list[str] = []

            if hasattr(layout, "main"):
                component_names.append(layout.main)
            if hasattr(layout, "header") and layout.header:
                component_names.append(layout.header)
            if hasattr(layout, "sidebar") and layout.sidebar:
                component_names.append(layout.sidebar)
            if hasattr(layout, "secondary") and layout.secondary:
                component_names.append(layout.secondary)
            if hasattr(layout, "footer") and layout.footer:
                component_names.append(layout.footer)
            if hasattr(layout, "regions"):
                component_names.extend(layout.regions.values())

            for component_name in component_names:
                if not self.get_component(component_name):
                    errors.append(
                        f"Workspace '{workspace.name}' references unknown component '{component_name}'"
                    )

        # Check that route components exist
        for workspace in self.workspaces:
            for route in workspace.routes:
                if not self.get_component(route.component):
                    errors.append(
                        f"Workspace '{workspace.name}' route '{route.path}' references unknown component '{route.component}'"
                    )

        # Check that component view references exist (ElementNode.as)
        # This is a simplified check - full validation would need recursive view tree traversal
        for component in self.components:
            if component.view and hasattr(component.view, "as_"):
                referenced = component.view.as_
                # Check if it's a component reference (starts with uppercase)
                if referenced[0].isupper() and not self.get_component(referenced):
                    errors.append(
                        f"Component '{component.name}' view references unknown component '{referenced}'"
                    )

        return errors

    # =========================================================================
    # Stats
    # =========================================================================

    @property
    def stats(self) -> dict[str, int]:
        """Get statistics about this UI spec."""
        return {
            "workspaces": len(self.workspaces),
            "components": len(self.components),
            "primitives": len(self.get_primitives()),
            "patterns": len(self.get_patterns()),
            "custom_components": len(self.get_custom_components()),
            "themes": len(self.themes),
            "total_routes": sum(len(w.routes) for w in self.workspaces),
        }
