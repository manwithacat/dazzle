"""Tests for service loader."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from dazzle_back.runtime.service_loader import (
    LoadedService,
    ServiceInvocationError,
    ServiceLoader,
    ServiceLoadError,
    create_service_loader,
)

if TYPE_CHECKING:
    pass


class TestServiceLoader:
    """Tests for ServiceLoader class."""

    def test_load_services_from_example(self) -> None:
        """Test loading services from simple_task example."""
        # Use the actual example services directory
        services_dir = Path("examples/simple_task/services")

        loader = ServiceLoader(services_dir=services_dir)
        services = loader.load_services()

        # Should have loaded the calculate_overdue_penalty service
        assert "calculate_overdue_penalty" in services
        assert isinstance(services["calculate_overdue_penalty"], LoadedService)

    def test_invoke_service(self) -> None:
        """Test invoking a loaded service."""
        services_dir = Path("examples/simple_task/services")
        loader = ServiceLoader(services_dir=services_dir)
        loader.load_services()

        # Invoke the service
        result = loader.invoke("calculate_overdue_penalty", task_id="test-123")

        # Check result structure
        assert "penalty_amount" in result
        assert "reason" in result
        assert isinstance(result["penalty_amount"], float)
        assert isinstance(result["reason"], str)

    def test_invoke_missing_service(self) -> None:
        """Test invoking a non-existent service raises error."""
        services_dir = Path("examples/simple_task/services")
        loader = ServiceLoader(services_dir=services_dir)
        loader.load_services()

        with pytest.raises(ServiceInvocationError, match="Service not found"):
            loader.invoke("nonexistent_service")

    def test_has_service(self) -> None:
        """Test has_service check."""
        services_dir = Path("examples/simple_task/services")
        loader = ServiceLoader(services_dir=services_dir)

        # Should auto-load when checking
        assert loader.has_service("calculate_overdue_penalty")
        assert not loader.has_service("nonexistent")

    def test_get_service_ids(self) -> None:
        """Test getting list of service IDs."""
        services_dir = Path("examples/simple_task/services")
        loader = ServiceLoader(services_dir=services_dir)

        ids = loader.get_service_ids()
        assert "calculate_overdue_penalty" in ids

    def test_get_service(self) -> None:
        """Test getting a specific service."""
        services_dir = Path("examples/simple_task/services")
        loader = ServiceLoader(services_dir=services_dir)

        service = loader.get_service("calculate_overdue_penalty")
        assert service is not None
        assert service.service_id == "calculate_overdue_penalty"
        assert callable(service.function)

        # Nonexistent service
        assert loader.get_service("nonexistent") is None

    def test_load_nonexistent_directory(self) -> None:
        """Test loading from non-existent directory returns empty."""
        loader = ServiceLoader(services_dir=Path("/nonexistent/path"))
        services = loader.load_services()
        assert services == {}

    def test_unload_all(self) -> None:
        """Test unloading all services."""
        services_dir = Path("examples/simple_task/services")
        loader = ServiceLoader(services_dir=services_dir)
        loader.load_services()

        assert len(loader.services) > 0

        loader.unload_all()

        assert len(loader.services) == 0
        assert loader._loaded is False


class TestLoadedService:
    """Tests for LoadedService dataclass."""

    def test_loaded_service_fields(self) -> None:
        """Test LoadedService has expected fields."""
        service = LoadedService(
            service_id="test_service",
            function=lambda x: x,
            module_path=Path("test.py"),
            result_type=None,
        )

        assert service.service_id == "test_service"
        assert callable(service.function)
        assert service.module_path == Path("test.py")
        assert service.result_type is None


class TestServiceLoaderResultType:
    """Tests for result type detection."""

    def test_result_type_detected(self) -> None:
        """Test that result TypedDict is detected."""
        services_dir = Path("examples/simple_task/services")
        loader = ServiceLoader(services_dir=services_dir)
        loader.load_services()

        service = loader.get_service("calculate_overdue_penalty")
        assert service is not None

        # The stub should have a CalculateOverduePenaltyResult TypedDict
        assert service.result_type is not None
        assert service.result_type.__name__ == "CalculateOverduePenaltyResult"

    def test_to_result_type_name(self) -> None:
        """Test snake_case to PascalCaseResult conversion."""
        loader = ServiceLoader(services_dir=Path("."))

        assert loader._to_result_type_name("calculate_vat") == "CalculateVatResult"
        assert (
            loader._to_result_type_name("calculate_overdue_penalty")
            == "CalculateOverduePenaltyResult"
        )
        assert loader._to_result_type_name("simple") == "SimpleResult"


class TestCreateServiceLoader:
    """Tests for create_service_loader factory function."""

    def test_create_service_loader(self) -> None:
        """Test factory function creates loader with correct path."""
        loader = create_service_loader(Path("examples/simple_task"))

        assert loader.services_dir == Path("examples/simple_task/services")

    def test_create_service_loader_string_path(self) -> None:
        """Test factory function accepts string path."""
        loader = create_service_loader("examples/simple_task")

        assert loader.services_dir == Path("examples/simple_task/services")


class TestServiceLoaderWithTempDir:
    """Tests using temporary directories for isolation."""

    def test_load_invalid_python_file(self, tmp_path: Path) -> None:
        """Test loading file with syntax error raises ServiceLoadError."""
        services_dir = tmp_path / "services"
        services_dir.mkdir()

        # Create invalid Python file
        bad_file = services_dir / "bad_service.py"
        bad_file.write_text("def bad_service(: invalid syntax")

        loader = ServiceLoader(services_dir=services_dir)

        with pytest.raises(ServiceLoadError, match="Error executing"):
            loader.load_services()

    def test_skip_underscore_files(self, tmp_path: Path) -> None:
        """Test that files starting with underscore are skipped."""
        services_dir = tmp_path / "services"
        services_dir.mkdir()

        # Create __init__.py (should be skipped)
        init_file = services_dir / "__init__.py"
        init_file.write_text("# init file")

        # Create _helper.py (should be skipped)
        helper_file = services_dir / "_helper.py"
        helper_file.write_text("def helper(): pass")

        # Create valid service
        valid_file = services_dir / "valid_service.py"
        valid_file.write_text(
            """
