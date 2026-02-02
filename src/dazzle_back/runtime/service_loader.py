"""
Service loader for domain service stubs.

Discovers, loads, and manages user-implemented domain service stubs.
These are Turing-complete Python functions that implement business logic
declared in DSL as service contracts.

The loader:
1. Discovers stub files in the services/ directory
2. Dynamically imports them at runtime
3. Validates they match expected signatures
4. Makes them available for invocation
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ServiceLoadError(Exception):
    """Raised when a service stub cannot be loaded."""

    pass


class ServiceInvocationError(Exception):
    """Raised when a service invocation fails."""

    pass


@dataclass
class LoadedService:
    """
    A loaded domain service stub.

    Attributes:
        service_id: Service identifier (matches DSL declaration)
        function: The callable Python function
        module_path: Path to the source module
        result_type: TypedDict class for the result (if found)
    """

    service_id: str
    function: Callable[..., Any]
    module_path: Path
    result_type: type | None = None


@dataclass
class ServiceLoader:
    """
    Load and invoke domain service stubs at runtime.

    The ServiceLoader discovers Python stub files in a services directory,
    imports them, and makes them available for invocation by the DNR runtime.

    Example:
        >>> loader = ServiceLoader(Path("examples/simple_task/services"))
        >>> loader.load_services()
        >>> result = loader.invoke("calculate_overdue_penalty", task_id="uuid-123")
    """

    services_dir: Path
    services: dict[str, LoadedService] = field(default_factory=dict)
    _loaded: bool = False

    def load_services(self) -> dict[str, LoadedService]:
        """
        Discover and load all service stubs.

        Scans the services directory for Python files and loads any
        that contain functions matching the expected stub pattern.

        Returns:
            Dict mapping service_id to LoadedService

        Raises:
            ServiceLoadError: If a service file cannot be loaded
        """
        if not self.services_dir.exists():
            logger.debug(f"Services directory not found: {self.services_dir}")
            return self.services

        if not self.services_dir.is_dir():
            logger.warning(f"Services path is not a directory: {self.services_dir}")
            return self.services

        # Find all Python files
        stub_files = list(self.services_dir.glob("*.py"))

        for stub_file in stub_files:
            if stub_file.name.startswith("_"):
                continue  # Skip __init__.py, __pycache__, etc.

            try:
                loaded = self._load_stub_file(stub_file)
                if loaded:
                    self.services[loaded.service_id] = loaded
                    logger.info(f"Loaded service stub: {loaded.service_id}")
            except Exception as e:
                logger.error(f"Failed to load service stub {stub_file}: {e}")
                raise ServiceLoadError(f"Failed to load {stub_file}: {e}") from e

        self._loaded = True
        return self.services

    def _load_stub_file(self, stub_file: Path) -> LoadedService | None:
        """
        Load a single stub file.

        The file is expected to contain:
        - A function with the same name as the file (snake_case)
        - Optionally, a TypedDict class for the result type

        Args:
            stub_file: Path to the Python stub file

        Returns:
            LoadedService if successful, None if no valid service found
        """
        # Derive service_id from filename
        service_id = stub_file.stem

        # Create a unique module name to avoid conflicts
        module_name = f"dazzle_stub_{service_id}"

        # Load the module
        spec = importlib.util.spec_from_file_location(module_name, stub_file)
        if spec is None or spec.loader is None:
            raise ServiceLoadError(f"Cannot create module spec for {stub_file}")

        module = importlib.util.module_from_spec(spec)

        # Add to sys.modules before exec (required for relative imports)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            # Clean up on failure
            del sys.modules[module_name]
            raise ServiceLoadError(f"Error executing {stub_file}: {e}") from e

        # Find the main function (same name as file)
        if not hasattr(module, service_id):
            logger.warning(f"Stub file {stub_file} has no function named {service_id}")
            del sys.modules[module_name]
            return None

        function = getattr(module, service_id)
        if not callable(function):
            logger.warning(f"{service_id} in {stub_file} is not callable")
            del sys.modules[module_name]
            return None

        # Try to find result type (PascalCase + "Result")
        result_type_name = self._to_result_type_name(service_id)
        result_type = getattr(module, result_type_name, None)

        return LoadedService(
            service_id=service_id,
            function=function,
            module_path=stub_file,
            result_type=result_type,
        )

    def _to_result_type_name(self, service_id: str) -> str:
        """Convert snake_case service_id to PascalCaseResult."""
        parts = service_id.split("_")
        pascal = "".join(word.capitalize() for word in parts)
        return f"{pascal}Result"

    def invoke(self, service_id: str, **kwargs: Any) -> Any:
        """
        Invoke a loaded service by ID.

        Args:
            service_id: Service identifier
            **kwargs: Arguments to pass to the service function

        Returns:
            Service result

        Raises:
            ServiceInvocationError: If service not found or invocation fails
        """
        if not self._loaded:
            self.load_services()

        if service_id not in self.services:
            raise ServiceInvocationError(f"Service not found: {service_id}")

        loaded = self.services[service_id]

        try:
            return loaded.function(**kwargs)
        except Exception as e:
            raise ServiceInvocationError(f"Service {service_id} invocation failed: {e}") from e

    def has_service(self, service_id: str) -> bool:
        """Check if a service is loaded."""
        if not self._loaded:
            self.load_services()
        return service_id in self.services

    def get_service_ids(self) -> list[str]:
        """Get list of loaded service IDs."""
        if not self._loaded:
            self.load_services()
        return list(self.services.keys())

    def get_service(self, service_id: str) -> LoadedService | None:
        """Get a loaded service by ID."""
        if not self._loaded:
            self.load_services()
        return self.services.get(service_id)

    def reload_service(self, service_id: str) -> LoadedService | None:
        """
        Reload a specific service from disk.

        Useful for development when stub code changes.

        Args:
            service_id: Service identifier to reload

        Returns:
            Reloaded service, or None if not found
        """
        # Find the stub file
        stub_file = self.services_dir / f"{service_id}.py"
        if not stub_file.exists():
            return None

        # Remove old module from sys.modules
        module_name = f"dazzle_stub_{service_id}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Remove from services dict
        self.services.pop(service_id, None)

        # Reload
        loaded = self._load_stub_file(stub_file)
        if loaded:
            self.services[loaded.service_id] = loaded
            logger.info(f"Reloaded service stub: {service_id}")
        return loaded

    def unload_all(self) -> None:
        """Unload all services and clean up modules."""
        for service_id in list(self.services.keys()):
            module_name = f"dazzle_stub_{service_id}"
            if module_name in sys.modules:
                del sys.modules[module_name]

        self.services.clear()
        self._loaded = False


def create_service_loader(project_dir: Path | str) -> ServiceLoader:
    """
    Create a ServiceLoader for a project.

    Args:
        project_dir: Project root directory

    Returns:
        ServiceLoader configured for the project's services/ directory
    """
    project_path = Path(project_dir)
    services_dir = project_path / "services"
    return ServiceLoader(services_dir=services_dir)


__all__ = [
    "ServiceLoadError",
    "ServiceInvocationError",
    "LoadedService",
    "ServiceLoader",
    "create_service_loader",
]
