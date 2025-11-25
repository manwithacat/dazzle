"""
Backend plugin system for DAZZLE.

Backends generate concrete artifacts (code, specs, configs) from validated AppSpec.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core import ir
from ..core.errors import BackendError


@dataclass
class BackendCapabilities:
    """
    Describes what a backend can generate.

    Used for introspection and CLI help text.
    """

    name: str
    description: str
    output_formats: list[str]  # e.g., ["yaml", "json"]
    supports_incremental: bool = False  # Can generate incrementally (update existing files)
    requires_config: bool = False  # Requires additional config beyond AppSpec


class Backend(ABC):
    """
    Abstract base class for all DAZZLE backends.

    Backends transform a validated AppSpec into concrete artifacts like:
    - API specifications (OpenAPI, GraphQL)
    - Database schemas (SQL DDL, Prisma)
    - Application code (React components, FastAPI routes)
    - Configuration files (Docker, Kubernetes)

    Minimal interface for easy extensibility.
    """

    @abstractmethod
    def generate(self, appspec: ir.AppSpec, output_dir: Path, **options: Any) -> None:
        """
        Generate artifacts from AppSpec.

        Args:
            appspec: Validated application specification
            output_dir: Directory to write generated files (will be created if needed)
            **options: Backend-specific options passed from CLI

        Raises:
            BackendError: If generation fails
        """
        pass

    def get_capabilities(self) -> BackendCapabilities:
        """
        Get backend capabilities for introspection.

        Override to provide backend metadata.

        Returns:
            BackendCapabilities describing what this backend can do
        """
        return BackendCapabilities(
            name=self.__class__.__name__,
            description="No description provided",
            output_formats=["unknown"],
        )

    def validate_config(self, **options: Any) -> None:
        """
        Validate backend-specific configuration.

        Called before generate() to catch config errors early.
        Override to validate backend-specific options.

        Args:
            **options: Backend-specific options from CLI

        Raises:
            BackendError: If config is invalid
        """
        # Default: no validation needed
        pass


class BackendRegistry:
    """
    Registry for backend plugins.

    Supports:
    - Manual registration via register()
    - Auto-discovery of backends in backends/ directory
    - Lookup by name
    """

    def __init__(self) -> None:
        self._backends: dict[str, type[Backend]] = {}

    def register(self, name: str, backend_class: type[Backend]) -> None:
        """
        Register a backend class.

        Args:
            name: Backend name (used in CLI: --backend <name>)
            backend_class: Backend class (must extend Backend)

        Raises:
            BackendError: If name already registered or class invalid
        """
        if name in self._backends:
            raise BackendError(
                f"Backend '{name}' is already registered. Cannot register {backend_class.__name__}."
            )

        if not issubclass(backend_class, Backend):
            raise BackendError(f"Backend class {backend_class.__name__} must extend Backend")

        self._backends[name] = backend_class

    def get(self, name: str) -> Backend:
        """
        Get a backend instance by name.

        Args:
            name: Backend name

        Returns:
            Backend instance

        Raises:
            BackendError: If backend not found
        """
        if name not in self._backends:
            available = list(self._backends.keys())
            raise BackendError(f"Backend '{name}' not found. Available backends: {available}")

        backend_class = self._backends[name]
        return backend_class()

    def list_backends(self) -> list[str]:
        """
        List all registered backend names.

        Returns:
            List of backend names
        """
        return list(self._backends.keys())

    def discover(self) -> None:
        """
        Auto-discover backends in backends/ directory.

        Looks for classes that extend Backend and registers them
        using their module name (e.g., 'openapi' from openapi.py).

        Supports both single-file backends (openapi.py) and package
        backends (django_micro_modular/__init__.py).

        This is called automatically by get_registry().
        """
        import importlib
        import inspect
        from pathlib import Path

        # Get backends directory
        backends_dir = Path(__file__).parent

        # Scan for .py files (single-file backends)
        for py_file in backends_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue  # Skip __init__.py, __pycache__, etc.

            module_name = py_file.stem
            self._try_register_module(module_name)

        # Scan for package backends (directories with __init__.py)
        for subdir in backends_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith("_") or subdir.name.startswith("."):
                continue  # Skip __pycache__, .git, etc.
            if not (subdir / "__init__.py").exists():
                continue  # Not a package

            module_name = subdir.name
            self._try_register_module(module_name)

    def _try_register_module(self, module_name: str) -> None:
        """Try to import and register a backend module."""
        import importlib
        import inspect

        if module_name in self._backends:
            return  # Already registered

        try:
            module = importlib.import_module(f"dazzle.stacks.{module_name}")

            # Find Backend subclasses
            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Backend) and obj is not Backend:
                    if module_name not in self._backends:
                        self.register(module_name, obj)
        except Exception:
            # Silently skip modules that fail to import
            # This allows partial installations
            pass


# Global registry instance
_registry: BackendRegistry | None = None


def get_registry() -> BackendRegistry:
    """
    Get the global backend registry.

    Performs auto-discovery on first call.

    Returns:
        BackendRegistry singleton
    """
    global _registry
    if _registry is None:
        _registry = BackendRegistry()
        _registry.discover()
    return _registry


def register_backend(name: str, backend_class: type[Backend]) -> None:
    """
    Register a backend in the global registry.

    Args:
        name: Backend name (used in CLI)
        backend_class: Backend class (must extend Backend)
    """
    get_registry().register(name, backend_class)


def get_backend(name: str) -> Backend:
    """
    Get a backend instance by name.

    Args:
        name: Backend name

    Returns:
        Backend instance

    Raises:
        BackendError: If backend not found
    """
    return get_registry().get(name)


def list_backends() -> list[str]:
    """
    List all available backend names.

    Returns:
        List of backend names
    """
    return get_registry().list_backends()


__all__ = [
    "Backend",
    "BackendCapabilities",
    "BackendRegistry",
    "BackendError",
    "get_registry",
    "register_backend",
    "get_backend",
    "list_backends",
]
