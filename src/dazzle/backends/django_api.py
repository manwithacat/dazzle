"""
Django REST Framework backend for DAZZLE.

Generates a complete Django project with DRF from AppSpec.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import textwrap

from . import Backend, BackendCapabilities
from ..core import ir
from ..core.errors import BackendError


class DjangoAPIBackend(Backend):
    """
    Generate Django REST Framework API from DAZZLE AppSpec.

    Maps DAZZLE concepts to Django/DRF:
    - Entities → Django models (models.py)
    - Entities → DRF serializers (serializers.py)
    - Surfaces → DRF ViewSets (views.py)
    - Relationships → ForeignKey, ManyToManyField
    """

    def get_capabilities(self) -> BackendCapabilities:
        """Get backend capabilities."""
        return BackendCapabilities(
            name="django_api",
            description="Generate Django REST Framework API with models, serializers, and viewsets",
            output_formats=["django"],
            supports_incremental=False,
            requires_config=False,
        )

    def generate(self, appspec: ir.AppSpec, output_dir: Path, **options) -> None:
        """
        Generate Django project structure.

        Args:
            appspec: Validated application specification
            output_dir: Output directory for Django project
            **options: Additional options

        Raises:
            BackendError: If generation fails
        """
        try:
            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)

            # Generate project structure
            self._generate_project_structure(appspec, output_dir)
            self._generate_models(appspec, output_dir)
            self._generate_serializers(appspec, output_dir)
            self._generate_viewsets(appspec, output_dir)
            self._generate_urls(appspec, output_dir)
            self._generate_settings(appspec, output_dir)
            self._generate_requirements(appspec, output_dir)
            self._generate_manage_py(appspec, output_dir)
            self._generate_readme(appspec, output_dir)

        except Exception as e:
            if isinstance(e, BackendError):
                raise
            raise BackendError(f"Failed to generate Django API: {e}")

    def _generate_project_structure(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Create Django project directory structure."""
        # Create main project directory
        project_dir = output_dir / "config"
        project_dir.mkdir(exist_ok=True)

        # Create app directory
        app_dir = output_dir / "api"
        app_dir.mkdir(exist_ok=True)

        # Create migrations directory
        migrations_dir = app_dir / "migrations"
        migrations_dir.mkdir(exist_ok=True)

        # Create __init__.py files
        (project_dir / "__init__.py").write_text("", encoding="utf-8")
        (app_dir / "__init__.py").write_text("", encoding="utf-8")
        (migrations_dir / "__init__.py").write_text("", encoding="utf-8")

    def _generate_models(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Generate Django models from entities."""
        app_dir = output_dir / "api"
        models_file = app_dir / "models.py"

        lines = [
            '"""',
            "Django models generated from DAZZLE AppSpec.",
            '"""',
            "",
            "import uuid",
            "from django.db import models",
            "",
            "",
        ]

        # Generate model for each entity
        for entity in appspec.domain.entities:
            lines.extend(self._generate_entity_model(entity, appspec))
            lines.append("")

        models_file.write_text("\n".join(lines), encoding="utf-8")

    def _generate_entity_model(self, entity: ir.EntitySpec, appspec: ir.AppSpec) -> List[str]:
        """Generate Django model class for an entity."""
        lines = []

        # Class definition
        class_name = self._to_class_name(entity.name)
        lines.append(f"class {class_name}(models.Model):")

        # Docstring
        lines.append(f'    """{entity.title or entity.name} model."""')
        lines.append("")

        # Fields
        has_fields = False
        for field in entity.fields:
            field_def = self._generate_model_field(field, entity, appspec)
            if field_def:
                lines.append(f"    {field_def}")
                has_fields = True

        if not has_fields:
            lines.append("    pass")

        # Meta class
        lines.append("")
        lines.append("    class Meta:")
        lines.append(f'        db_table = "{self._to_table_name(entity.name)}"')
        lines.append(f'        verbose_name = "{entity.title or entity.name}"')
        lines.append(f'        verbose_name_plural = "{entity.title or entity.name}s"')

        # Add ordering if created_at exists
        if any(f.name == "created_at" for f in entity.fields):
            lines.append('        ordering = ["-created_at"]')

        # __str__ method
        lines.append("")
        lines.append("    def __str__(self):")

        # Try to find a good string representation field
        str_field = None
        for field_name in ["title", "name", "email"]:
            if any(f.name == field_name for f in entity.fields):
                str_field = field_name
                break

        if str_field:
            lines.append(f'        return str(self.{str_field})')
        else:
            lines.append(f'        return f"{class_name} {{self.pk}}"')

        return lines

    def _generate_model_field(
        self, field: ir.FieldSpec, entity: ir.EntitySpec, appspec: ir.AppSpec
    ) -> Optional[str]:
        """Generate Django field definition."""
        field_name = field.name
        field_type = field.type

        # Handle primary key
        if field.is_primary_key:
            if field_type.kind == ir.FieldTypeKind.UUID:
                return f'{field_name} = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)'
            elif field_type.kind == ir.FieldTypeKind.INT:
                return f'{field_name} = models.AutoField(primary_key=True)'
            else:
                return f'{field_name} = models.BigIntegerField(primary_key=True)'

        # Build field kwargs
        kwargs = []

        # Handle nullability
        if not field.is_required:
            kwargs.append("null=True")
            kwargs.append("blank=True")

        # Handle uniqueness
        if field.is_unique:
            kwargs.append("unique=True")

        # Handle auto timestamps
        if ir.FieldModifier.AUTO_ADD in field.modifiers:
            kwargs.append("auto_now_add=True")
        if ir.FieldModifier.AUTO_UPDATE in field.modifiers:
            kwargs.append("auto_now=True")

        # Handle default values
        if field.default is not None:
            if isinstance(field.default, str):
                kwargs.append(f'default="{field.default}"')
            else:
                kwargs.append(f'default={field.default}')

        # Map field type to Django field
        django_field = self._map_field_type(field_type, kwargs)

        kwargs_str = ", ".join(kwargs) if kwargs else ""
        return f"{field_name} = {django_field}({kwargs_str})"

    def _map_field_type(self, field_type: ir.FieldType, kwargs: List[str]) -> str:
        """Map DAZZLE field type to Django field type."""
        kind = field_type.kind

        if kind == ir.FieldTypeKind.STR:
            max_length = field_type.max_length or 255
            kwargs.insert(0, f"max_length={max_length}")
            return "models.CharField"

        elif kind == ir.FieldTypeKind.TEXT:
            return "models.TextField"

        elif kind == ir.FieldTypeKind.INT:
            return "models.IntegerField"

        elif kind == ir.FieldTypeKind.DECIMAL:
            precision = field_type.precision or 10
            scale = field_type.scale or 2
            kwargs.insert(0, f"max_digits={precision}")
            kwargs.insert(1, f"decimal_places={scale}")
            return "models.DecimalField"

        elif kind == ir.FieldTypeKind.BOOL:
            return "models.BooleanField"

        elif kind == ir.FieldTypeKind.DATE:
            return "models.DateField"

        elif kind == ir.FieldTypeKind.DATETIME:
            return "models.DateTimeField"

        elif kind == ir.FieldTypeKind.UUID:
            kwargs.insert(0, "default=uuid.uuid4")
            return "models.UUIDField"

        elif kind == ir.FieldTypeKind.EMAIL:
            return "models.EmailField"

        elif kind == ir.FieldTypeKind.ENUM:
            # Generate choices from enum values
            if field_type.enum_values:
                choices = ", ".join([f'("{val}", "{val.replace("_", " ").title()}")'
                                    for val in field_type.enum_values])
                # Note: choices need to be defined at class level, this is simplified
                kwargs.insert(0, f"choices=[{choices}]")
                kwargs.insert(1, f'max_length={max(len(v) for v in field_type.enum_values) + 10}')
            return "models.CharField"

        elif kind == ir.FieldTypeKind.REF:
            # Foreign key relationship
            if field_type.ref_entity:
                ref_class = self._to_class_name(field_type.ref_entity)
                kwargs.insert(0, f'"{ref_class}"')
                kwargs.insert(1, 'on_delete=models.CASCADE')
                return "models.ForeignKey"
            return "models.IntegerField"

        else:
            # Default to CharField for unknown types
            kwargs.insert(0, "max_length=255")
            return "models.CharField"

    def _generate_serializers(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Generate DRF serializers."""
        app_dir = output_dir / "api"
        serializers_file = app_dir / "serializers.py"

        lines = [
            '"""',
            "Django REST Framework serializers.",
            '"""',
            "",
            "from rest_framework import serializers",
            "from .models import " + ", ".join([self._to_class_name(e.name) for e in appspec.domain.entities]),
            "",
            "",
        ]

        # Generate serializer for each entity
        for entity in appspec.domain.entities:
            lines.extend(self._generate_entity_serializer(entity))
            lines.append("")

        serializers_file.write_text("\n".join(lines), encoding="utf-8")

    def _generate_entity_serializer(self, entity: ir.EntitySpec) -> List[str]:
        """Generate DRF serializer for an entity."""
        class_name = self._to_class_name(entity.name)
        lines = []

        lines.append(f"class {class_name}Serializer(serializers.ModelSerializer):")
        lines.append(f'    """{entity.title or entity.name} serializer."""')
        lines.append("")
        lines.append("    class Meta:")
        lines.append(f"        model = {class_name}")
        lines.append("        fields = '__all__'")

        # Add read-only fields for auto fields
        read_only = []
        for field in entity.fields:
            if (ir.FieldModifier.AUTO_ADD in field.modifiers or
                ir.FieldModifier.AUTO_UPDATE in field.modifiers or
                field.is_primary_key):
                read_only.append(f"'{field.name}'")

        if read_only:
            lines.append(f"        read_only_fields = [{', '.join(read_only)}]")

        return lines

    def _generate_viewsets(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Generate DRF viewsets from surfaces."""
        app_dir = output_dir / "api"
        views_file = app_dir / "views.py"

        lines = [
            '"""',
            "Django REST Framework viewsets.",
            '"""',
            "",
            "from rest_framework import viewsets, filters",
            "from rest_framework.decorators import action",
            "from rest_framework.response import Response",
            "from django_filters.rest_framework import DjangoFilterBackend",
            "",
            "from .models import " + ", ".join([self._to_class_name(e.name) for e in appspec.domain.entities]),
            "from .serializers import " + ", ".join([f"{self._to_class_name(e.name)}Serializer"
                                                      for e in appspec.domain.entities]),
            "",
            "",
        ]

        # Group surfaces by entity
        entity_surfaces: Dict[str, List[ir.SurfaceSpec]] = {}
        for surface in appspec.surfaces:
            if surface.entity_ref:
                if surface.entity_ref not in entity_surfaces:
                    entity_surfaces[surface.entity_ref] = []
                entity_surfaces[surface.entity_ref].append(surface)

        # Generate viewset for each entity
        for entity_name, surfaces in entity_surfaces.items():
            entity = appspec.get_entity(entity_name)
            if entity:
                lines.extend(self._generate_entity_viewset(entity, surfaces, appspec))
                lines.append("")

        views_file.write_text("\n".join(lines), encoding="utf-8")

    def _generate_entity_viewset(
        self, entity: ir.EntitySpec, surfaces: List[ir.SurfaceSpec], appspec: ir.AppSpec
    ) -> List[str]:
        """Generate DRF viewset for an entity."""
        class_name = self._to_class_name(entity.name)
        lines = []

        lines.append(f"class {class_name}ViewSet(viewsets.ModelViewSet):")
        lines.append(f'    """{entity.title or entity.name} viewset."""')
        lines.append("")
        lines.append(f"    queryset = {class_name}.objects.all()")
        lines.append(f"    serializer_class = {class_name}Serializer")
        lines.append("    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]")

        # Add filterable fields (all simple fields)
        filterable = []
        searchable = []
        for field in entity.fields:
            if field.type.kind in [ir.FieldTypeKind.STR, ir.FieldTypeKind.TEXT, ir.FieldTypeKind.EMAIL]:
                searchable.append(field.name)
            if field.type.kind not in [ir.FieldTypeKind.TEXT]:
                filterable.append(field.name)

        if filterable:
            lines.append(f"    filterset_fields = {filterable}")
        if searchable:
            lines.append(f"    search_fields = {searchable}")
        lines.append(f"    ordering_fields = '__all__'")

        return lines

    def _generate_urls(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Generate URL routing."""
        app_dir = output_dir / "api"
        urls_file = app_dir / "urls.py"

        lines = [
            '"""',
            "API URL routing.",
            '"""',
            "",
            "from django.urls import path, include",
            "from rest_framework.routers import DefaultRouter",
            "",
            "from . import views",
            "",
            "",
            "router = DefaultRouter()",
            "",
        ]

        # Register viewsets
        for entity in appspec.domain.entities:
            class_name = self._to_class_name(entity.name)
            url_prefix = self._to_url_prefix(entity.name)
            lines.append(f'router.register(r"{url_prefix}", views.{class_name}ViewSet, basename="{entity.name}")')

        lines.extend([
            "",
            "urlpatterns = [",
            "    path('', include(router.urls)),",
            "]",
        ])

        urls_file.write_text("\n".join(lines), encoding="utf-8")

    def _generate_settings(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Generate Django settings.py."""
        project_dir = output_dir / "config"
        settings_file = project_dir / "settings.py"

        app_name = appspec.name

        content = f'''"""
Django settings for {app_name}.

Generated by DAZZLE.
"""

import os
from pathlib import Path

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-CHANGE-ME-IN-PRODUCTION')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'django_filters',
    'corsheaders',

    # Local apps
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {{
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        }},
    }},
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {{
    'default': {{
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', '{app_name}_db'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }}
}}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}},
    {{'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'}},
    {{'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}},
    {{'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {{
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}}

# CORS settings
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:3000').split(',')
'''

        settings_file.write_text(content, encoding="utf-8")

        # Generate WSGI file
        wsgi_file = project_dir / "wsgi.py"
        wsgi_content = '''"""
WSGI config.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
'''
        wsgi_file.write_text(wsgi_content, encoding="utf-8")

        # Generate ASGI file
        asgi_file = project_dir / "asgi.py"
        asgi_content = '''"""
ASGI config.

It exposes the ASGI callable as a module-level variable named ``application``.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()
'''
        asgi_file.write_text(asgi_content, encoding="utf-8")

        # Generate main URLs
        urls_file = project_dir / "urls.py"
        urls_content = '''"""
Main URL configuration.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]
'''
        urls_file.write_text(urls_content, encoding="utf-8")

    def _generate_requirements(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Generate requirements.txt."""
        requirements_file = output_dir / "requirements.txt"

        requirements = [
            "Django>=4.2,<5.0",
            "djangorestframework>=3.14,<4.0",
            "django-filter>=23.0",
            "django-cors-headers>=4.0",
            "psycopg2-binary>=2.9",
            "python-dotenv>=1.0",
        ]

        requirements_file.write_text("\n".join(requirements) + "\n", encoding="utf-8")

    def _generate_manage_py(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Generate manage.py."""
        manage_file = output_dir / "manage.py"

        content = '''#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
