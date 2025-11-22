"""
Generators for Django Micro backend.

Each generator creates specific artifacts:
- ModelsGenerator: Django models (models.py)
- FormsGenerator: Django forms (forms.py)
- ViewsGenerator: Views and business logic (views.py)
- UrlsGenerator: URL routing (urls.py)
- TemplatesGenerator: HTML templates
- SettingsGenerator: Django settings
- AdminGenerator: Admin configuration
- DeploymentGenerator: Deployment configs
- TestGenerator: Test suite (tests/)
"""

from .models import ModelsGenerator
from .admin import AdminGenerator
from .forms import FormsGenerator
from .views import ViewsGenerator
from .urls import UrlsGenerator
from .templates import TemplatesGenerator
from .static import StaticGenerator
from .settings import SettingsGenerator
from .deployment import DeploymentGenerator
from .tests import TestGenerator

__all__ = [
    "ModelsGenerator",
    "AdminGenerator",
    "FormsGenerator",
    "ViewsGenerator",
    "UrlsGenerator",
    "TemplatesGenerator",
    "StaticGenerator",
    "SettingsGenerator",
    "DeploymentGenerator",
    "TestGenerator",
]
