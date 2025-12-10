"""
FastAPI backend adapter.

This module re-exports the modular FastAPI adapter from the fastapi_impl package.
The implementation has been split into smaller, focused modules for better
maintainability and LLM context handling.

For implementation details, see the fastapi_impl/ package:
- fastapi_impl/models.py - SQLAlchemy model generation
- fastapi_impl/schemas.py - Pydantic schema generation
- fastapi_impl/routers.py - API router generation
- fastapi_impl/services.py - Business logic service generation
- fastapi_impl/guards.py - State machine guard generation
- fastapi_impl/validators.py - Invariant validator generation
- fastapi_impl/access.py - Access control policy generation
- fastapi_impl/app.py - Application entry point and config generation
- fastapi_impl/utils.py - Shared utilities
"""

# Re-export everything from the fastapi_impl package for backwards compatibility
from .fastapi_impl import (
    FastAPIAdapter,
    TYPE_MAPPING,
    snake_case,
    pascal_case,
)

__all__ = [
    "FastAPIAdapter",
    "TYPE_MAPPING",
    "snake_case",
    "pascal_case",
]
