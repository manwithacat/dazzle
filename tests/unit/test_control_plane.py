"""
Unit tests for Dazzle Bar control plane endpoints.

Tests the /dazzle/dev/* endpoints for the Dazzle Bar developer overlay.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from dazzle_dnr_back.specs import BackendSpec

# Check if FastAPI is available (needed for integration tests)
try:
    import fastapi  # noqa: F401

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# These imports are safe - they only depend on Pydantic
from dazzle_dnr_back.runtime.control_plane import (
    DazzleBarState,
    ExportRequest,
    ExportResponse,
    FeedbackRequest,
    FeedbackResponse,
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


class TestFeedbackRequest:
    """Tests for FeedbackRequest model."""

    def test_feedback_request_minimal(self) -> None:
        """Test creating feedback request with minimal fields."""
        request = FeedbackRequest(message="Test feedback")
        assert request.message == "Test feedback"
        assert request.category is None
        assert request.persona_id is None
        assert request.scenario_id is None

    def test_feedback_request_full(self) -> None:
        """Test creating feedback request with all fields."""
        request = FeedbackRequest(
            message="Test feedback",
            category="bug",
            persona_id="teacher",
            scenario_id="busy_term",
            route="/classes",
            url="http://localhost:3000/classes",
            extra_context={"component": "TaskList"},
        )
        assert request.message == "Test feedback"
        assert request.category == "bug"
        assert request.persona_id == "teacher"
        assert request.extra_context == {"component": "TaskList"}


class TestFeedbackResponse:
    """Tests for FeedbackResponse model."""

    def test_feedback_response(self) -> None:
        """Test creating feedback response."""
        response = FeedbackResponse(status="logged", feedback_id="abc12345")
        assert response.status == "logged"
        assert response.feedback_id == "abc12345"


class TestExportRequest:
    """Tests for ExportRequest model."""

    def test_export_request_defaults(self) -> None:
        """Test creating export request with defaults."""
        request = ExportRequest()
        assert request.include_spec is True
        assert request.include_feedback is True
        assert request.include_session_data is False
        assert request.export_format == "github_issue"

    def test_export_request_custom(self) -> None:
        """Test creating export request with custom values."""
        request = ExportRequest(
            include_spec=False,
            include_feedback=False,
            include_session_data=True,
            export_format="json",
        )
        assert request.include_spec is False
        assert request.export_format == "json"


class TestExportResponse:
    """Tests for ExportResponse model."""

    def test_export_response_with_url(self) -> None:
        """Test creating export response with URL."""
        response = ExportResponse(
            status="generated",
            export_url="https://github.com/owner/repo/issues/new?title=test",
        )
        assert response.status == "generated"
        assert response.export_url is not None

    def test_export_response_with_data(self) -> None:
        """Test creating export response with data."""
        response = ExportResponse(
            status="exported",
            export_data={"timestamp": "2024-01-01T00:00:00"},
        )
        assert response.status == "exported"
        assert response.export_data is not None


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


class TestDazzleBarState:
    """Tests for DazzleBarState model."""

    def test_dazzle_bar_state_defaults(self) -> None:
        """Test creating dazzle bar state with defaults."""
        state = DazzleBarState()
        assert state.current_persona is None
        assert state.current_scenario is None
        assert state.available_personas == []
        assert state.available_scenarios == []
        assert state.dev_mode is True

    def test_dazzle_bar_state_full(self) -> None:
        """Test creating dazzle bar state with all fields."""
        state = DazzleBarState(
            current_persona="teacher",
            current_scenario="busy_term",
            available_personas=[{"id": "teacher", "label": "Teacher"}],
            available_scenarios=[{"id": "busy_term", "name": "Busy Term"}],
            dev_mode=True,
        )
        assert state.current_persona == "teacher"
        assert len(state.available_personas) == 1


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestControlPlaneIntegration:
    """Integration tests for control plane routes with real server.

    Uses a class-scoped fixture to share one FastAPI app/client across all tests.
    """

    @pytest.fixture(scope="class")
    def backend_spec(self) -> BackendSpec:
        """Create a test backend spec (class-scoped for reuse)."""
        from dazzle_dnr_back.specs import BackendSpec
        from dazzle_dnr_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType
        from dazzle_dnr_back.specs.service import DomainOperation, OperationKind, ServiceSpec

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
        from fastapi.testclient import TestClient

        from dazzle_dnr_back.runtime.server import create_app

        # Use tmp_path_factory for class-scoped fixtures
        tmp_path = tmp_path_factory.mktemp("control_plane")
        db_path = tmp_path / "test.db"
        feedback_dir = tmp_path / "feedback"

        app = create_app(
            backend_spec,
            db_path=str(db_path),
            enable_dev_mode=True,
            feedback_dir=str(feedback_dir),
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
        """Test getting complete Dazzle Bar state."""
        response = test_client.get("/dazzle/dev/state")
        assert response.status_code == 200
        data = response.json()
        assert "current_persona" in data
        assert "current_scenario" in data
        assert "available_personas" in data
        assert "available_scenarios" in data
        assert data["dev_mode"] is True
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
        """Test regenerating demo data."""
        response = test_client.post(
            "/dazzle/dev/regenerate",
            json={"entity_counts": {"Task": 5}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "regenerated"
        assert "counts" in data
        assert data["counts"]["Task"] == 5

    def test_submit_feedback(self, test_client: TestClient) -> None:
        """Test submitting feedback."""
        response = test_client.post(
            "/dazzle/dev/feedback",
            json={
                "message": "Test feedback message",
                "category": "bug",
                "route": "/tasks",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "logged"
        assert "feedback_id" in data

    def test_export_github_issue(self, test_client: TestClient) -> None:
        """Test exporting session as GitHub issue URL."""
        response = test_client.post(
            "/dazzle/dev/export",
            json={"export_format": "github_issue"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "generated"
        assert "export_url" in data
        assert "github.com" in data["export_url"]

    def test_export_json(self, test_client: TestClient) -> None:
        """Test exporting session as JSON."""
        response = test_client.post(
            "/dazzle/dev/export",
            json={"export_format": "json"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "exported"
        assert "export_data" in data

    def test_inspect_entities(self, test_client: TestClient) -> None:
        """Test inspecting entity schemas."""
        response = test_client.get("/dazzle/dev/inspect/entities")
        assert response.status_code == 200
        data = response.json()
        assert "entities" in data
        assert len(data["entities"]) == 1
        assert data["entities"][0]["name"] == "Task"
        assert "fields" in data["entities"][0]

    def test_inspect_routes(self, test_client: TestClient) -> None:
        """Test inspecting registered routes."""
        response = test_client.get("/dazzle/dev/inspect/routes")
        assert response.status_code == 200
        data = response.json()
        assert "routes" in data


class TestDazzleBarBundle:
    """Tests for Dazzle Bar JavaScript bundle generation."""

    def test_get_dazzle_bar_js(self) -> None:
        """Test that the Dazzle Bar JavaScript bundle generates correctly."""
        from dazzle_dnr_ui.runtime.js_loader import get_dazzle_bar_js

        js = get_dazzle_bar_js()

        # Should contain the header
        assert "Dazzle Bar - Developer Overlay" in js

        # Should contain signals.js dependency
        assert "signals.js (dependency)" in js

        # Should contain the bar modules
        assert "dazzle-bar/runtime.js" in js
        assert "dazzle-bar/bar.js" in js
        assert "dazzle-bar/index.js" in js

        # Should contain key functions (with exports stripped)
        assert "function createSignal" in js
        assert "function initDazzleBar" in js
        assert "const DazzleRuntime" in js

        # Should NOT contain import statements (stripped)
        assert "import { createSignal }" not in js
        assert "import { createEffect }" not in js

    def test_dazzle_bar_bundle_size(self) -> None:
        """Test that the bundle is within reasonable size."""
        from dazzle_dnr_ui.runtime.js_loader import get_dazzle_bar_js

        js = get_dazzle_bar_js()

        # Bundle should be between 20KB and 100KB
        assert 20000 < len(js) < 100000, f"Bundle size {len(js)} bytes is out of expected range"


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestDevModeDisabled:
    """Test that control plane endpoints are not available when dev mode is disabled."""

    @pytest.fixture(scope="class")
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

    @pytest.fixture(scope="class")
    def test_client(
        self, backend_spec: BackendSpec, tmp_path_factory: pytest.TempPathFactory
    ) -> TestClient:
        """Create a test client WITHOUT dev mode enabled."""
        from fastapi.testclient import TestClient

        from dazzle_dnr_back.runtime.server import create_app

        tmp_path = tmp_path_factory.mktemp("dev_disabled")
        db_path = tmp_path / "test.db"
        app = create_app(
            backend_spec,
            db_path=str(db_path),
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

    def test_feedback_not_available(self, test_client: TestClient) -> None:
        """Test that feedback endpoint is not available when dev mode disabled."""
        response = test_client.post(
            "/dazzle/dev/feedback",
            json={"message": "Test"},
        )
        assert response.status_code == 404
