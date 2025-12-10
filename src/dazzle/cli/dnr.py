"""
DNR (Dazzle Native Runtime) CLI commands.

This module re-exports the modular DNR commands from the dnr_impl package.
The implementation has been split into smaller, focused modules for better
maintainability and LLM context handling.

For implementation details, see the dnr_impl/ package:
- dnr_impl/build.py - Build commands (build-ui, build-api, build, migrate)
- dnr_impl/serve.py - Development server (serve)
- dnr_impl/lifecycle.py - Container management (stop, rebuild, logs, status)
- dnr_impl/inspect.py - Inspection commands (inspect)
- dnr_impl/info.py - Status display (info)
- dnr_impl/test.py - Testing (test)
- dnr_impl/docker.py - Docker/container utilities
"""

# Re-export everything from the dnr_impl package for backwards compatibility
from .dnr_impl import (
    dnr_app,
    dnr_build,
    dnr_build_api,
    dnr_build_ui,
    dnr_info,
    dnr_inspect,
    dnr_logs,
    dnr_migrate,
    dnr_rebuild,
    dnr_serve,
    dnr_status,
    dnr_stop,
    dnr_test,
)

__all__ = [
    "dnr_app",
    "dnr_build",
    "dnr_build_api",
    "dnr_build_ui",
    "dnr_info",
    "dnr_inspect",
    "dnr_logs",
    "dnr_migrate",
    "dnr_rebuild",
    "dnr_serve",
    "dnr_status",
    "dnr_stop",
    "dnr_test",
]