'''

        manage_file.write_text(content, encoding="utf-8")

        # Make executable on Unix systems
        try:
            import stat
            manage_file.chmod(manage_file.stat().st_mode | stat.S_IEXEC)
        except Exception:
            pass  # Windows or permission error

    def _generate_readme(self, appspec: ir.AppSpec, output_dir: Path) -> None:
        """Generate README with setup instructions."""
        readme_file = output_dir / "README.md"

        app_name = appspec.title or appspec.name

        content = f'''# {app_name} - Django REST API

Generated by DAZZLE.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure database

Create a PostgreSQL database and set environment variables:

```bash
export DB_NAME={app_name.lower().replace(" ", "_")}_db
export DB_USER=postgres
export DB_PASSWORD=postgres
export DB_HOST=localhost
export DB_PORT=5432
```

Or create a `.env` file:

```
DB_NAME={app_name.lower().replace(" ", "_")}_db
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
SECRET_KEY=your-secret-key-here
DEBUG=True
```

### 3. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Create superuser (optional)

```bash
python manage.py createsuperuser
```

### 5. Run development server

```bash
python manage.py runserver
```

The API will be available at: http://localhost:8000/api/

## API Endpoints

The following resources are available:

'''

        # List endpoints
        for entity in appspec.domain.entities:
            url_prefix = self._to_url_prefix(entity.name)
            content += f"- `GET/POST /api/{url_prefix}/` - List/Create {entity.title or entity.name}\n"
            content += f"- `GET/PUT/PATCH/DELETE /api/{url_prefix}/{{id}}/` - Retrieve/Update/Delete {entity.title or entity.name}\n"
            content += "\n"

        content += '''
