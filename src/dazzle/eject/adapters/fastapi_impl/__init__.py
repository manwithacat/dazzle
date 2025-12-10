"""
FastAPI backend adapter.

Generates a complete FastAPI application from AppSpec including:
- Pydantic models and schemas
- CRUD routers with proper typing
- State machine guards
- Invariant validators
- Access control policies

This package contains the modular implementation split into:
- models.py - SQLAlchemy model generation
- schemas.py - Pydantic schema generation
- routers.py - API router generation
- services.py - Business logic service generation
- guards.py - State machine guard generation
- validators.py - Invariant validator generation
- access.py - Access control policy generation
- app.py - Application entry point and config generation
- utils.py - Shared utilities
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.eject.adapters.base import AdapterRegistry, BackendAdapter
from dazzle.eject.generator import GeneratorResult

from .access import AccessGenerator
from .app import AppGenerator
from .guards import GuardGenerator
from .models import ModelGenerator
from .routers import RouterGenerator
from .schemas import SchemaGenerator
from .services import ServiceGenerator
from .utils import TYPE_MAPPING, pascal_case, snake_case
from .validators import ValidatorGenerator

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec
    from dazzle.eject.config import EjectionBackendConfig


class FastAPIAdapter(BackendAdapter):
    """Generate FastAPI application from AppSpec.

    Uses composition to delegate generation to specialized generators.
    """

    # Expose type mapping for backwards compatibility
    TYPE_MAPPING = TYPE_MAPPING

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        config: EjectionBackendConfig,
    ):
        super().__init__(spec, output_dir, config)
        self.backend_dir = output_dir / "backend"

        # Initialize generators
        self._model_gen = ModelGenerator(spec, output_dir, self._write_file, self._ensure_dir)
        self._schema_gen = SchemaGenerator(spec, output_dir, self._write_file, self._ensure_dir)
        self._router_gen = RouterGenerator(
            spec, output_dir, config, self._write_file, self._ensure_dir
        )
        self._service_gen = ServiceGenerator(spec, output_dir, self._write_file, self._ensure_dir)
        self._guard_gen = GuardGenerator(spec, output_dir, self._write_file, self._ensure_dir)
        self._validator_gen = ValidatorGenerator(
            spec, output_dir, self._write_file, self._ensure_dir
        )
        self._access_gen = AccessGenerator(spec, output_dir, self._write_file, self._ensure_dir)
        self._app_gen = AppGenerator(spec, output_dir, self._write_file, self._ensure_dir)

    def generate_config(self) -> GeneratorResult:
        """Generate configuration module."""
        return self._app_gen.generate_config()

    def generate_models(self) -> GeneratorResult:
        """Generate entity models."""
        return self._model_gen.generate_models()

    def generate_schemas(self) -> GeneratorResult:
        """Generate Pydantic request/response schemas."""
        return self._schema_gen.generate_schemas()

    def generate_routers(self) -> GeneratorResult:
        """Generate API routers."""
        return self._router_gen.generate_routers()

    def generate_services(self) -> GeneratorResult:
        """Generate business logic services."""
        return self._service_gen.generate_services()

    def generate_guards(self) -> GeneratorResult:
        """Generate state machine transition guards."""
        return self._guard_gen.generate_guards()

    def generate_validators(self) -> GeneratorResult:
        """Generate invariant validators."""
        return self._validator_gen.generate_validators()

    def generate_access(self) -> GeneratorResult:
        """Generate access control policies."""
        return self._access_gen.generate_access()

    def generate_app(self) -> GeneratorResult:
        """Generate main application entry point."""
        return self._app_gen.generate_app()

    # Utility methods for backwards compatibility
    def _snake_case(self, name: str) -> str:
        """Convert PascalCase to snake_case."""
        return snake_case(name)

    def _pascal_case(self, name: str) -> str:
        """Convert snake_case to PascalCase."""
        return pascal_case(name)


# Register adapter
AdapterRegistry.register_backend("fastapi", FastAPIAdapter)

__all__ = [
    "FastAPIAdapter",
    "TYPE_MAPPING",
    "snake_case",
    "pascal_case",
]
