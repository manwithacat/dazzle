"""
Next.js Semantic UI Backend Implementation.

Generates Next.js applications with layout engine integration.

Performance optimizations:
- Layout plan caching (skip unchanged workspaces)
- Parallel workspace processing (when cache misses)
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ...core import ir
from ...ui.layout_engine import (
    build_layout_plan,
    enrich_app_spec_with_layouts,
    get_layout_cache,
    LayoutPlanCache,
)
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
        """Generate layout plans for all workspaces (with caching + parallel processing)."""
        self.layout_plans = {}

        # Auto-convert WorkspaceSpec to WorkspaceLayout if needed
        if not self.spec.ux or not self.spec.ux.workspaces:
            # Try to convert from WorkspaceSpec
            if self.spec.workspaces:
                self.spec = enrich_app_spec_with_layouts(self.spec)
            else:
                # No workspaces at all
                return

        if not self.spec.ux or not self.spec.ux.workspaces:
            return

        # Get cache instance (stores in output_dir/.dazzle/cache/layout_plans)
        cache = get_layout_cache(self.output_dir)

        # Separate cached vs uncached workspaces
        cached_workspaces = []
        uncached_workspaces = []

        for workspace in self.spec.ux.workspaces:
            cached_plan = cache.get(workspace)
            if cached_plan is not None:
                cached_workspaces.append((workspace, cached_plan))
            else:
                uncached_workspaces.append(workspace)

        # Add cached plans immediately
        for workspace, plan in cached_workspaces:
            self.layout_plans[workspace.id] = plan

        # Process uncached workspaces in parallel (if multiple)
        if len(uncached_workspaces) > 1:
            self._generate_plans_parallel(uncached_workspaces, cache)
        elif len(uncached_workspaces) == 1:
            # Single workspace - no parallelization overhead
            workspace = uncached_workspaces[0]
            plan = build_layout_plan(workspace)
            self.layout_plans[workspace.id] = plan
            cache.set(workspace, plan)

    def _generate_plans_parallel(
        self,
        workspaces: list[ir.WorkspaceLayout],
        cache: LayoutPlanCache,
    ) -> None:
        """Generate layout plans in parallel for multiple workspaces."""
        # Use thread pool for I/O-bound operations
        # Limit workers to avoid overwhelming CPU (layout planning is mostly CPU-bound)
        max_workers = min(4, len(workspaces))

        def process_workspace(workspace: ir.WorkspaceLayout):
            """Process single workspace and return result."""
            plan = build_layout_plan(workspace)
            return workspace, plan

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(process_workspace, ws): ws
                for ws in workspaces
            }

            # Collect results as they complete
            for future in as_completed(futures):
                workspace, plan = future.result()
                self.layout_plans[workspace.id] = plan
                # Cache for next time
                cache.set(workspace, plan)


__all__ = ["NextjsSemanticBackend"]
