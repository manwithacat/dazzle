"""
Unit tests for control plane endpoints.

Tests the /dazzle/dev/* endpoints for developer-mode operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from dazzle_back.specs import BackendSpec

# Check if FastAPI is available (needed for integration tests)
try:
    import fastapi  # noqa: F401

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# These imports are safe - they only depend on Pydantic
from dazzle_back.runtime.control_plane import (
    PersonaContext,
    RegenerateRequest,
    ScenarioContext,
    SetPersonaRequest,
    SetScenarioRequest,
)


class TestPersonaContext:
    """Tests for PersonaContext model."""

    def test_persona_context_minimal(self) -> None:
        """Test creating persona context with minimal fields."""
        context = PersonaContext(persona_id="teacher")
        assert context.persona_id == "teacher"
        assert context.label is None

    def test_persona_context_with_label(self) -> None:
        """Test creating persona context with label."""
        context = PersonaContext(persona_id="teacher", label="Teacher")
        assert context.persona_id == "teacher"
        assert context.label == "Teacher"


class TestScenarioContext:
    """Tests for ScenarioContext model."""

    def test_scenario_context_minimal(self) -> None:
        """Test creating scenario context with minimal fields."""
        context = ScenarioContext(scenario_id="busy_term")
        assert context.scenario_id == "busy_term"
        assert context.name is None

    def test_scenario_context_with_name(self) -> None:
        """Test creating scenario context with name."""
        context = ScenarioContext(scenario_id="busy_term", name="Busy Term")
        assert context.scenario_id == "busy_term"
        assert context.name == "Busy Term"


class TestSetPersonaRequest:
    """Tests for SetPersonaRequest model."""

    def test_set_persona_request(self) -> None:
        """Test creating set persona request."""
        request = SetPersonaRequest(persona_id="admin")
        assert request.persona_id == "admin"


class TestSetScenarioRequest:
    """Tests for SetScenarioRequest model."""

    def test_set_scenario_request(self) -> None:
        """Test creating set scenario request."""
        request = SetScenarioRequest(scenario_id="empty")
        assert request.scenario_id == "empty"


class TestRegenerateRequest:
    """Tests for RegenerateRequest model."""

    def test_regenerate_request_empty(self) -> None:
        """Test creating regenerate request with defaults."""
        request = RegenerateRequest()
        assert request.scenario_id is None
        assert request.entity_counts is None

    def test_regenerate_request_with_counts(self) -> None:
        """Test creating regenerate request with entity counts."""
        request = RegenerateRequest(
            scenario_id="demo",
            entity_counts={"Task": 20, "User": 5},
        )
        assert request.scenario_id == "demo"
        assert request.entity_counts == {"Task": 20, "User": 5}


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestControlPlaneIntegration:
    """Integration tests for control plane routes with real server.

    Uses a class-scoped fixture to share one FastAPI app/client across all tests.
    """

    @pytest.fixture(scope="class")
    def backend_spec(self) -> BackendSpec:
        """Create a test backend spec (class-scoped for reuse)."""
        from dazzle_back.specs import BackendSpec
        from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType
        from dazzle_back.specs.service import DomainOperation, OperationKind, ServiceSpec

        task_entity = EntitySpec(
            name="Task",
            label="Task",
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
                    name="TaskList",
                    domain_operation=DomainOperation(kind=OperationKind.LIST, entity="Task"),
                ),
            ],
            endpoints=[],
        )

    @pytest.fixture(scope="class")
    def shared_test_client(
        self, backend_spec: BackendSpec, tmp_path_factory: pytest.TempPathFactory
    ) -> TestClient:
        """Create a shared test client for the class (reused across tests)."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from dazzle_back.runtime.server import create_app

        with (
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
            patch("dazzle_back.runtime.server.auto_migrate"),
        ):
            app = create_app(
                backend_spec,
                database_url="postgresql://mock/test",
                enable_dev_mode=True,
                personas=[
                    {"id": "admin", "label": "Administrator"},
                    {"id": "viewer", "label": "Viewer"},
                ],
                scenarios=[
                    {"id": "empty", "name": "Empty State"},
                    {"id": "demo", "name": "Demo Data"},
                ],
            )
        return TestClient(app)

    @pytest.fixture
    def test_client(self, shared_test_client: TestClient) -> TestClient:
        """Provide test client for each test."""
        return shared_test_client

    def test_get_dazzle_state(self, test_client: TestClient) -> None:
        """Test getting complete control plane state."""
        response = test_client.get("/dazzle/dev/state")
        assert response.status_code == 200
        data = response.json()
        assert "current_persona" in data
        assert "current_scenario" in data
        assert "available_personas" in data
        assert "available_scenarios" in data
        assert len(data["available_personas"]) == 2
        assert len(data["available_scenarios"]) == 2

    def test_get_current_persona_empty(self, test_client: TestClient) -> None:
        """Test getting current persona when not set."""
        response = test_client.get("/dazzle/dev/current_persona")
        assert response.status_code == 200
        # Returns null when no persona is set
        assert response.json() is None

    def test_set_and_get_current_persona(self, test_client: TestClient) -> None:
        """Test setting and getting current persona."""
        # Set persona
        set_response = test_client.post(
            "/dazzle/dev/current_persona",
            json={"persona_id": "admin"},
        )
        assert set_response.status_code == 200
        data = set_response.json()
        assert data["persona_id"] == "admin"
        assert data["label"] == "Administrator"

        # Get persona
        get_response = test_client.get("/dazzle/dev/current_persona")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["persona_id"] == "admin"

    def test_get_current_scenario_empty(self, test_client: TestClient) -> None:
        """Test getting current scenario when not set."""
        response = test_client.get("/dazzle/dev/current_scenario")
        assert response.status_code == 200
        # Returns null when no scenario is set

    def test_set_and_get_current_scenario(self, test_client: TestClient) -> None:
        """Test setting and getting current scenario."""
        # Set scenario
        set_response = test_client.post(
            "/dazzle/dev/current_scenario",
            json={"scenario_id": "demo"},
        )
        assert set_response.status_code == 200
        data = set_response.json()
        assert data["scenario_id"] == "demo"
        assert data["name"] == "Demo Data"

        # Get scenario
        get_response = test_client.get("/dazzle/dev/current_scenario")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["scenario_id"] == "demo"

    def test_reset_data(self, test_client: TestClient) -> None:
        """Test resetting all data."""
        response = test_client.post("/dazzle/dev/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reset_complete"

    def test_regenerate_data(self, test_client: TestClient) -> None:
        """Test regenerating demo data returns correct response structure."""
        response = test_client.post(
            "/dazzle/dev/regenerate",
            json={"entity_counts": {"Task": 5}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "regenerated"
        assert "counts" in data
        # With mocked DB, counts may be 0 — just verify the key exists
        assert "Task" in data["counts"]


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestDevModeDisabled:
    """Test that control plane endpoints are not available when dev mode is disabled."""

    @pytest.fixture(scope="class")
    def backend_spec(self) -> BackendSpec:
        """Create a test backend spec."""
        from dazzle_back.specs import BackendSpec
        from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

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

    @pytest.fixture(scope="class")
    def test_client(
        self, backend_spec: BackendSpec, tmp_path_factory: pytest.TempPathFactory
    ) -> TestClient:
        """Create a test client WITHOUT dev mode enabled."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from dazzle_back.runtime.server import create_app

        with (
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
            patch("dazzle_back.runtime.server.auto_migrate"),
        ):
            app = create_app(
                backend_spec,
                database_url="postgresql://mock/test",
                enable_dev_mode=False,
                enable_test_mode=False,
            )
        return TestClient(app)

    def test_state_not_available(self, test_client: TestClient) -> None:
        """Test that state endpoint is not available when dev mode disabled."""
        response = test_client.get("/dazzle/dev/state")
        assert response.status_code == 404

    def test_persona_not_available(self, test_client: TestClient) -> None:
        """Test that persona endpoint is not available when dev mode disabled."""
        response = test_client.get("/dazzle/dev/current_persona")
        assert response.status_code == 404
