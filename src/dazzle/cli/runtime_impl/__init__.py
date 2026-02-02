"""
Dazzle Runtime CLI commands.

This package provides commands for generating and serving runtime apps.
The modules are:

- build.py: Build commands (build-ui, build-api, build, migrate)
- serve.py: Development server (serve)
- lifecycle.py: Container management (stop, rebuild, logs, status)
- inspect.py: Inspection commands (schema)
- info.py: Status display (info)
- test.py: Testing (check)
- docker.py: Docker/container utilities
"""

from __future__ import annotations

from .build import build_api_command, build_command, build_ui_command, migrate_command
from .info import info_command
from .inspect import schema_command
from .lifecycle import logs_command, rebuild_command, status_command, stop_command
from .serve import serve_command
from .test import check_command

__all__ = [
    # Build commands
    "build_ui_command",
    "build_api_command",
    "migrate_command",
    "build_command",
    # Serve
    "serve_command",
    # Lifecycle
    "stop_command",
    "rebuild_command",
    "logs_command",
    "status_command",
    # Inspect
    "schema_command",
    # Info
    "info_command",
    # Test
    "check_command",
]
