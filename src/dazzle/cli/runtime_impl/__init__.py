"""
Dazzle Runtime CLI commands.

This package provides commands for generating and serving runtime apps.
The modules are:

- build.py: Build commands (build-ui, build-api, build, migrate)
- serve.py: Development server (serve)
- inspect.py: Inspection commands (schema)
- info.py: Status display (info)
- test.py: Testing (check)
"""

from .build import (
    build_api_command,
    build_command,
    build_css_command,
    build_ui_command,
    migrate_command,
)
from .info import info_command
from .inspect import schema_command
from .serve import serve_command
from .test import check_command

__all__ = [
    # Build commands
    "build_ui_command",
    "build_api_command",
    "build_css_command",
    "migrate_command",
    "build_command",
    # Serve
    "serve_command",
    # Inspect
    "schema_command",
    # Info
    "info_command",
    # Test
    "check_command",
]
