"""
Next.js Onebox Backend.

Generates a complete Next.js 14+ application with:
- App Router
- Prisma + PostgreSQL
- Tailwind CSS + Mantine DataTable
- Full UX Semantic Layer support
- Built-in authentication
- Docker deployment
"""

from pathlib import Path
from typing import Any

from ...core import ir
from .. import BackendCapabilities
from ..base.backend import ModularBackend
from ..base.generator import Generator
from .generators import (
    ActionsGenerator,
    AuthGenerator,
    ComponentsGenerator,
    ConfigGenerator,
    DockerGenerator,
    LayoutGenerator,
    LibGenerator,
    MiddlewareGenerator,
    PagesGenerator,
    PrismaGenerator,
    StylesGenerator,
    TypesGenerator,
)


class NextJSOneboxBackend(ModularBackend):
    """
    Next.js Onebox stack backend.

    Generates a production-ready Next.js application in a single Docker container.
    """

    def __init__(self) -> None:
        """Initialize the Next.js Onebox backend."""
        super().__init__()
        self.register_hooks()

    def register_hooks(self) -> None:
        """Register post-build hooks."""
        # Hooks will be added later
        pass

    def get_capabilities(self) -> BackendCapabilities:
        """Return backend capabilities."""
        return BackendCapabilities(
            name="nextjs_onebox",
            description="Next.js 14+ App Router with Prisma, PostgreSQL, and full UX layer",
            output_formats=["typescript", "prisma", "docker"],
            supports_incremental=False,
            requires_config=False,
        )

    def get_generators(self, spec: ir.AppSpec, output_dir: Path, **options: Any) -> list[Generator]:
        """
        Get the list of generators for Next.js Onebox.

        Generator order matters - dependencies must be generated first.
        """
        # Calculate project path
        project_name = self._normalize_name(spec.name)
        project_path = output_dir / project_name

        # Store in options for generators
        options["project_path"] = project_path
        options["project_name"] = project_name

        return [
            # Phase 1: Foundation
            ConfigGenerator(spec, project_path),
            DockerGenerator(spec, project_path),
            # Phase 2: Data Layer
            PrismaGenerator(spec, project_path),  # type: ignore[no-untyped-call]
            TypesGenerator(spec, project_path),
            LibGenerator(spec, project_path),
            # Phase 3: Actions
            ActionsGenerator(spec, project_path),
            # Phase 4: Components & Styles
            ComponentsGenerator(spec, project_path),
            StylesGenerator(spec, project_path),
            # Phase 5: Pages & Layout
            AuthGenerator(spec, project_path),
            LayoutGenerator(spec, project_path),
            MiddlewareGenerator(spec, project_path),
            PagesGenerator(spec, project_path),
        ]

    def _normalize_name(self, name: str) -> str:
        """Normalize project name for file system."""
        return name.lower().replace(" ", "_").replace("-", "_")
