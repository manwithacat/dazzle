"""
Tests for social auth wiring in server.py.

Verifies that OAuth social login routes are correctly wired when
configured in the manifest.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

# Check if FastAPI is available
try:
    import fastapi  # noqa: F401

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Skip all tests in this module if FastAPI is not installed
pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")

if TYPE_CHECKING:
    from dazzle_dnr_back.specs import BackendSpec


@dataclass
class MockAuthOAuthProvider:
    """Mock OAuth provider config matching manifest.AuthOAuthProvider."""

    provider: str
    client_id_env: str
    client_secret_env: str
    scopes: list[str] = field(default_factory=list)


@dataclass
class MockAuthJwtConfig:
    """Mock JWT config."""

    access_token_minutes: int = 15
    refresh_token_days: int = 7


@dataclass
class MockAuthConfig:
    """Mock auth config matching manifest.AuthConfig."""

    enabled: bool = True
    provider: str = "session"
    oauth_providers: list[MockAuthOAuthProvider] = field(default_factory=list)
    jwt: MockAuthJwtConfig = field(default_factory=MockAuthJwtConfig)


@pytest.fixture
def minimal_backend_spec() -> BackendSpec:
    """Create a minimal backend spec for testing."""
    from dazzle_dnr_back.specs import BackendSpec

    return BackendSpec(
        name="test_app",
        version="1.0.0",
        entities=[],
        services=[],
        endpoints=[],
    )


class TestSocialAuthWiring:
    """Tests for social auth route wiring."""

    def test_no_oauth_config_no_social_routes(
        self, minimal_backend_spec: BackendSpec, tmp_path
    ) -> None:
        """Server starts normally without OAuth config."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        app_builder = DNRBackendApp(
            minimal_backend_spec,
            db_path=tmp_path / "data.db",
            enable_auth=True,
            auth_config=None,  # No auth config
        )
        app = app_builder.build()

        # Check that /auth/social routes are NOT present
        routes = [r.path for r in app.routes]
        social_routes = [r for r in routes if "/auth/social" in r]
        assert len(social_routes) == 0, "Social routes should not be present"

    def test_empty_oauth_providers_no_social_routes(
        self, minimal_backend_spec: BackendSpec, tmp_path
    ) -> None:
        """Server starts normally with empty oauth_providers list."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        auth_config = MockAuthConfig(
            enabled=True,
            oauth_providers=[],  # Empty list
        )

        app_builder = DNRBackendApp(
            minimal_backend_spec,
            db_path=tmp_path / "data.db",
            enable_auth=True,
            auth_config=auth_config,
        )
        app = app_builder.build()

        # Check that /auth/social routes are NOT present
        routes = [r.path for r in app.routes]
        social_routes = [r for r in routes if "/auth/social" in r]
        assert len(social_routes) == 0, "Social routes should not be present"

    def test_oauth_config_with_env_vars_creates_social_routes(
        self, minimal_backend_spec: BackendSpec, tmp_path
    ) -> None:
        """Social routes are created when OAuth is configured with valid env vars."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        auth_config = MockAuthConfig(
            enabled=True,
            oauth_providers=[
                MockAuthOAuthProvider(
                    provider="google",
                    client_id_env="TEST_GOOGLE_CLIENT_ID",
                    client_secret_env="TEST_GOOGLE_CLIENT_SECRET",
                ),
            ],
        )

        # Set environment variable
        with patch.dict(os.environ, {"TEST_GOOGLE_CLIENT_ID": "test-client-id"}):
            app_builder = DNRBackendApp(
                minimal_backend_spec,
                db_path=tmp_path / "data.db",
                enable_auth=True,
                auth_config=auth_config,
            )
            app = app_builder.build()

            # Check that /auth/social routes ARE present
            routes = [r.path for r in app.routes]
            social_routes = [r for r in routes if "/auth/social" in r]
            assert len(social_routes) > 0, "Social routes should be present"

    def test_missing_env_vars_logs_warning_but_does_not_crash(
        self, minimal_backend_spec: BackendSpec, tmp_path, caplog
    ) -> None:
        """Missing env vars log warning but server still starts."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        auth_config = MockAuthConfig(
            enabled=True,
            oauth_providers=[
                MockAuthOAuthProvider(
                    provider="google",
                    client_id_env="NONEXISTENT_GOOGLE_ID",
                    client_secret_env="NONEXISTENT_GOOGLE_SECRET",
                ),
            ],
        )

        # Ensure env var is NOT set
        env_without_google = {k: v for k, v in os.environ.items() if "NONEXISTENT_GOOGLE" not in k}
        with patch.dict(os.environ, env_without_google, clear=True):
            app_builder = DNRBackendApp(
                minimal_backend_spec,
                db_path=tmp_path / "data.db",
                enable_auth=True,
                auth_config=auth_config,
            )
            # Should not raise
            app = app_builder.build()

            # Server should still be usable
            assert app is not None

    def test_multiple_providers_configured(
        self, minimal_backend_spec: BackendSpec, tmp_path
    ) -> None:
        """Multiple OAuth providers can be configured."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        auth_config = MockAuthConfig(
            enabled=True,
            oauth_providers=[
                MockAuthOAuthProvider(
                    provider="google",
                    client_id_env="TEST_GOOGLE_ID",
                    client_secret_env="TEST_GOOGLE_SECRET",
                ),
                MockAuthOAuthProvider(
                    provider="github",
                    client_id_env="TEST_GITHUB_ID",
                    client_secret_env="TEST_GITHUB_SECRET",
                ),
            ],
        )

        env_vars = {
            "TEST_GOOGLE_ID": "google-client-id",
            "TEST_GITHUB_ID": "github-client-id",
            "TEST_GITHUB_SECRET": "github-client-secret",
        }

        with patch.dict(os.environ, env_vars):
            app_builder = DNRBackendApp(
                minimal_backend_spec,
                db_path=tmp_path / "data.db",
                enable_auth=True,
                auth_config=auth_config,
            )
            app = app_builder.build()

            # Check social routes exist
            routes = [r.path for r in app.routes]
            social_routes = [r for r in routes if "/auth/social" in r]
            assert len(social_routes) > 0, "Social routes should be present"

    def test_auth_disabled_no_social_routes(
        self, minimal_backend_spec: BackendSpec, tmp_path
    ) -> None:
        """When auth is disabled, no social routes even if OAuth is configured."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        auth_config = MockAuthConfig(
            enabled=True,
            oauth_providers=[
                MockAuthOAuthProvider(
                    provider="google",
                    client_id_env="TEST_GOOGLE_ID",
                    client_secret_env="TEST_GOOGLE_SECRET",
                ),
            ],
        )

        with patch.dict(os.environ, {"TEST_GOOGLE_ID": "test-id"}):
            app_builder = DNRBackendApp(
                minimal_backend_spec,
                db_path=tmp_path / "data.db",
                enable_auth=False,  # Auth disabled
                auth_config=auth_config,
            )
            app = app_builder.build()

            # Check that /auth/social routes are NOT present
            routes = [r.path for r in app.routes]
            social_routes = [r for r in routes if "/auth/social" in r]
            assert len(social_routes) == 0, "Social routes should not be present"


class TestBuildSocialAuthConfig:
    """Tests for _build_social_auth_config helper method."""

    def test_google_provider_extracts_client_id(self, tmp_path) -> None:
        """Google provider correctly extracts client_id from env."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp
        from dazzle_dnr_back.specs import BackendSpec

        spec = BackendSpec(name="test", entities=[], services=[], endpoints=[])

        app_builder = DNRBackendApp(
            spec,
            db_path=tmp_path / "data.db",
            enable_auth=True,
        )

        providers = [
            MockAuthOAuthProvider(
                provider="google",
                client_id_env="MY_GOOGLE_ID",
                client_secret_env="MY_GOOGLE_SECRET",
            ),
        ]

        with patch.dict(os.environ, {"MY_GOOGLE_ID": "google-12345"}):
            config = app_builder._build_social_auth_config(providers)

        assert config is not None
        assert config.google_client_id == "google-12345"

    def test_github_provider_extracts_id_and_secret(self, tmp_path) -> None:
        """GitHub provider correctly extracts client_id and secret from env."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp
        from dazzle_dnr_back.specs import BackendSpec

        spec = BackendSpec(name="test", entities=[], services=[], endpoints=[])

        app_builder = DNRBackendApp(
            spec,
            db_path=tmp_path / "data.db",
            enable_auth=True,
        )

        providers = [
            MockAuthOAuthProvider(
                provider="github",
                client_id_env="MY_GITHUB_ID",
                client_secret_env="MY_GITHUB_SECRET",
            ),
        ]

        env = {
            "MY_GITHUB_ID": "github-id-123",
            "MY_GITHUB_SECRET": "github-secret-456",
        }
        with patch.dict(os.environ, env):
            config = app_builder._build_social_auth_config(providers)

        assert config is not None
        assert config.github_client_id == "github-id-123"
        assert config.github_client_secret == "github-secret-456"

    def test_returns_none_when_no_providers_configured(self, tmp_path) -> None:
        """Returns None when no providers have valid credentials."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp
        from dazzle_dnr_back.specs import BackendSpec

        spec = BackendSpec(name="test", entities=[], services=[], endpoints=[])

        app_builder = DNRBackendApp(
            spec,
            db_path=tmp_path / "data.db",
            enable_auth=True,
        )

        providers = [
            MockAuthOAuthProvider(
                provider="google",
                client_id_env="MISSING_ENV_VAR",
                client_secret_env="ALSO_MISSING",
            ),
        ]

        # Don't set any env vars
        config = app_builder._build_social_auth_config(providers)
        assert config is None
