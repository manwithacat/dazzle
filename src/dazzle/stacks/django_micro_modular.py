"""
Django Micro Modular Backend - Entry point for auto-discovery.

This module exports the modular Django Micro backend for the backend registry.
The actual implementation is in django_micro_modular/ subdirectory.
"""

from .django_micro_modular import DjangoMicroModularBackend

__all__ = ["DjangoMicroModularBackend"]
