"""
Django Micro Modular Backend - Production Ready

Complete Django application generator with modular architecture:
- 9 specialized generators (models, admin, forms, views, urls, templates, static, settings, deployment)
- Pre/post-build hooks for extensibility
- Provisioning support (admin credentials)
- Clean separation of concerns
- Production-ready code generation

This is now the default backend for DAZZLE, generating fully functional
Django applications with proper primary keys, CRUD operations, responsive UI,
and deployment configurations.
"""

from pathlib import Path

from ...core import ir
from ..base import Generator, ModularBackend
from .generators import (
    AdminGenerator,
    DeploymentGenerator,
    FormsGenerator,
    ModelsGenerator,
    SettingsGenerator,
    StaticGenerator,
    TemplatesGenerator,
    TestGenerator,
    UrlsGenerator,
    ViewsGenerator,
)
from .hooks import (
    CreateMigrationsHook,
    CreateSuperuserCredentialsHook,
    CreateSuperuserHook,
    DisplayDjangoInstructionsHook,
    RunMigrationsHook,
    SetupUvEnvironmentHook,
)


class DjangoMicroModularBackend(ModularBackend):
    """
    Production-ready modular Django Micro backend.

    Generates complete Django applications using a modular architecture with
    9 specialized generators, each handling a specific aspect of the application.

    This is now the default backend for DAZZLE, replacing the monolithic version.
    """

    def __init__(self):
        """Initialize backend and register hooks."""
        super().__init__()
        self.app_name = "app"
        self.register_hooks()

    def register_hooks(self):
        """Register pre/post-build hooks."""
        # Post-build hooks (order matters!)
        self.add_post_build_hook(CreateSuperuserCredentialsHook())  # 1. Generate credentials
        self.add_post_build_hook(SetupUvEnvironmentHook())  # 2. Create venv & install deps
        self.add_post_build_hook(CreateMigrationsHook())  # 3. Generate migration files
        self.add_post_build_hook(RunMigrationsHook())  # 4. Apply migrations
        self.add_post_build_hook(CreateSuperuserHook())  # 5. Create superuser
        self.add_post_build_hook(DisplayDjangoInstructionsHook())  # 6. Show instructions

    def get_generators(self, spec: ir.AppSpec, output_dir: Path, **options) -> list[Generator]:
        """
        Get list of generators to run.

        All 10 generators implemented:
        - ModelsGenerator, AdminGenerator, FormsGenerator
        - ViewsGenerator, UrlsGenerator, TemplatesGenerator
        - StaticGenerator, SettingsGenerator, DeploymentGenerator
        - TestGenerator
        """
        project_name = self._get_project_name(spec)
        project_path = output_dir / project_name

        return [
            ModelsGenerator(spec, project_path, self.app_name),
            AdminGenerator(spec, project_path, self.app_name),
            FormsGenerator(spec, project_path, self.app_name),
            ViewsGenerator(spec, project_path, self.app_name),
            UrlsGenerator(spec, project_path, project_name, self.app_name),
            TemplatesGenerator(spec, project_path, self.app_name),
            StaticGenerator(spec, project_path, self.app_name),
            SettingsGenerator(spec, project_path, project_name, self.app_name),
            DeploymentGenerator(spec, project_path, project_name),
            TestGenerator(spec, project_path, self.app_name),
        ]

    def generate(self, appspec: ir.AppSpec, output_dir: Path, **options) -> None:
        """
        Generate Django application with modular architecture.

        Generates a complete, production-ready Django application with:
        1. Models with proper primary keys
        2. Django Admin interface
        3. Forms (Create/Edit)
        4. Class-based views (List/Detail/Create/Update/Delete)
        5. URL routing
        6. HTML templates with responsive design
        7. CSS styling
        8. Django settings and configuration
        9. Deployment files (requirements.txt, Procfile, README.md)
        """
        # Create basic project structure first
        self._create_project_structure(appspec, output_dir)

        # Add normalized project name/path to options for hooks to use
        project_name = self._get_project_name(appspec)
        project_path = output_dir / project_name
        options["project_name"] = project_name
        options["project_path"] = project_path

        # Run the full modular generate workflow
        super().generate(appspec, output_dir, **options)

    def _create_project_structure(self, spec: ir.AppSpec, output_dir: Path):
        """
        Create basic Django project structure.
        """
        project_name = self._get_project_name(spec)
        project_root = output_dir / project_name

        # Create project directory
        project_dir = project_root / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "__init__.py").write_text("")

        # Create app directory
        app_dir = project_root / self.app_name
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "__init__.py").write_text("")

        # Create minimal apps.py
        apps_content = f"""from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = '{self.app_name}'
"""
        (app_dir / "apps.py").write_text(apps_content)

        # Create migrations directory
        migrations_dir = app_dir / "migrations"
        migrations_dir.mkdir(exist_ok=True)
        (migrations_dir / "__init__.py").write_text("")

        # Create static directory
        static_dir = app_dir / "static"
        static_dir.mkdir(exist_ok=True)

    def _get_project_name(self, spec: ir.AppSpec) -> str:
        """Get project name from spec."""
        # Use spec name, converting to valid Python identifier
        name = spec.name.lower().replace(" ", "_").replace("-", "_")
        # Remove any non-alphanumeric characters except underscore
        import re

        name = re.sub(r"[^\w]", "", name)
        return name or "app"

    def get_capabilities(self):
        """Return backend capabilities."""
        from .. import BackendCapabilities

        return BackendCapabilities(
            name="django_micro_modular",
            description="Django Micro - Complete Django application with modular architecture (Production Ready)",
            output_formats=["python"],
        )
