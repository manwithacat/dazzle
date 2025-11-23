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

from .admin import AdminGenerator
from .deployment import DeploymentGenerator
from .forms import FormsGenerator
from .models import ModelsGenerator
from .settings import SettingsGenerator
from .static import StaticGenerator
from .templates import TemplatesGenerator
from .tests import TestGenerator
from .urls import UrlsGenerator
from .views import ViewsGenerator

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
