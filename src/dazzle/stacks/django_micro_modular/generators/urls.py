"""
URLs generator for Django Micro backend.

Generates Django URL configurations.
"""

from pathlib import Path

from ....core import ir
from ...base import Generator, GeneratorResult


class UrlsGenerator(Generator):
    """
    Generate Django URL configurations.

    Creates:
    - app/urls.py - URL patterns for entities
    - project/urls.py - Root URL configuration

    URL patterns are generated for each entity with proper ordering:
    - Specific paths before parameterized paths
    - create/ before <pk>/
    """

    def __init__(
        self, spec: ir.AppSpec, output_dir: Path, project_name: str, app_name: str = "app"
    ):
        """
        Initialize URLs generator.

        Args:
            spec: Application specification
            output_dir: Root output directory
            project_name: Name of the Django project
            app_name: Name of the Django app
        """
        super().__init__(spec, output_dir)
        self.project_name = project_name
        self.app_name = app_name

    def generate(self) -> GeneratorResult:
        """Generate URL configuration files."""
        result = GeneratorResult()

        # Generate app URLs
        app_urls_code = self._build_app_urls_code()
        app_urls_path = self.output_dir / self.app_name / "urls.py"
        self._write_file(app_urls_path, app_urls_code)
        result.add_file(app_urls_path)

        # Generate project URLs
        project_urls_code = self._build_project_urls_code()
        project_urls_path = self.output_dir / self.project_name / "urls.py"
        self._write_file(project_urls_path, project_urls_code)
        result.add_file(project_urls_path)

        return result

    def _build_app_urls_code(self) -> str:
        """Build app/urls.py content."""
        lines = [
            '"""',
            "App URL configuration generated from DAZZLE DSL.",
            '"""',
            "from django.urls import path",
            "from . import views",
            "",
            "urlpatterns = [",
            "    # Home page",
            '    path("", views.HomeView.as_view(), name="home"),',
            "",
        ]

        # Group surfaces by entity to determine which URLs to generate
        entity_surfaces = {}
        for surface in self.spec.surfaces:
            if surface.entity_ref:
                entity_name = surface.entity_ref
                if entity_name not in entity_surfaces:
                    entity_surfaces[entity_name] = set()
                entity_surfaces[entity_name].add(surface.mode)

        # Generate URLs only for surfaces that exist in DSL
        for entity in self.spec.domain.entities:
            entity_name = entity.name
            entity_lower = entity_name.lower()

            # Skip entities with no surfaces defined
            if entity_name not in entity_surfaces:
                continue

            modes = entity_surfaces[entity_name]
            lines.append(f"    # {entity_name} URLs")

            # List view (if mode: list exists)
            if ir.SurfaceMode.LIST in modes:
                lines.append(
                    f'    path("{entity_lower}/", views.{entity_name}ListView.as_view(), name="{entity_lower}-list"),'
                )

            # Create view (if mode: create exists)
            # IMPORTANT: Put create/ before <pk>/ to avoid matching issues
            if ir.SurfaceMode.CREATE in modes:
                lines.append(
                    f'    path("{entity_lower}/create/", views.{entity_name}CreateView.as_view(), name="{entity_lower}-create"),'
                )

            # Detail view (if mode: view exists)
            if ir.SurfaceMode.VIEW in modes:
                lines.append(
                    f'    path("{entity_lower}/<pk>/", views.{entity_name}DetailView.as_view(), name="{entity_lower}-detail"),'
                )

            # Update view (if mode: edit exists)
            if ir.SurfaceMode.EDIT in modes:
                lines.append(
                    f'    path("{entity_lower}/<pk>/edit/", views.{entity_name}UpdateView.as_view(), name="{entity_lower}-update"),'
                )

            # Delete view - always generate if entity has any surfaces
            # (Delete is a safety mechanism, keep it available)
            lines.append(
                f'    path("{entity_lower}/<pk>/delete/", views.{entity_name}DeleteView.as_view(), name="{entity_lower}-delete"),'
            )

            lines.append("")

        lines.append("]")
        return "\n".join(lines)

    def _build_project_urls_code(self) -> str:
        """Build project/urls.py content."""
        lines = [
            '"""',
            "Project URL configuration generated from DAZZLE DSL.",
            '"""',
            "from django.contrib import admin",
            "from django.urls import path, include",
            "from django.conf import settings",
            "from django.conf.urls.static import static",
            "",
            "urlpatterns = [",
            '    path("admin/", admin.site.urls),',
            f'    path("", include("{self.app_name}.urls")),',
            "]",
            "",
            "# Serve static files during development",
            "if settings.DEBUG:",
            "    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)",
        ]
        return "\n".join(lines)
