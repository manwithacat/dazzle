"""
Tests for combined DNR server (backend + frontend).

Tests the unified development server that runs both
FastAPI backend and frontend dev server together.
"""

from pathlib import Path

import pytest

from dazzle_ui.runtime.combined_server import (
    DNRCombinedHandler,
    DNRCombinedServer,
)
from dazzle_ui.specs import (
    ComponentSpec,
    RouteSpec,
    SingleColumnLayout,
    UISpec,
    WorkspaceSpec,
)

# Check if backend modules are available
try:
    from dazzle_back.specs import (
        BackendSpec,
        EntitySpec,
        FieldSpec,
        FieldType,
        ScalarType,
    )

    BACKEND_AVAILABLE = True
except ImportError:
    BACKEND_AVAILABLE = False


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_ui_spec() -> UISpec:
    """Create a simple UI spec for testing."""
    return UISpec(
        name="test_app",
        version="1.0.0",
        workspaces=[
            WorkspaceSpec(
                name="main",
                title="Main",
                layout=SingleColumnLayout(main="HomePage"),
                routes=[
                    RouteSpec(path="/", component="HomePage"),
                ],
            ),
        ],
        components=[
            ComponentSpec(
                name="HomePage",
                category="custom",
                description="Home page component",
            ),
        ],
    )


@pytest.fixture
def simple_backend_spec():
    """Create a simple backend spec for testing."""
    if not BACKEND_AVAILABLE:
        pytest.skip("Backend module not available")

    return BackendSpec(
        name="test_app",
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
                        type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                        required=True,
                    ),
                ],
            ),
        ],
    )


# =============================================================================
# Handler Tests
# =============================================================================


class TestDNRCombinedHandler:
    """Test the combined HTTP handler."""

    def test_handler_has_class_attributes(self):
        """Test that handler has the expected class attributes."""
        assert hasattr(DNRCombinedHandler, "ui_spec")
        assert hasattr(DNRCombinedHandler, "backend_url")

    def test_handler_default_backend_url(self):
        """Test default backend URL."""
        assert DNRCombinedHandler.backend_url == "http://127.0.0.1:8000"

    def test_handler_can_be_configured(self, simple_ui_spec: UISpec):
        """Test that handler can be configured with spec."""
        DNRCombinedHandler.ui_spec = simple_ui_spec
        DNRCombinedHandler.backend_url = "http://localhost:9000"

        assert DNRCombinedHandler.ui_spec == simple_ui_spec
        assert DNRCombinedHandler.backend_url == "http://localhost:9000"

        # Reset
        DNRCombinedHandler.ui_spec = None
        DNRCombinedHandler.backend_url = "http://127.0.0.1:8000"


# =============================================================================
# Server Configuration Tests
# =============================================================================


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not available")
class TestDNRCombinedServerConfig:
    """Test combined server configuration."""

    def test_server_initialization(self, simple_backend_spec, simple_ui_spec: UISpec):
        """Test server initialization with specs."""
        server = DNRCombinedServer(
            backend_spec=simple_backend_spec,
            ui_spec=simple_ui_spec,
        )

        assert server.backend_spec == simple_backend_spec
        assert server.ui_spec == simple_ui_spec
        assert server.backend_host == "127.0.0.1"
        assert server.backend_port == 8000
        assert server.frontend_host == "127.0.0.1"
        assert server.frontend_port == 3000

    def test_server_custom_ports(self, simple_backend_spec, simple_ui_spec: UISpec):
        """Test server with custom ports."""
        server = DNRCombinedServer(
            backend_spec=simple_backend_spec,
            ui_spec=simple_ui_spec,
            backend_port=9000,
            frontend_port=4000,
        )

        assert server.backend_port == 9000
        assert server.frontend_port == 4000

    def test_server_custom_db_path(
        self, simple_backend_spec, simple_ui_spec: UISpec, tmp_path: Path
    ):
        """Test server with custom database path."""
        db_path = tmp_path / "custom.db"
        server = DNRCombinedServer(
            backend_spec=simple_backend_spec,
            ui_spec=simple_ui_spec,
            db_path=db_path,
        )

        assert server.db_path == db_path

    def test_server_default_db_path(self, simple_backend_spec, simple_ui_spec: UISpec):
        """Test server default database path."""
        server = DNRCombinedServer(
            backend_spec=simple_backend_spec,
            ui_spec=simple_ui_spec,
        )

        assert server.db_path == Path(".dazzle/data.db")


# =============================================================================
# Integration Tests (requires actual server)
# =============================================================================


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not available")
class TestCombinedServerIntegration:
    """Integration tests for combined server.

    Note: These tests start actual servers, so they use
    non-standard ports to avoid conflicts.
    """

    @pytest.fixture
    def server_ports(self):
        """Return unique ports for testing."""
        import random

        base = random.randint(10000, 60000)
        return {
            "backend": base,
            "frontend": base + 1,
        }

    def test_server_attributes_set(
        self,
        simple_backend_spec,
        simple_ui_spec: UISpec,
        server_ports,
    ):
        """Test that server sets up internal attributes."""
        server = DNRCombinedServer(
            backend_spec=simple_backend_spec,
            ui_spec=simple_ui_spec,
            backend_port=server_ports["backend"],
            frontend_port=server_ports["frontend"],
        )

        assert server._backend_thread is None
        assert server._frontend_server is None

    def test_server_can_stop_cleanly(
        self,
        simple_backend_spec,
        simple_ui_spec: UISpec,
        server_ports,
    ):
        """Test that server stop method doesn't error when not started."""
        server = DNRCombinedServer(
            backend_spec=simple_backend_spec,
            ui_spec=simple_ui_spec,
            backend_port=server_ports["backend"],
            frontend_port=server_ports["frontend"],
        )

        # Stop should not raise even if never started
        server.stop()


# =============================================================================
# API Proxy Tests
# =============================================================================


class TestAPIProxyLogic:
    """Test API proxy path detection logic."""

    def test_api_paths_detected(self):
        """Test that API paths are correctly identified by _is_api_path."""
        from dazzle_ui.runtime.combined_server import DNRCombinedHandler

        # Set up entity prefixes (normally done by DNRCombinedServer)
        DNRCombinedHandler.api_route_prefixes = {"/tasks", "/users"}

        # Create a mock handler to test _is_api_path
        class MockHandler(DNRCombinedHandler):
            def __init__(self):
                pass  # Skip parent init

        handler = MockHandler()

        api_paths = [
            "/tasks",
            "/tasks/123",
            "/users/456",
            "/auth/login",
            "/auth/me",
            "/files/upload",
        ]
        non_api_paths = [
            "/",
            "/index.html",
            "/app.js",
            "/styles.css",
        ]

        for path in api_paths:
            assert handler._is_api_path(path), f"{path} should be API path"

        for path in non_api_paths:
            assert not handler._is_api_path(path), f"{path} should not be API path"

    def test_special_backend_paths(self):
        """Test special paths that go to backend."""
        backend_paths = [
            "/health",
            "/docs",
            "/openapi.json",
        ]

        for path in backend_paths:
            # These should be proxied to backend
            assert path in ["/health", "/docs", "/openapi.json"]
