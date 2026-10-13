"""
Dazzle Runtime CLI commands.

This package provides commands for generating and serving runtime apps.
The modules are:

- build.py: Build commands (build-ui, build-api, build, migrate)
- serve.py: Development server (serve)
"""

from .build import (
    build_api_command,
    build_command,
    build_ui_command,
    migrate_command,
)
from .serve import serve_command

__all__ = [
    # Build commands
    "build_ui_command",
    "build_api_command",
    "migrate_command",
    "build_command",
    # Serve
    "serve_command",
]
