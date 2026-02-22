"""
Tests for unified DNR server.

Tests the unified development server that runs a single FastAPI app
with both backend API and server-rendered UI on one port.
"""

import inspect

import pytest

from dazzle_ui.runtime.combined_server import (
    _clickable_url,
    _supports_hyperlinks,
    run_backend_only,
    run_unified_server,
)

# =============================================================================
# Terminal Utility Tests
# =============================================================================


class TestTerminalUtilities:
    """Test terminal helper functions."""

    def test_supports_hyperlinks_no_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """NO_COLOR disables hyperlinks."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setenv("TERM", "xterm-256color")
        assert _supports_hyperlinks() is False

    def test_supports_hyperlinks_no_term(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing TERM disables hyperlinks."""
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        assert _supports_hyperlinks() is False

    def test_supports_hyperlinks_dumb(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TERM=dumb disables hyperlinks."""
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        assert _supports_hyperlinks() is False

    def test_clickable_url_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Clickable URL falls back to plain text when unsupported."""
        monkeypatch.delenv("TERM", raising=False)
        assert _clickable_url("http://localhost:3000") == "http://localhost:3000"

    def test_clickable_url_with_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Clickable URL uses label in fallback mode."""
        monkeypatch.delenv("TERM", raising=False)
        assert _clickable_url("http://localhost:3000", "my app") == "my app"


# =============================================================================
# run_unified_server Signature Tests
# =============================================================================


class TestRunUnifiedServerSignature:
    """Test that run_unified_server has the expected interface."""

    def test_function_exists(self) -> None:
        """run_unified_server is importable."""
        assert callable(run_unified_server)

    def test_accepts_expected_params(self) -> None:
        """run_unified_server accepts all expected keyword arguments."""
        sig = inspect.signature(run_unified_server)
        expected = {
            "appspec",
            "ui_spec",
            "port",
            "db_path",
            "enable_test_mode",
            "enable_dev_mode",
            "enable_auth",
            "auth_config",
            "host",
            "enable_watch",
            "watch_source",
            "project_root",
            "personas",
            "scenarios",
            "sitespec_data",
            "theme_preset",
            "theme_overrides",
            "redis_url",
            "config",
        }
        assert expected == set(sig.parameters.keys())

    def test_default_port(self) -> None:
        """Default port is 3000."""
        sig = inspect.signature(run_unified_server)
        assert sig.parameters["port"].default == 3000

    def test_default_host(self) -> None:
        """Default host is 127.0.0.1."""
        sig = inspect.signature(run_unified_server)
        assert sig.parameters["host"].default == "127.0.0.1"


# =============================================================================
# run_backend_only Signature Tests
# =============================================================================


class TestRunBackendOnlySignature:
    """Test that run_backend_only has the expected interface."""

    def test_function_exists(self) -> None:
        """run_backend_only is importable."""
        assert callable(run_backend_only)

    def test_accepts_expected_params(self) -> None:
        """run_backend_only accepts all expected keyword arguments."""
        sig = inspect.signature(run_backend_only)
        expected = {
            "appspec",
            "host",
            "port",
            "db_path",
            "enable_test_mode",
            "enable_dev_mode",
            "enable_graphql",
            "sitespec_data",
            "project_root",
            "redis_url",
        }
        assert expected == set(sig.parameters.keys())


# =============================================================================
# Module Export Tests
# =============================================================================


class TestModuleExports:
    """Test that the runtime module exports the right names."""

    def test_run_unified_server_exported(self) -> None:
        """run_unified_server is available from dazzle_ui.runtime."""
        from dazzle_ui.runtime import run_unified_server as fn

        assert callable(fn)

    def test_run_backend_only_exported(self) -> None:
        """run_backend_only is available from dazzle_ui.runtime."""
        from dazzle_ui.runtime import run_backend_only as fn

        assert callable(fn)

    def test_old_combined_server_not_exported(self) -> None:
        """DNRCombinedHandler / DNRCombinedServer / run_combined_server are removed."""
        import dazzle_ui.runtime as mod

        assert not hasattr(mod, "DNRCombinedHandler")
        assert not hasattr(mod, "DNRCombinedServer")
        assert not hasattr(mod, "run_combined_server")
        assert not hasattr(mod, "run_frontend_only")
