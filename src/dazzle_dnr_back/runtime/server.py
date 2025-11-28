"""
Runtime server - creates and runs a FastAPI application from BackendSpec.

This module provides the main entry point for running a DNR-Back application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel

from dazzle_dnr_back.specs import BackendSpec
from dazzle_dnr_back.runtime.model_generator import (
    generate_all_entity_models,
    generate_create_schema,
    generate_update_schema,
)
from dazzle_dnr_back.runtime.service_generator import ServiceFactory

# FastAPI is optional - use TYPE_CHECKING for type hints
if TYPE_CHECKING:
    from fastapi import FastAPI

# Runtime import
try:
    from fastapi import FastAPI as _FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from dazzle_dnr_back.runtime.route_generator import RouteGenerator

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    _FastAPI = None  # type: ignore
    CORSMiddleware = None  # type: ignore
    RouteGenerator = None  # type: ignore


# =============================================================================
# Application Builder
# =============================================================================


class DNRBackendApp:
    """
    DNR Backend Application.

    Creates a complete FastAPI application from a BackendSpec.
    """

    def __init__(self, spec: BackendSpec):
        """
        Initialize the backend application.

        Args:
            spec: Backend specification
        """
        if not FASTAPI_AVAILABLE:
            raise RuntimeError(
                "FastAPI is not installed. Install with: pip install fastapi uvicorn"
            )

        self.spec = spec
        self._app: Optional[FastAPI] = None
        self._models: dict[str, type[BaseModel]] = {}
        self._schemas: dict[str, dict[str, type[BaseModel]]] = {}
        self._services: dict[str, Any] = {}

    def build(self) -> FastAPI:
        """
        Build the FastAPI application.

        Returns:
            FastAPI application instance
        """
        # Create FastAPI app
        self._app = _FastAPI(
            title=self.spec.name,
            description=self.spec.description or f"DNR Backend: {self.spec.name}",
            version=self.spec.version,
        )

        # Add CORS middleware
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Generate models
        self._models = generate_all_entity_models(self.spec.entities)

        # Generate schemas (create/update)
        for entity in self.spec.entities:
            self._schemas[entity.name] = {
                "create": generate_create_schema(entity),
                "update": generate_update_schema(entity),
            }

        # Create services
        factory = ServiceFactory(self._models)
        self._services = factory.create_all_services(
            self.spec.services,
            self._schemas,
        )

        # Generate routes
        service_specs = {svc.name: svc for svc in self.spec.services}
        route_generator = RouteGenerator(
            services=self._services,
            models=self._models,
            schemas=self._schemas,
        )
        router = route_generator.generate_all_routes(
            self.spec.endpoints,
            service_specs,
        )

        # Include router
        self._app.include_router(router)

        # Add health check
        @self._app.get("/health", tags=["System"])
        async def health_check() -> dict[str, str]:
            return {"status": "healthy", "app": self.spec.name}

        # Add spec endpoint
        @self._app.get("/spec", tags=["System"])
        async def get_spec() -> dict[str, Any]:
            return self.spec.model_dump()

        return self._app

    @property
    def app(self) -> Optional[FastAPI]:
        """Get the FastAPI application (None if not built)."""
        return self._app

    @property
    def models(self) -> dict[str, type[BaseModel]]:
        """Get generated Pydantic models."""
        return self._models

    @property
    def services(self) -> dict[str, Any]:
        """Get service instances."""
        return self._services

    def get_service(self, name: str) -> Any | None:
        """Get a service by name."""
        return self._services.get(name)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_app(spec: BackendSpec) -> FastAPI:
    """
    Create a FastAPI application from a BackendSpec.

    This is the main entry point for creating a DNR-Back application.

    Args:
        spec: Backend specification

    Returns:
        FastAPI application

    Example:
        >>> from dazzle_dnr_back.specs import BackendSpec
        >>> spec = BackendSpec(name="my_app", ...)
        >>> app = create_app(spec)
        >>> # Run with uvicorn: uvicorn mymodule:app
    """
    builder = DNRBackendApp(spec)
    return builder.build()


def run_app(
    spec: BackendSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """
    Run a DNR-Back application.

    Args:
        spec: Backend specification
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload (for development)

    Example:
        >>> from dazzle_dnr_back.specs import BackendSpec
        >>> spec = BackendSpec(name="my_app", ...)
        >>> run_app(spec)  # Starts server on http://127.0.0.1:8000
    """
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn is not installed. Install with: pip install uvicorn")

    app = create_app(spec)
    uvicorn.run(app, host=host, port=port, reload=reload)


# =============================================================================
# App from JSON/Dict
# =============================================================================


def create_app_from_dict(spec_dict: dict[str, Any]) -> FastAPI:
    """
    Create a FastAPI application from a dictionary specification.

    Useful for loading specs from JSON files or API responses.

    Args:
        spec_dict: Dictionary representation of BackendSpec

    Returns:
        FastAPI application
    """
    spec = BackendSpec.model_validate(spec_dict)
    return create_app(spec)


def create_app_from_json(json_path: str) -> FastAPI:
    """
    Create a FastAPI application from a JSON file.

    Args:
        json_path: Path to JSON file containing BackendSpec

    Returns:
        FastAPI application
    """
    import json
    from pathlib import Path

    spec_dict = json.loads(Path(json_path).read_text())
    return create_app_from_dict(spec_dict)
