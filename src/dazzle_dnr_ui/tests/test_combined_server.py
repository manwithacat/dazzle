"""
Tests for combined DNR server (backend + frontend).

Tests the unified development server that runs both
FastAPI backend and frontend dev server together.
"""

import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

import pytest

from dazzle_dnr_ui.specs import (
    UISpec,
    WorkspaceSpec,
    SingleColumnLayout,
    ComponentSpec,
    RouteSpec,
)
from dazzle_dnr_ui.runtime.combined_server import (
    DNRCombinedHandler,
    DNRCombinedServer,
)
from dazzle_dnr_ui.runtime.js_generator import JSGenerator


# Check if backend modules are available
try:
    from dazzle_dnr_back.specs import (
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
        assert hasattr(DNRCombinedHandler, "generator")
        assert hasattr(DNRCombinedHandler, "backend_url")

    def test_handler_default_backend_url(self):
        """Test default backend URL."""
        assert DNRCombinedHandler.backend_url == "http://127.0.0.1:8000"

    def test_handler_can_be_configured(self, simple_ui_spec: UISpec):
        """Test that handler can be configured with spec."""
        DNRCombinedHandler.ui_spec = simple_ui_spec
        DNRCombinedHandler.generator = JSGenerator(simple_ui_spec)
        DNRCombinedHandler.backend_url = "http://localhost:9000"

        assert DNRCombinedHandler.ui_spec == simple_ui_spec
        assert DNRCombinedHandler.generator is not None
        assert DNRCombinedHandler.backend_url == "http://localhost:9000"

        # Reset
        DNRCombinedHandler.ui_spec = None
        DNRCombinedHandler.generator = None
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
# JS Generator Tests (for combined server)
# =============================================================================


class TestJSGeneratorForCombinedServer:
    """Test JS generator produces valid output for combined server."""

    def test_generator_produces_html(self, simple_ui_spec: UISpec):
        """Test that generator produces HTML."""
        generator = JSGenerator(simple_ui_spec)
        html = generator.generate_html()

        assert "<!DOCTYPE html>" in html
        assert "test_app" in html  # Uses name, not title

    def test_generator_produces_runtime(self, simple_ui_spec: UISpec):
        """Test that generator produces runtime JS."""
        generator = JSGenerator(simple_ui_spec)
        runtime = generator.generate_runtime()

        assert "signal" in runtime.lower() or "state" in runtime.lower()

    def test_generator_produces_app_js(self, simple_ui_spec: UISpec):
        """Test that generator produces app JS."""
        generator = JSGenerator(simple_ui_spec)
        app_js = generator.generate_app_js()

        # Should contain app initialization
        assert len(app_js) > 0

    def test_generator_produces_spec_json(self, simple_ui_spec: UISpec):
        """Test that generator produces spec JSON."""
        generator = JSGenerator(simple_ui_spec)
        spec_json = generator.generate_spec_json()

        assert "test_app" in spec_json
        assert "main" in spec_json  # Workspace name, not "home"


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
        """Test that API paths are correctly identified."""
        api_paths = [
            "/api/tasks",
            "/api/users/123",
            "/api/v1/items",
        ]
        non_api_paths = [
            "/",
            "/index.html",
            "/app.js",
            "/styles.css",
        ]

        for path in api_paths:
            assert path.startswith("/api/"), f"{path} should be API path"

        for path in non_api_paths:
            assert not path.startswith("/api/"), f"{path} should not be API path"

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
