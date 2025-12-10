"""
DNR (Dazzle Native Runtime) CLI commands.

This package provides commands for generating and serving runtime apps using DNR.
The monolithic dnr.py has been split into focused modules:

- build.py: Build commands (build-ui, build-api, build, migrate)
- serve.py: Development server (serve)
- lifecycle.py: Container management (stop, rebuild, logs, status)
- inspect.py: Inspection commands (inspect)
- info.py: Status display (info)
- test.py: Testing (test)
- docker.py: Docker/container utilities
"""

from __future__ import annotations

import typer

from .build import dnr_build, dnr_build_api, dnr_build_ui, dnr_migrate
from .info import dnr_info
from .inspect import dnr_inspect
from .lifecycle import dnr_logs, dnr_rebuild, dnr_status, dnr_stop
from .serve import dnr_serve
from .test import dnr_test

# Create the typer app
dnr_app = typer.Typer(
    help="Dazzle Native Runtime (DNR) commands for generating and serving runtime apps.",
    no_args_is_help=True,
)

# Register all commands
dnr_app.command("build-ui")(dnr_build_ui)
dnr_app.command("build-api")(dnr_build_api)
dnr_app.command("migrate")(dnr_migrate)
dnr_app.command("build")(dnr_build)
dnr_app.command("serve")(dnr_serve)
dnr_app.command("info")(dnr_info)
dnr_app.command("stop")(dnr_stop)
dnr_app.command("rebuild")(dnr_rebuild)
dnr_app.command("logs")(dnr_logs)
dnr_app.command("status")(dnr_status)
dnr_app.command("inspect")(dnr_inspect)
dnr_app.command("test")(dnr_test)

__all__ = [
    "dnr_app",
    # Build commands
    "dnr_build_ui",
    "dnr_build_api",
    "dnr_migrate",
    "dnr_build",
    # Serve
    "dnr_serve",
    # Lifecycle
    "dnr_stop",
    "dnr_rebuild",
    "dnr_logs",
    "dnr_status",
    # Inspect
    "dnr_inspect",
    # Info
    "dnr_info",
    # Test
    "dnr_test",
]