def valid_service(x: str) -> dict:
    return {"result": x}
"""
        )

        loader = ServiceLoader(services_dir=services_dir)
        services = loader.load_services()

        # Should only have valid_service
        assert "valid_service" in services
        assert "__init__" not in services
        assert "_helper" not in services

    def test_file_without_matching_function(self, tmp_path: Path) -> None:
        """Test file without matching function name is skipped."""
        services_dir = tmp_path / "services"
        services_dir.mkdir()

        # Create file where function name doesn't match filename
        file = services_dir / "my_service.py"
        file.write_text(
            """
def different_name(x: str) -> dict:
    return {"result": x}
"""
        )

        loader = ServiceLoader(services_dir=services_dir)
        services = loader.load_services()

        # Should not load because function name doesn't match
        assert "my_service" not in services

    def test_reload_service(self, tmp_path: Path) -> None:
        """Test reloading a service picks up changes."""
        services_dir = tmp_path / "services"
        services_dir.mkdir()

        # Create initial service
        file = services_dir / "counter.py"
        file.write_text(
            """
def counter() -> dict:
    return {"value": 1}
"""
        )

        loader = ServiceLoader(services_dir=services_dir)
        loader.load_services()

        # Initial value
        result1 = loader.invoke("counter")
        assert result1["value"] == 1

        # Update the service
        file.write_text(
            """
def counter() -> dict:
    return {"value": 42}
"""
        )

        # Reload
        loader.reload_service("counter")

        # Should have new value
        result2 = loader.invoke("counter")
        assert result2["value"] == 42
