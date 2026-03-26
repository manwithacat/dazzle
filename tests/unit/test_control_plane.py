"""
Unit tests for control plane endpoints.

Tests the /dazzle/dev/* endpoints for developer-mode operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from dazzle.core.ir.appspec import AppSpec

# Check if FastAPI is available (needed for integration tests)
try:
    import fastapi  # noqa: F401

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestControlPlaneIntegration:
    """Integration tests for control plane routes with real server.

    Uses a class-scoped fixture to share one FastAPI app/client across all tests.
    """

    @pytest.fixture(scope="class")
    def appspec(self) -> AppSpec:
        """Create a test AppSpec (class-scoped for reuse)."""
        from dazzle.core.ir.appspec import AppSpec
        from dazzle.core.ir.domain import DomainSpec
        from dazzle.core.ir.domain import EntitySpec as IREntitySpec
        from dazzle.core.ir.fields import FieldSpec as IRFieldSpec
        from dazzle.core.ir.fields import FieldType as IRFieldType
        from dazzle.core.ir.fields import FieldTypeKind

        task_entity = IREntitySpec(
            name="Task",
            title="Task",
            fields=[
                IRFieldSpec(
                    name="id",
                    type=IRFieldType(kind=FieldTypeKind.UUID),
                    modifiers=["pk"],
                ),
                IRFieldSpec(
                    name="title",
                    type=IRFieldType(kind=FieldTypeKind.STR, max_length=200),
                    modifiers=["required"],
                ),
                IRFieldSpec(
                    name="completed",
                    type=IRFieldType(kind=FieldTypeKind.BOOL),
                    default=False,
                ),
            ],
        )

        return AppSpec(
            name="test_app",
            version="0.1.0",
            domain=DomainSpec(entities=[task_entity]),
        )

    @pytest.fixture(scope="class")
    def shared_test_client(
        self, appspec: AppSpec, tmp_path_factory: pytest.TempPathFactory
    ) -> TestClient:
        """Create a shared test client for the class (reused across tests)."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from dazzle_back.runtime.app_factory import create_app

        with (
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
        ):
            app = create_app(
                appspec,
                database_url="postgresql://mock/test",
                enable_dev_mode=True,
            )
        return TestClient(app)

    @pytest.fixture
    def test_client(self, shared_test_client: TestClient) -> TestClient:
        """Provide test client for each test."""
        return shared_test_client

    def test_reset_data(self, test_client: TestClient) -> None:
        """Test resetting all data."""
        response = test_client.post("/dazzle/dev/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reset_complete"

    def test_log_frontend_message(self, test_client: TestClient) -> None:
        """Test logging a frontend message."""
        response = test_client.post(
            "/dazzle/dev/log",
            json={"level": "error", "message": "Something went wrong", "url": "/tasks"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "logged"

    def test_get_logs(self, test_client: TestClient) -> None:
        """Test retrieving recent logs."""
        response = test_client.get("/dazzle/dev/logs")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "entries" in data
        assert "log_file" in data

    def test_get_error_summary(self, test_client: TestClient) -> None:
        """Test retrieving error summary."""
        response = test_client.get("/dazzle/dev/logs/errors")
        assert response.status_code == 200


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestDevModeDisabled:
    """Test that control plane endpoints are not available when dev mode is disabled."""

    @pytest.fixture(scope="class")
    def appspec(self) -> AppSpec:
        """Create a test AppSpec."""
        from dazzle.core.ir.appspec import AppSpec
        from dazzle.core.ir.domain import DomainSpec
        from dazzle.core.ir.domain import EntitySpec as IREntitySpec
        from dazzle.core.ir.fields import FieldSpec as IRFieldSpec
        from dazzle.core.ir.fields import FieldType as IRFieldType
        from dazzle.core.ir.fields import FieldTypeKind

        task_entity = IREntitySpec(
            name="Task",
            title="Task",
            fields=[
                IRFieldSpec(
                    name="id",
                    type=IRFieldType(kind=FieldTypeKind.UUID),
                    modifiers=["pk"],
                ),
                IRFieldSpec(
                    name="title",
                    type=IRFieldType(kind=FieldTypeKind.STR, max_length=200),
                ),
            ],
        )

        return AppSpec(
            name="test_app",
            version="0.1.0",
            domain=DomainSpec(entities=[task_entity]),
        )

    @pytest.fixture(scope="class")
    def test_client(self, appspec: AppSpec, tmp_path_factory: pytest.TempPathFactory) -> TestClient:
        """Create a test client WITHOUT dev mode enabled."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from dazzle_back.runtime.app_factory import create_app

        with (
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
        ):
            app = create_app(
                appspec,
                database_url="postgresql://mock/test",
                enable_dev_mode=False,
                enable_test_mode=False,
            )
        return TestClient(app)

    def test_reset_not_available(self, test_client: TestClient) -> None:
        """Test that reset endpoint is not available when dev mode disabled."""
        response = test_client.post("/dazzle/dev/reset")
        assert response.status_code == 404

    def test_log_not_available(self, test_client: TestClient) -> None:
        """Test that log endpoint is not available when dev mode disabled."""
        response = test_client.post("/dazzle/dev/log", json={"level": "info", "message": "test"})
        assert response.status_code == 404
