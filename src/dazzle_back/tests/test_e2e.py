"""
End-to-end tests for Dazzle Backend server.

Tests the complete flow from spec to running API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

try:
    from fastapi.testclient import TestClient as _TestClient  # noqa: F811

    TESTCLIENT_AVAILABLE = True
except ImportError:
    _TestClient = None  # type: ignore[misc,assignment]
    TESTCLIENT_AVAILABLE = False

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.domain import EntitySpec as IREntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldTypeKind
from dazzle.core.ir.fields import FieldSpec as IRFieldSpec
from dazzle.core.ir.fields import FieldType as IRFieldType
from dazzle.core.ir.surfaces import SurfaceElement, SurfaceMode, SurfaceSection, SurfaceSpec
from dazzle_back.runtime.server import create_app

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def task_spec() -> AppSpec:
    """Create a simple task management spec."""
    return AppSpec(
        name="task_app",
        version="1.0.0",
        domain=DomainSpec(
            entities=[
                IREntitySpec(
                    name="Task",
                    title="Task",
                    fields=[
                        IRFieldSpec(
                            name="id",
                            type=IRFieldType(kind=FieldTypeKind.UUID),
                            modifiers=[FieldModifier.PK],
                        ),
                        IRFieldSpec(
                            name="title",
                            type=IRFieldType(kind=FieldTypeKind.STR, max_length=200),
                            modifiers=[FieldModifier.REQUIRED],
                        ),
                        IRFieldSpec(
                            name="status",
                            type=IRFieldType(
                                kind=FieldTypeKind.ENUM, enum_values=["pending", "done"]
                            ),
                            modifiers=[FieldModifier.REQUIRED],
                            default="pending",
                        ),
                    ],
                ),
            ]
        ),
        surfaces=[
            SurfaceSpec(
                name="task_list",
                title="Task List",
                entity_ref="Task",
                mode=SurfaceMode.LIST,
                sections=[
                    SurfaceSection(
                        name="main",
                        title="Tasks",
                        elements=[
                            SurfaceElement(field_name="title", label="Title"),
                            SurfaceElement(field_name="status", label="Status"),
                        ],
                    )
                ],
            ),
            SurfaceSpec(
                name="task_create",
                title="Create Task",
                entity_ref="Task",
                mode=SurfaceMode.CREATE,
                sections=[
                    SurfaceSection(
                        name="main",
                        title="New Task",
                        elements=[
                            SurfaceElement(field_name="title", label="Title"),
                            SurfaceElement(field_name="status", label="Status"),
                        ],
                    )
                ],
            ),
            SurfaceSpec(
                name="task_detail",
                title="Task Detail",
                entity_ref="Task",
                mode=SurfaceMode.VIEW,
            ),
            SurfaceSpec(
                name="task_edit",
                title="Edit Task",
                entity_ref="Task",
                mode=SurfaceMode.EDIT,
                sections=[
                    SurfaceSection(
                        name="main",
                        title="Edit Task",
                        elements=[
                            SurfaceElement(field_name="title", label="Title"),
                            SurfaceElement(field_name="status", label="Status"),
                        ],
                    )
                ],
            ),
        ],
    )


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.skipif(not TESTCLIENT_AVAILABLE, reason="TestClient not available")
@pytest.mark.skipif(
    not __import__("os").environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — E2E tests require PostgreSQL",
)
class TestE2EEndpoints:
    """End-to-end endpoint tests."""

    @pytest.fixture
    def client(self, task_spec: AppSpec) -> TestClient:
        """Create a test client with clean database."""
        import os

        from dazzle_back.runtime.pg_backend import PostgresBackend

        database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/dazzle_test")
        # Clean Task table before each test for isolation
        try:
            db = PostgresBackend(database_url)
            with db.connection() as conn:
                conn.execute('DELETE FROM "Task"')
        except Exception:
            pass
        app = create_app(task_spec, database_url=database_url)
        return _TestClient(app)

    def test_health_endpoint(self, client: TestClient) -> None:
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_list_empty(self, client: TestClient) -> None:
        """Test listing tasks when empty."""
        response = client.get("/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_task(self, client: TestClient) -> None:
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

    def test_read_task(self, client: TestClient) -> None:
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

    def test_update_task(self, client: TestClient) -> None:
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

    def test_delete_task(self, client: TestClient) -> None:
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

    def test_crud_flow(self, client: TestClient) -> None:
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

    def test_db_info(self, client: TestClient) -> None:
        """Test database info endpoint."""
        response = client.get("/db-info")
        assert response.status_code == 200
        data = response.json()
        assert data["database_backend"] == "postgresql"
        assert "Task" in data["tables"]
