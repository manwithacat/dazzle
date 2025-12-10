"""
Base adapter classes for ejection.

All adapters extend the Generator interface from dazzle.eject.generator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.eject.generator import Generator, GeneratorResult

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec
    from dazzle.eject.config import (
        EjectionBackendConfig,
        EjectionCIConfig,
        EjectionFrontendConfig,
        EjectionTestingConfig,
    )


class BackendAdapter(Generator, ABC):
    """
    Base class for backend code generators.

    Backend adapters generate:
    - Entity models (SQLAlchemy, Pydantic, Django ORM)
    - Request/response schemas
    - API routers/endpoints
    - Business logic services
    - State machine guards
    - Invariant validators
    - Access control policies
    """

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        config: EjectionBackendConfig,
    ):
        super().__init__(spec, output_dir)
        self.config = config

    def generate(self) -> GeneratorResult:
        """Generate complete backend application."""
        result = GeneratorResult()

        # Generate in dependency order
        result.merge(self.generate_config())
        result.merge(self.generate_models())
        result.merge(self.generate_schemas())
        result.merge(self.generate_guards())
        result.merge(self.generate_validators())
        result.merge(self.generate_access())
        result.merge(self.generate_services())
        result.merge(self.generate_routers())
        result.merge(self.generate_app())

        return result

    @abstractmethod
    def generate_config(self) -> GeneratorResult:
        """Generate configuration module."""
        pass

    @abstractmethod
    def generate_models(self) -> GeneratorResult:
        """Generate entity models."""
        pass

    @abstractmethod
    def generate_schemas(self) -> GeneratorResult:
        """Generate request/response schemas."""
        pass

    @abstractmethod
    def generate_routers(self) -> GeneratorResult:
        """Generate API routers/endpoints."""
        pass

    @abstractmethod
    def generate_services(self) -> GeneratorResult:
        """Generate business logic services."""
        pass

    @abstractmethod
    def generate_guards(self) -> GeneratorResult:
        """Generate state machine transition guards."""
        pass

    @abstractmethod
    def generate_validators(self) -> GeneratorResult:
        """Generate invariant validators."""
        pass

    @abstractmethod
    def generate_access(self) -> GeneratorResult:
        """Generate access control policies."""
        pass

    @abstractmethod
    def generate_app(self) -> GeneratorResult:
        """Generate main application entry point."""
        pass


class FrontendAdapter(Generator, ABC):
    """
    Base class for frontend code generators.

    Frontend adapters generate:
    - TypeScript types from entities
    - Runtime validation schemas (Zod)
    - HTTP client with validation
    - Data fetching hooks
    - Client-side validators
    """

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        config: EjectionFrontendConfig,
    ):
        super().__init__(spec, output_dir)
        self.config = config

    def generate(self) -> GeneratorResult:
        """Generate complete frontend API layer."""
        result = GeneratorResult()

        result.merge(self.generate_types())
        result.merge(self.generate_schemas())
        result.merge(self.generate_client())
        result.merge(self.generate_hooks())
        result.merge(self.generate_validation())

        return result

    @abstractmethod
    def generate_types(self) -> GeneratorResult:
        """Generate TypeScript types from entities."""
        pass

    @abstractmethod
    def generate_schemas(self) -> GeneratorResult:
        """Generate Zod schemas for runtime validation."""
        pass

    @abstractmethod
    def generate_client(self) -> GeneratorResult:
        """Generate HTTP client with validation."""
        pass

    @abstractmethod
    def generate_hooks(self) -> GeneratorResult:
        """Generate data fetching hooks."""
        pass

    @abstractmethod
    def generate_validation(self) -> GeneratorResult:
        """Generate client-side invariant validators."""
        pass


class TestingAdapter(Generator, ABC):
    """
    Base class for testing code generators.

    Testing adapters generate:
    - Contract tests (Schemathesis)
    - Unit test stubs
    - State machine tests
    - Invariant tests
    - E2E test flows
    """

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        config: EjectionTestingConfig,
    ):
        super().__init__(spec, output_dir)
        self.config = config


class CIAdapter(Generator, ABC):
    """
    Base class for CI configuration generators.

    CI adapters generate:
    - Workflow files (GitHub Actions, GitLab CI)
    - Build scripts
    - Deployment configurations
    """

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        config: EjectionCIConfig,
    ):
        super().__init__(spec, output_dir)
        self.config = config


class AdapterRegistry:
    """
    Registry for ejection adapters.

    Maps configuration values to adapter implementations.
    """

    _backend_adapters: dict[str, type[BackendAdapter]] = {}
    _frontend_adapters: dict[str, type[FrontendAdapter]] = {}
    _testing_adapters: dict[str, type[TestingAdapter]] = {}
    _ci_adapters: dict[str, type[CIAdapter]] = {}

    @classmethod
    def register_backend(cls, framework: str, adapter: type[BackendAdapter]) -> None:
        """Register a backend adapter."""
        cls._backend_adapters[framework] = adapter

    @classmethod
    def register_frontend(cls, framework: str, adapter: type[FrontendAdapter]) -> None:
        """Register a frontend adapter."""
        cls._frontend_adapters[framework] = adapter

    @classmethod
    def register_testing(cls, tool: str, adapter: type[TestingAdapter]) -> None:
        """Register a testing adapter."""
        cls._testing_adapters[tool] = adapter

    @classmethod
    def register_ci(cls, template: str, adapter: type[CIAdapter]) -> None:
        """Register a CI adapter."""
        cls._ci_adapters[template] = adapter

    @classmethod
    def get_backend(cls, framework: str) -> type[BackendAdapter] | None:
        """Get backend adapter by framework name."""
        return cls._backend_adapters.get(framework)

    @classmethod
    def get_frontend(cls, framework: str) -> type[FrontendAdapter] | None:
        """Get frontend adapter by framework name."""
        return cls._frontend_adapters.get(framework)

    @classmethod
    def get_testing(cls, tool: str) -> type[TestingAdapter] | None:
        """Get testing adapter by tool name."""
        return cls._testing_adapters.get(tool)

    @classmethod
    def get_ci(cls, template: str) -> type[CIAdapter] | None:
        """Get CI adapter by template name."""
        return cls._ci_adapters.get(template)

    @classmethod
    def list_backends(cls) -> list[str]:
        """List registered backend frameworks."""
        return list(cls._backend_adapters.keys())

    @classmethod
    def list_frontends(cls) -> list[str]:
        """List registered frontend frameworks."""
        return list(cls._frontend_adapters.keys())

    @classmethod
    def list_testing(cls) -> list[str]:
        """List registered testing tools."""
        return list(cls._testing_adapters.keys())

    @classmethod
    def list_ci(cls) -> list[str]:
        """List registered CI templates."""
        return list(cls._ci_adapters.keys())
