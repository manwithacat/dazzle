"""
FastAPI server factory for DNR container runtime.

Creates and configures the FastAPI application with all routes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .auth import register_auth_routes
from .crud import register_crud_routes
from .pages import register_page_routes
from .test_routes import register_test_routes


def create_app(
    backend_spec: dict[str, Any],
    ui_spec: dict[str, Any],
    test_mode: bool = False,
    auth_enabled: bool = False,
    static_dir: Path | None = None,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        backend_spec: Backend specification dict
        ui_spec: UI specification dict
        test_mode: Enable test endpoints
        auth_enabled: Enable authentication endpoints
        static_dir: Directory containing static files

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title=backend_spec.get("name", "Dazzle API"),
        description="Auto-generated API from Dazzle DSL",
        version="1.0.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/health", tags=["System"], summary="Health check")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "mode": "docker"}

    # UI spec endpoint
    @app.get("/ui-spec", tags=["System"], summary="Get UI specification")
    async def get_ui_spec() -> dict[str, Any]:
        """Return the UI specification."""
        return ui_spec

    # Entity CRUD routes
    entities = backend_spec.get("entities", [])
    register_crud_routes(app, entities)

    # Authentication routes
    if auth_enabled:
        register_auth_routes(app)

    # Test mode routes
    if test_mode:
        register_test_routes(app, auth_enabled=auth_enabled)

    # Static page routes
    register_page_routes(app, ui_spec)

    # Static files / UI serving
    if static_dir and static_dir.exists():
        _register_static_routes(app, static_dir)

    return app


def _register_static_routes(app: FastAPI, static_dir: Path) -> None:
    """Register static file serving routes."""

    @app.get("/", response_class=HTMLResponse)
    async def serve_ui() -> str:
        return (static_dir / "index.html").read_text()

    @app.get("/{path:path}")
    async def serve_static(path: str) -> FileResponse | HTMLResponse:
        file_path = static_dir / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        # SPA fallback
        return HTMLResponse((static_dir / "index.html").read_text())


def load_specs(
    backend_spec_path: Path,
    ui_spec_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Load backend and UI specs from JSON files.

    Args:
        backend_spec_path: Path to backend_spec.json
        ui_spec_path: Path to ui_spec.json

    Returns:
        Tuple of (backend_spec, ui_spec)
    """
    with open(backend_spec_path) as f:
        backend_spec = json.load(f)
    with open(ui_spec_path) as f:
        ui_spec = json.load(f)
    return backend_spec, ui_spec
