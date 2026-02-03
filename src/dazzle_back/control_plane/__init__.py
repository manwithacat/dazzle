"""
Dazzle Control Plane - Built-in observability dashboard.

Provides metrics, logs, and process monitoring for Dazzle applications.
Can be deployed as a separate dyno/service or integrated into the main app.
"""

from __future__ import annotations

from .app import create_app, create_app_factory

__all__ = [
    "create_app",
    "create_app_factory",
]
