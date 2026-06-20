"""
Unit tests for Dazzle test endpoints.

Tests the /__test__/* endpoints for E2E testing support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from dazzle.core.ir.appspec import AppSpec

# These imports are safe - they only depend on Pydantic
from dazzle.http.runtime.test_routes import (
    AuthenticateRequest,
    AuthenticateResponse,
    FixtureData,
    SeedRequest,
    SeedResponse,
    SnapshotResponse,
    _mirror_auth_user_to_domain,
)


class _CaptureConn:
    """A fake DB connection capturing the SQL + params the mirror runs."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self) -> _CaptureConn:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def commit(self) -> None:
        return None


class TestMirrorAuthUserSchemaDerived:
    """#1398 (now ADR-0039 Slice 3): the auth->domain User mirror derives columns from
    the entity's actual schema (the undeclared/best-effort path), not a hard-coded
    name/role/is_active set. The mirror reads the core-IR `User` via deps.user_ir_spec."""

    def _deps(self, user_dsl_fields: str) -> tuple[object, _CaptureConn]:
        from pathlib import Path
        from types import SimpleNamespace

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = 'module t\napp t "T"\nentity User "User":\n  id: uuid pk\n' + user_dsl_fields
        _n, _a, _t, _c, _u, frag = parse_dsl(dsl, Path("t.dsl"))
        user = next(e for e in frag.entities if e.name == "User")
        conn = _CaptureConn()
        deps = SimpleNamespace(
            user_ir_spec=user,
            db_manager=SimpleNamespace(connection=lambda: conn),
        )
        return deps, conn

    def test_username_display_name_schema_no_name_column(self) -> None:
        # The exact repro: User has username/display_name, no name/role/is_active.
        deps, conn = self._deps(
            "  email: str(120) required\n  username: str(40)\n  display_name: str(80)\n"
        )
        _mirror_auth_user_to_domain(deps, "u-1", "alice@example.com", "Alice", "admin")
        assert len(conn.executed) == 1
        sql, params = conn.executed[0]
        # Only declared columns are referenced -- no UndefinedColumn.
        assert '"username"' in sql and '"display_name"' in sql
        assert '"email"' in sql and "id" in sql
        assert '"name"' not in sql and '"role"' not in sql and '"is_active"' not in sql
        assert "ON CONFLICT (id) DO UPDATE" in sql
        assert "Alice" in params

    def test_classic_name_role_is_active_schema_still_works(self) -> None:
        deps, conn = self._deps(
            "  email: str(120) required\n  name: str(80)\n  role: str(40)\n  is_active: bool=true\n"
        )
        _mirror_auth_user_to_domain(deps, "u-2", "bob@example.com", "Bob", "member")
        sql, params = conn.executed[0]
        assert '"name"' in sql and '"role"' in sql and '"is_active"' in sql
        assert "Bob" in params and "member" in params and True in params

    def test_no_user_entity_is_noop(self) -> None:
        from types import SimpleNamespace

        # No User entity → user_ir_spec is None → mirror is a no-op (must not touch the DB).
        conn = _CaptureConn()
        deps = SimpleNamespace(
            user_ir_spec=None, db_manager=SimpleNamespace(connection=lambda: conn)
        )
        _mirror_auth_user_to_domain(deps, "u-3", "c@example.com", "Cara", "admin")
        assert conn.executed == []


class TestFixtureData:
    """Tests for FixtureData model."""

    def test_fixture_data_minimal_and_with_refs(self) -> None:
        """Minimal FixtureData has refs=None; refs round-trip when supplied."""
        minimal = FixtureData(id="task_1", entity="Task", data={"title": "Test Task"})
        assert minimal.id == "task_1"
        assert minimal.entity == "Task"
        assert minimal.data == {"title": "Test Task"}
        assert minimal.refs is None

        with_refs = FixtureData(
            id="task_1",
            entity="Task",
            data={"title": "Test Task"},
            refs={"project_id": "project_1"},
        )
        assert with_refs.refs == {"project_id": "project_1"}


class TestSeedRequest:
    """Tests for SeedRequest model."""

    def test_seed_request_empty_and_with_fixtures(self) -> None:
        """Empty fixtures list and multi-fixture round-trip both work."""
        assert SeedRequest(fixtures=[]).fixtures == []

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

    def test_seed_response_empty_and_with_created(self) -> None:
        """Empty and populated `created` map both serialise correctly."""
        assert SeedResponse(created={}).created == {}

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

    def test_snapshot_response_empty_and_with_entities(self) -> None:
        """Empty and multi-entity snapshot responses round-trip correctly."""
        assert SnapshotResponse(entities={}).entities == {}

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

    def test_authenticate_request_defaults_and_values(self) -> None:
        """Defaults are None; supplied values round-trip."""
        default = AuthenticateRequest()
        assert default.username is None
        assert default.password is None
        assert default.role is None

        filled = AuthenticateRequest(username="testuser", password="testpass", role="admin")
        assert filled.username == "testuser"
        assert filled.password == "testpass"
        assert filled.role == "admin"


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


