"""
Container configuration from environment variables.

This module reads configuration from environment variables at runtime,
eliminating the need for code templating.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ContainerConfig:
    """Configuration for the DNR container runtime."""

    api_port: int
    frontend_port: int
    host: str
    db_path: Path
    test_mode: bool
    auth_enabled: bool
    auth_db_path: Path
    backend_spec_path: Path
    ui_spec_path: Path

    @classmethod
    def from_env(cls) -> ContainerConfig:
        """Load configuration from environment variables."""
        return cls(
            api_port=int(os.environ.get("DNR_API_PORT", "8000")),
            frontend_port=int(os.environ.get("DNR_FRONTEND_PORT", "3000")),
            host=os.environ.get("DNR_HOST", "0.0.0.0"),
            db_path=Path(os.environ.get("DNR_DB_PATH", "/app/.dazzle/data.db")),
            test_mode=os.environ.get("DNR_TEST_MODE", "0") == "1",
            auth_enabled=os.environ.get("DNR_AUTH_ENABLED", "0") == "1",
            auth_db_path=Path(os.environ.get("DNR_AUTH_DB_PATH", "/app/.dazzle/auth.db")),
            backend_spec_path=Path(os.environ.get("DNR_BACKEND_SPEC", "backend_spec.json")),
            ui_spec_path=Path(os.environ.get("DNR_UI_SPEC", "ui_spec.json")),
        )
