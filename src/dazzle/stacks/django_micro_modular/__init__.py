"""
Django Micro Backend - Modular Architecture

Generates a complete single-file Django application with:
- Models, views, forms, templates
- Django Admin interface
- SQLite database
- Easy deployment configuration

This is a refactored version using the modular backend architecture.
"""

from .backend import DjangoMicroModularBackend

__all__ = ["DjangoMicroModularBackend"]
