"""
DNR Container Runtime Package.

This package contains the Python code that runs inside the Docker container.
It replaces the previous approach of embedding code as string templates.

Usage:
    python -m dazzle_ui.runtime.container
"""

from __future__ import annotations

from .auth import (
    AUTH_SESSIONS,
    AUTH_USERS,
    clear_auth_data,
    get_auth_stats,
    hash_password,
    register_auth_routes,
    verify_password,
)
from .config import ContainerConfig
from .crud import register_crud_routes
from .data_store import DataStore, data_store
from .markdown import markdown_to_html
from .pages import register_page_routes
from .server import create_app, load_specs
from .test_routes import register_test_routes

__all__ = [
    # Config
    "ContainerConfig",
    # Data store
    "DataStore",
    "data_store",
    # Server
    "create_app",
    "load_specs",
    # Routes
    "register_crud_routes",
    "register_auth_routes",
    "register_page_routes",
    "register_test_routes",
    # Auth utilities
    "AUTH_USERS",
    "AUTH_SESSIONS",
    "hash_password",
    "verify_password",
    "clear_auth_data",
    "get_auth_stats",
    # Markdown
    "markdown_to_html",
]