class TestSeedFieldFiltering:
    """Tests that seed endpoint filters fixture data to known entity fields."""

    def test_seed_filters_unknown_fields(self) -> None:
        """Verify that seed_fixtures strips fields not in the entity spec.

        This prevents SQL errors when fixture generators include stale or
        incorrect field names (e.g. 'domain' for an entity that has no
        such column).
        """
        import inspect

        from dazzle.http.runtime.test_routes import _seed_fixtures

        source = inspect.getsource(_seed_fixtures)
        assert "known_fields" in source, (
            "seed_fixtures must define known_fields to filter fixture data"
        )
        assert "repo._field_types" in source, (
            "seed_fixtures must use repo._field_types to determine known fields"
        )

    def test_field_filtering_logic(self) -> None:
        """Test the actual filtering logic used in seed_fixtures."""
        # Simulate what seed_fixtures does
        mock_field_types = {"title": "str", "completed": "bool"}
        known_fields = set(mock_field_types) | {"id"}

        fixture_data = {
            "title": "Test Task",
            "completed": True,
            "domain": "unknown_field",
            "status": "also_unknown",
        }

        filtered = {k: v for k, v in fixture_data.items() if k in known_fields}

        assert filtered == {"title": "Test Task", "completed": True}
        assert "domain" not in filtered
        assert "status" not in filtered

    def test_id_field_preserved(self) -> None:
        """Test that 'id' is always preserved even if not in _field_types."""
        mock_field_types = {"title": "str"}
        known_fields = set(mock_field_types) | {"id"}

        fixture_data = {"id": "abc-123", "title": "Test", "extra": "removed"}
        filtered = {k: v for k, v in fixture_data.items() if k in known_fields}

        assert filtered == {"id": "abc-123", "title": "Test"}


@pytest.mark.e2e
class TestTestRoutesIntegration:
    """Integration tests for test routes with real server.

    Uses a class-scoped fixture to share one FastAPI app/client across all tests,
    with automatic reset between tests to ensure isolation.

    Requires PostgreSQL — run with: pytest -m e2e
    """

    @pytest.fixture(scope="class")
    def database_url(self) -> str:
        """Get PostgreSQL URL from environment."""
        import os

        url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/dazzle_test")
        return url

    @pytest.fixture(scope="class")
    def appspec(self) -> AppSpec:
        """Create a test app spec (class-scoped for reuse)."""
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
    def shared_test_client(self, appspec: AppSpec, database_url: str) -> TestClient:
        """Create a shared test client for the class (reused across tests)."""
        from fastapi.testclient import TestClient

        from dazzle.http.runtime.app_factory import create_app

        app = create_app(
            appspec,
            database_url=database_url,
            enable_test_mode=True,
        )
        return TestClient(app)

    @pytest.fixture
    def test_client(self, shared_test_client: TestClient) -> TestClient:
        """Provide test client with automatic reset for test isolation."""
        # Reset data before each test to ensure isolation
        shared_test_client.post("/__test__/reset")
        return shared_test_client

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

    @pytest.mark.xfail(
        reason="SQLite connection isolation: seed writes via repo, count reads via db_manager"
    )
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


@pytest.mark.e2e
class TestTestModeDisabled:
    """Test that test endpoints are not available when test mode is disabled."""

    @pytest.fixture(scope="class")
    def database_url(self) -> str:
        """Get PostgreSQL URL from environment."""
        import os

        url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/dazzle_test")
        return url

    @pytest.fixture(scope="class")
    def appspec(self) -> AppSpec:
        """Create a test app spec."""
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
                    type=IRFieldType(kind=FieldTypeKind.STR),
                ),
            ],
        )

        return AppSpec(
            name="test_app",
            version="0.1.0",
            domain=DomainSpec(entities=[task_entity]),
        )

    @pytest.fixture(scope="class")
    def test_client(self, appspec: AppSpec, database_url: str) -> TestClient:
        """Create a test client WITHOUT test mode enabled."""
        from fastapi.testclient import TestClient

        from dazzle.http.runtime.app_factory import create_app

        app = create_app(
            appspec,
            database_url=database_url,
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
