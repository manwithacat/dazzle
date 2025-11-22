"""
URLs generator for Django Micro backend.

Generates Django URL configurations.
"""

from pathlib import Path

from ...base import Generator, GeneratorResult
from ....core import ir


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

    def __init__(self, spec: ir.AppSpec, output_dir: Path, project_name: str, app_name: str = "app"):
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
            'App URL configuration generated from DAZZLE DSL.',
            '"""',
            'from django.urls import path',
            'from . import views',
            '',
            'urlpatterns = [',
            '    # Home page',
            '    path("", views.HomeView.as_view(), name="home"),',
            '',
        ]

        # Generate URLs for each entity
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            lines.append(f'    # {entity.name} URLs')
            lines.append(f'    path("{entity_lower}/", views.{entity.name}ListView.as_view(), name="{entity_lower}-list"),')

            # IMPORTANT: Put create/ before <pk>/ to avoid matching issues
            lines.append(f'    path("{entity_lower}/create/", views.{entity.name}CreateView.as_view(), name="{entity_lower}-create"),')
            lines.append(f'    path("{entity_lower}/<pk>/", views.{entity.name}DetailView.as_view(), name="{entity_lower}-detail"),')
            lines.append(f'    path("{entity_lower}/<pk>/edit/", views.{entity.name}UpdateView.as_view(), name="{entity_lower}-update"),')
            lines.append(f'    path("{entity_lower}/<pk>/delete/", views.{entity.name}DeleteView.as_view(), name="{entity_lower}-delete"),')
            lines.append('')

        lines.append(']')
        return '\n'.join(lines)

    def _build_project_urls_code(self) -> str:
        """Build project/urls.py content."""
        lines = [
            '"""',
            'Project URL configuration generated from DAZZLE DSL.',
            '"""',
            'from django.contrib import admin',
            'from django.urls import path, include',
            '',
            'urlpatterns = [',
            '    path("admin/", admin.site.urls),',
            f'    path("", include("{self.app_name}.urls")),',
            ']',
        ]
        return '\n'.join(lines)
