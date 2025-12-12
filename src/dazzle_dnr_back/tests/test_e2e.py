"""
End-to-end tests for DNR Backend server.

Tests the complete flow from spec to running API.
"""

import pytest

try:
    from fastapi.testclient import TestClient

    TESTCLIENT_AVAILABLE = True
except ImportError:
    TESTCLIENT_AVAILABLE = False

from dazzle_dnr_back.runtime.server import create_app
from dazzle_dnr_back.specs import (
    BackendSpec,
    DomainOperation,
    EndpointSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    HttpMethod,
    OperationKind,
    ScalarType,
    ServiceSpec,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def task_spec() -> BackendSpec:
    """Create a simple task management spec."""
    return BackendSpec(
        name="task_app",
        version="1.0.0",
        entities=[
            EntitySpec(
                name="Task",
                fields=[
                    FieldSpec(
                        name="id",
                        type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        required=True,
                    ),
                    FieldSpec(
                        name="title",
                        type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                        required=True,
                    ),
                    FieldSpec(
                        name="status",
                        type=FieldType(kind="enum", enum_values=["pending", "done"]),
                        required=True,
                        default="pending",
                    ),
                ],
            ),
        ],
        services=[
            ServiceSpec(
                name="task_service",
                is_crud=True,
                target_entity="Task",
                domain_operation=DomainOperation(kind=OperationKind.LIST, entity="Task"),
            ),
        ],
        endpoints=[
            EndpointSpec(
                name="list_tasks",
                service="task_service",
                method=HttpMethod.GET,
                path="/tasks",
            ),
            EndpointSpec(
                name="get_task",
                service="task_service",
                method=HttpMethod.GET,
                path="/tasks/{id}",
            ),
            EndpointSpec(
                name="create_task",
                service="task_service",
                method=HttpMethod.POST,
                path="/tasks",
            ),
            EndpointSpec(
                name="update_task",
                service="task_service",
                method=HttpMethod.PUT,
                path="/tasks/{id}",
            ),
            EndpointSpec(
                name="delete_task",
                service="task_service",
                method=HttpMethod.DELETE,
                path="/tasks/{id}",
            ),
        ],
    )


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.skipif(not TESTCLIENT_AVAILABLE, reason="TestClient not available")
class TestE2EEndpoints:
    """End-to-end endpoint tests."""

    @pytest.fixture
    def client(self, task_spec: BackendSpec, tmp_path) -> TestClient:
        """Create a test client."""
        db_path = tmp_path / "test.db"
        app = create_app(task_spec, db_path=db_path, use_database=True)
        return TestClient(app)

    def test_health_endpoint(self, client: TestClient):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_list_empty(self, client: TestClient):
        """Test listing tasks when empty."""
        response = client.get("/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_task(self, client: TestClient):
        """Test creating a task."""
        response = client.post(
            "/tasks",
            json={"title": "Test Task", "status": "pending"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Task"
        assert data["status"] == "pending"
        assert "id" in data

    def test_read_task(self, client: TestClient):
        """Test reading a task."""
        # Create first
        create_response = client.post(
            "/tasks",
            json={"title": "Read Test", "status": "pending"},
        )
        task_id = create_response.json()["id"]

        # Read back
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Read Test"

    def test_update_task(self, client: TestClient):
        """Test updating a task."""
        # Create first
        create_response = client.post(
            "/tasks",
            json={"title": "Original", "status": "pending"},
        )
        task_id = create_response.json()["id"]

        # Update
        response = client.put(
            f"/tasks/{task_id}",
            json={"title": "Updated", "status": "done"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated"
        assert data["status"] == "done"

    def test_delete_task(self, client: TestClient):
        """Test deleting a task."""
        # Create first
        create_response = client.post(
            "/tasks",
            json={"title": "To Delete", "status": "pending"},
        )
        task_id = create_response.json()["id"]

        # Delete
        response = client.delete(f"/tasks/{task_id}")
        assert response.status_code == 200

        # Verify deleted
        get_response = client.get(f"/tasks/{task_id}")
        assert get_response.status_code == 404

    def test_crud_flow(self, client: TestClient):
        """Test complete CRUD flow."""
        # 1. Create
        create_response = client.post(
            "/tasks",
            json={"title": "CRUD Test", "status": "pending"},
        )
        assert create_response.status_code == 200
        task = create_response.json()
        task_id = task["id"]

        # 2. List (should have 1 item)
        list_response = client.get("/tasks")
        assert list_response.json()["total"] == 1

        # 3. Read
        read_response = client.get(f"/tasks/{task_id}")
        assert read_response.json()["title"] == "CRUD Test"

        # 4. Update
        update_response = client.put(
            f"/tasks/{task_id}",
            json={"title": "Updated CRUD", "status": "done"},
        )
        assert update_response.json()["status"] == "done"

        # 5. Delete
        delete_response = client.delete(f"/tasks/{task_id}")
        assert delete_response.status_code == 200

        # 6. Verify empty again
        final_list = client.get("/tasks")
        assert final_list.json()["total"] == 0

    def test_db_info(self, client: TestClient):
        """Test database info endpoint."""
        response = client.get("/db-info")
        assert response.status_code == 200
        data = response.json()
        assert data["database_enabled"] is True
        assert "Task" in data["tables"]
