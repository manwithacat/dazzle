"""
Next.js Semantic UI Backend Implementation.

Generates Next.js applications with layout engine integration.
"""

from pathlib import Path
from typing import Any

from ...core import ir
from ...ui.layout_engine import build_layout_plan
from .. import Backend, BackendCapabilities
from .generators import (
    ArchetypeComponentsGenerator,
    ConfigGenerator,
    LayoutTypesGenerator,
    PackageJsonGenerator,
    PagesGenerator,
    TailwindConfigGenerator,
)


class NextjsSemanticBackend(Backend):
    """
    Next.js Semantic UI backend - layout engine powered.

    Generates modern Next.js applications with:
    - Semantic layout archetypes
    - TypeScript types from IR
    - Tailwind CSS styling
    - Responsive layouts
    - Persona-aware components
    """

    def get_capabilities(self) -> BackendCapabilities:
        """Return backend capabilities."""
        return BackendCapabilities(
            name="nextjs_semantic",
            description="Next.js app with semantic layout engine (TypeScript, Tailwind, App Router)",
            output_formats=["typescript", "tsx", "css", "json"],
            supports_incremental=False,
        )

    def generate(self, appspec: ir.AppSpec, output_dir: Path, **options: Any) -> None:
        """
        Generate Next.js application with semantic layouts.

        Args:
            appspec: Application specification
            output_dir: Output directory
            **options: Backend options
        """
        self.spec = appspec
        self.output_dir = output_dir
        self.options = options

        # Determine project name
        self.project_name = self._get_project_name(appspec)

        # Create project structure
        self._generate_project_structure()

        # Generate layout plans for all workspaces
        self._generate_layout_plans()

        # Run generators
        generators = [
            PackageJsonGenerator(self.spec, self.project_path, self.project_name),
            ConfigGenerator(self.spec, self.project_path),
            TailwindConfigGenerator(self.spec, self.project_path),
            LayoutTypesGenerator(self.spec, self.project_path, self.layout_plans),
            ArchetypeComponentsGenerator(self.spec, self.project_path),
            PagesGenerator(self.spec, self.project_path, self.layout_plans),
        ]

        for generator in generators:
            generator.generate()

    def _get_project_name(self, spec: ir.AppSpec) -> str:
        """Get project name from spec."""
        if spec.name:
            name = spec.name.lower().replace(" ", "-").replace("_", "-")
            name = "".join(c for c in name if c.isalnum() or c == "-")
            return name or "my-app"
        return "my-app"

    def _generate_project_structure(self) -> None:
        """Create Next.js App Router project structure."""
        self.project_path = self.output_dir / self.project_name
        self.project_path.mkdir(parents=True, exist_ok=True)

        # Next.js App Router structure
        (self.project_path / "src").mkdir(exist_ok=True)
        (self.project_path / "src" / "app").mkdir(exist_ok=True)
        (self.project_path / "src" / "components").mkdir(exist_ok=True)
        (self.project_path / "src" / "components" / "archetypes").mkdir(exist_ok=True)
        (self.project_path / "src" / "components" / "signals").mkdir(exist_ok=True)
        (self.project_path / "src" / "lib").mkdir(exist_ok=True)
        (self.project_path / "src" / "types").mkdir(exist_ok=True)
        (self.project_path / "public").mkdir(exist_ok=True)

    def _generate_layout_plans(self) -> None:
        """Generate layout plans for all workspaces in the spec."""
        self.layout_plans = {}

        # Get workspaces from UX section
        if not self.spec.ux or not self.spec.ux.workspaces:
            return

        for workspace in self.spec.ux.workspaces:
            # Build plan without persona first (can add persona support later)
            plan = build_layout_plan(workspace)
            self.layout_plans[workspace.id] = plan


__all__ = ["NextjsSemanticBackend"]