## Admin Interface

Access the Django admin at: http://localhost:8000/admin/

## Project Structure

```
.
├── manage.py              # Django management script
├── requirements.txt       # Python dependencies
├── config/               # Django project settings
│   ├── settings.py       # Main settings
│   ├── urls.py          # Root URL configuration
│   ├── wsgi.py          # WSGI application
│   └── asgi.py          # ASGI application
└── api/                  # Main API app
    ├── models.py         # Database models
    ├── serializers.py    # DRF serializers
    ├── views.py          # API viewsets
    ├── urls.py           # API URL routing
    └── migrations/       # Database migrations
```

## Development

### Run tests

```bash
python manage.py test
```

### Create new migration

```bash
python manage.py makemigrations
```

### Apply migrations

```bash
python manage.py migrate
```

### Access Django shell

```bash
python manage.py shell
```

## Working with AI Assistants

This project was generated by DAZZLE and includes LLM context files to help AI assistants understand the codebase:

- **LLM_CONTEXT.md** - Overview of the project structure and workflow
- **.llm/DAZZLE_PRIMER.md** - Deep dive into DAZZLE concepts
- **.claude/** - Claude-specific context and permissions
- **.copilot/** - GitHub Copilot context

### Important Rules for AI Assistants

1. **Source of Truth**: The DSL files in `dsl/` define the application structure. This Django code is generated from those files.
2. **Never Edit Generated Code Directly**: Always modify the DSL files and rebuild using `dazzle build` instead of editing this Django code.
3. **Safe Commands**: You can safely run `python manage.py` commands, `dazzle validate`, `dazzle build`, and git operations.
4. **Rebuild After Changes**: After modifying DSL files, run `dazzle build` to regenerate this code.

For more information, see the `LLM_CONTEXT.md` file in the project root.
'''

        readme_file.write_text(content, encoding="utf-8")

    # Helper methods

    def _to_class_name(self, name: str) -> str:
        """Convert entity name to PascalCase class name."""
        return "".join(word.capitalize() for word in name.split("_"))

    def _to_table_name(self, name: str) -> str:
        """Convert entity name to database table name."""
        return name.lower()

    def _to_url_prefix(self, name: str) -> str:
        """Convert entity name to URL prefix."""
        # Convert to plural
        if name.endswith('y'):
            return name[:-1] + 'ies'
        elif name.endswith('s'):
            return name + 'es'
        else:
            return name + 's'
