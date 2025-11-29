"""
Unit tests for DNR test endpoints.

Tests the /__test__/* endpoints for E2E testing support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from dazzle_dnr_back.specs import BackendSpec

from dazzle_dnr_back.runtime.test_routes import (
    AuthenticateRequest,
    AuthenticateResponse,
    FixtureData,
    SeedRequest,
    SeedResponse,
    SnapshotResponse,
)


class TestFixtureData:
    """Tests for FixtureData model."""

    def test_fixture_data_minimal(self) -> None:
        """Test creating fixture data with minimal fields."""
        fixture = FixtureData(
            id="task_1",
            entity="Task",
            data={"title": "Test Task"},
        )
        assert fixture.id == "task_1"
        assert fixture.entity == "Task"
        assert fixture.data == {"title": "Test Task"}
        assert fixture.refs is None

    def test_fixture_data_with_refs(self) -> None:
        """Test creating fixture data with references."""
        fixture = FixtureData(
            id="task_1",
            entity="Task",
            data={"title": "Test Task"},
            refs={"project_id": "project_1"},
        )
        assert fixture.refs == {"project_id": "project_1"}


class TestSeedRequest:
    """Tests for SeedRequest model."""

    def test_seed_request_empty(self) -> None:
        """Test creating seed request with no fixtures."""
        request = SeedRequest(fixtures=[])
        assert request.fixtures == []

    def test_seed_request_with_fixtures(self) -> None:
        """Test creating seed request with multiple fixtures."""
        request = SeedRequest(
            fixtures=[
                FixtureData(id="task_1", entity="Task", data={"title": "Task 1"}),
                FixtureData(id="task_2", entity="Task", data={"title": "Task 2"}),
            ]
        )
        assert len(request.fixtures) == 2
        assert request.fixtures[0].id == "task_1"
        assert request.fixtures[1].id == "task_2"


class TestSeedResponse:
    """Tests for SeedResponse model."""

    def test_seed_response_empty(self) -> None:
        """Test creating seed response with no created entities."""
        response = SeedResponse(created={})
        assert response.created == {}

    def test_seed_response_with_created(self) -> None:
        """Test creating seed response with created entities."""
        response = SeedResponse(
            created={
                "task_1": {"id": "uuid-1", "title": "Task 1"},
                "task_2": {"id": "uuid-2", "title": "Task 2"},
            }
        )
        assert len(response.created) == 2
        assert response.created["task_1"]["title"] == "Task 1"


class TestSnapshotResponse:
    """Tests for SnapshotResponse model."""

    def test_snapshot_response_empty(self) -> None:
        """Test creating snapshot response with no entities."""
        response = SnapshotResponse(entities={})
        assert response.entities == {}

    def test_snapshot_response_with_entities(self) -> None:
        """Test creating snapshot response with entity data."""
        response = SnapshotResponse(
            entities={
                "Task": [
                    {"id": "uuid-1", "title": "Task 1"},
                    {"id": "uuid-2", "title": "Task 2"},
                ],
                "Project": [
                    {"id": "uuid-3", "name": "Project 1"},
                ],
            }
        )
        assert len(response.entities) == 2
        assert len(response.entities["Task"]) == 2
        assert len(response.entities["Project"]) == 1


class TestAuthenticateRequest:
    """Tests for AuthenticateRequest model."""

    def test_authenticate_request_defaults(self) -> None:
        """Test creating authenticate request with defaults."""
        request = AuthenticateRequest()
        assert request.username is None
        assert request.password is None
        assert request.role is None

    def test_authenticate_request_with_values(self) -> None:
        """Test creating authenticate request with values."""
        request = AuthenticateRequest(
            username="testuser",
            password="testpass",
            role="admin",
        )
        assert request.username == "testuser"
        assert request.password == "testpass"
        assert request.role == "admin"


class TestAuthenticateResponse:
    """Tests for AuthenticateResponse model."""

    def test_authenticate_response(self) -> None:
        """Test creating authenticate response."""
        response = AuthenticateResponse(
            user_id="uuid-1",
            username="testuser",
            role="admin",
            session_token="token-123",
        )
        assert response.user_id == "uuid-1"
        assert response.username == "testuser"
        assert response.role == "admin"
        assert response.session_token == "token-123"


class TestTestRoutesIntegration:
    """Integration tests for test routes with real server."""

    @pytest.fixture
    def backend_spec(self) -> BackendSpec:
        """Create a test backend spec."""
        from dazzle_dnr_back.specs import BackendSpec
        from dazzle_dnr_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType
        from dazzle_dnr_back.specs.service import DomainOperation, OperationKind, ServiceSpec

        task_entity = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
                FieldSpec(
                    name="completed",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.BOOL),
                    default=False,
                ),
            ],
        )

        return BackendSpec(
            name="test_app",
            version="0.1.0",
            entities=[task_entity],
            services=[
                ServiceSpec(
                    name="TaskCreate",
                    domain_operation=DomainOperation(kind=OperationKind.CREATE, entity="Task"),
                ),
                ServiceSpec(
                    name="TaskRead",
                    domain_operation=DomainOperation(kind=OperationKind.READ, entity="Task"),
                ),
                ServiceSpec(
                    name="TaskList",
                    domain_operation=DomainOperation(kind=OperationKind.LIST, entity="Task"),
                ),
            ],
            endpoints=[],
        )

    @pytest.fixture
    def test_client(self, backend_spec: BackendSpec, tmp_path) -> TestClient:
        """Create a test client with test mode enabled."""
        from fastapi.testclient import TestClient

        from dazzle_dnr_back.runtime.server import create_app

        db_path = tmp_path / "test.db"
        app = create_app(
            backend_spec,
            db_path=str(db_path),
            enable_test_mode=True,
        )
        return TestClient(app)

    def test_seed_fixtures(self, test_client: TestClient) -> None:
        """Test seeding fixtures via API."""
        response = test_client.post(
            "/__test__/seed",
            json={
                "fixtures": [
                    {
                        "id": "task_1",
                        "entity": "Task",
                        "data": {"title": "Test Task 1"},
                    },
                    {
                        "id": "task_2",
                        "entity": "Task",
                        "data": {"title": "Test Task 2"},
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "created" in data
        assert "task_1" in data["created"]
        assert "task_2" in data["created"]
        assert data["created"]["task_1"]["title"] == "Test Task 1"

    def test_reset_test_data(self, test_client: TestClient) -> None:
        """Test resetting test data via API."""
        # First seed some data
        test_client.post(
            "/__test__/seed",
            json={
                "fixtures": [
                    {
                        "id": "task_1",
                        "entity": "Task",
                        "data": {"title": "Test Task"},
                    },
                ]
            },
        )

        # Reset
        response = test_client.post("/__test__/reset")
        assert response.status_code == 200
        assert response.json()["status"] == "reset_complete"

        # Verify data is gone
        snapshot = test_client.get("/__test__/snapshot")
        assert snapshot.status_code == 200
        assert len(snapshot.json()["entities"]["Task"]) == 0

    def test_get_snapshot(self, test_client: TestClient) -> None:
        """Test getting database snapshot via API."""
        # Seed some data
        test_client.post(
            "/__test__/seed",
            json={
                "fixtures": [
                    {
                        "id": "task_1",
                        "entity": "Task",
                        "data": {"title": "Test Task"},
                    },
                ]
            },
        )

        # Get snapshot
        response = test_client.get("/__test__/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "entities" in data
        assert "Task" in data["entities"]
        assert len(data["entities"]["Task"]) == 1
        assert data["entities"]["Task"][0]["title"] == "Test Task"

    def test_authenticate_test_user(self, test_client: TestClient) -> None:
        """Test authenticating test user via API."""
        response = test_client.post(
            "/__test__/authenticate",
            json={"role": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"
        assert "user_id" in data
        assert "session_token" in data

    def test_get_entity_data(self, test_client: TestClient) -> None:
        """Test getting entity data via API."""
        # Seed some data
        test_client.post(
            "/__test__/seed",
            json={
                "fixtures": [
                    {
                        "id": "task_1",
                        "entity": "Task",
                        "data": {"title": "Test Task"},
                    },
                ]
            },
        )

        response = test_client.get("/__test__/entity/Task")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Test Task"

    def test_get_entity_count(self, test_client: TestClient) -> None:
        """Test getting entity count via API."""
        # Seed some data
        test_client.post(
            "/__test__/seed",
            json={
                "fixtures": [
                    {
                        "id": "task_1",
                        "entity": "Task",
                        "data": {"title": "Test Task 1"},
                    },
                    {
                        "id": "task_2",
                        "entity": "Task",
                        "data": {"title": "Test Task 2"},
                    },
                ]
            },
        )

        response = test_client.get("/__test__/entity/Task/count")
        assert response.status_code == 200
        assert response.json()["count"] == 2

    def test_delete_entity(self, test_client: TestClient) -> None:
        """Test deleting entity via API."""
        # Seed some data
        seed_response = test_client.post(
            "/__test__/seed",
            json={
                "fixtures": [
                    {
                        "id": "task_1",
                        "entity": "Task",
                        "data": {"title": "Test Task"},
                    },
                ]
            },
        )
        task_id = seed_response.json()["created"]["task_1"]["id"]

        # Delete
        response = test_client.delete(f"/__test__/entity/Task/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify gone
        count_response = test_client.get("/__test__/entity/Task/count")
        assert count_response.json()["count"] == 0

    def test_unknown_entity_returns_404(self, test_client: TestClient) -> None:
        """Test that unknown entity returns 404."""
        response = test_client.get("/__test__/entity/NonExistent")
        assert response.status_code == 404

    def test_seed_unknown_entity_returns_400(self, test_client: TestClient) -> None:
        """Test that seeding unknown entity returns 400."""
        response = test_client.post(
            "/__test__/seed",
            json={
                "fixtures": [
                    {
                        "id": "unknown_1",
                        "entity": "NonExistent",
                        "data": {"title": "Test"},
                    },
                ]
            },
        )
        assert response.status_code == 400


class TestTestModeDisabled:
    """Test that test endpoints are not available when test mode is disabled."""

    @pytest.fixture
    def backend_spec(self) -> BackendSpec:
        """Create a test backend spec."""
        from dazzle_dnr_back.specs import BackendSpec
        from dazzle_dnr_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

        task_entity = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                ),
            ],
        )

        return BackendSpec(
            name="test_app",
            version="0.1.0",
            entities=[task_entity],
            services=[],
            endpoints=[],
        )

    @pytest.fixture
    def test_client(self, backend_spec: BackendSpec, tmp_path) -> TestClient:
        """Create a test client WITHOUT test mode enabled."""
        from fastapi.testclient import TestClient

        from dazzle_dnr_back.runtime.server import create_app

        db_path = tmp_path / "test.db"
        app = create_app(
            backend_spec,
            db_path=str(db_path),
            enable_test_mode=False,  # Explicitly disabled
        )
        return TestClient(app)

    def test_seed_not_available(self, test_client: TestClient) -> None:
        """Test that seed endpoint is not available when test mode disabled."""
        response = test_client.post("/__test__/seed", json={"fixtures": []})
        assert response.status_code == 404

    def test_reset_not_available(self, test_client: TestClient) -> None:
        """Test that reset endpoint is not available when test mode disabled."""
        response = test_client.post("/__test__/reset")
        assert response.status_code == 404

    def test_snapshot_not_available(self, test_client: TestClient) -> None:
        """Test that snapshot endpoint is not available when test mode disabled."""
        response = test_client.get("/__test__/snapshot")
        assert response.status_code == 404
