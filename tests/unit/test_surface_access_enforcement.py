"""
Unit tests for surface access enforcement.

Tests the runtime check_surface_access() function with various
access configurations and user contexts.
"""

import pytest

from dazzle_back.runtime.surface_access import (
    SurfaceAccessConfig,
    SurfaceAccessDenied,
    check_surface_access,
)


class TestSurfaceAccessEnforcement:
    """Tests for check_surface_access() enforcement."""

    def test_public_surface_allows_anonymous(self) -> None:
        """Public surfaces allow access without authentication."""
        config = SurfaceAccessConfig(require_auth=False)
        # No exception raised for anonymous user
        check_surface_access(config, user=None, is_api_request=False)

    def test_authenticated_surface_rejects_anonymous(self) -> None:
        """Authenticated surfaces reject anonymous access."""
        config = SurfaceAccessConfig(require_auth=True, redirect_unauthenticated="/login")
        with pytest.raises(SurfaceAccessDenied) as exc_info:
            check_surface_access(config, user=None, is_api_request=False)
        assert exc_info.value.is_auth_required is True
        assert exc_info.value.redirect_url == "/login"

    def test_authenticated_surface_allows_logged_in(self) -> None:
        """Authenticated surfaces allow any logged-in user."""
        config = SurfaceAccessConfig(require_auth=True)
        user = {"id": "user-123", "email": "test@example.com"}
        # No exception raised for authenticated user
        check_surface_access(config, user=user, is_api_request=False)

    def test_persona_surface_allows_matching_persona(self) -> None:
        """Persona-restricted surfaces allow users with matching persona."""
        config = SurfaceAccessConfig(
            require_auth=True,
            allow_personas=["admin", "manager"],
        )
        user = {"id": "user-123"}
        check_surface_access(config, user=user, user_personas=["admin"], is_api_request=False)

    def test_persona_surface_rejects_wrong_persona(self) -> None:
        """Persona-restricted surfaces reject users without matching persona."""
        config = SurfaceAccessConfig(
            require_auth=True,
            allow_personas=["admin", "manager"],
        )
        user = {"id": "user-123"}
        with pytest.raises(SurfaceAccessDenied) as exc_info:
            check_surface_access(config, user=user, user_personas=["viewer"], is_api_request=False)
        assert exc_info.value.is_auth_required is False

    def test_access_none_defaults_to_allow(self) -> None:
        """Default config (access=None equivalent) allows all access."""
        config = SurfaceAccessConfig()  # defaults: require_auth=False
        check_surface_access(config, user=None, is_api_request=False)

    def test_deny_personas_takes_precedence(self) -> None:
        """Deny list takes precedence over allow list."""
        config = SurfaceAccessConfig(
            require_auth=True,
            allow_personas=["admin"],
            deny_personas=["admin"],
        )
        user = {"id": "user-123"}
        with pytest.raises(SurfaceAccessDenied):
            check_surface_access(config, user=user, user_personas=["admin"], is_api_request=False)

    def test_api_request_no_redirect(self) -> None:
        """API requests get no redirect URL on auth failure."""
        config = SurfaceAccessConfig(require_auth=True, redirect_unauthenticated="/login")
        with pytest.raises(SurfaceAccessDenied) as exc_info:
            check_surface_access(config, user=None, is_api_request=True)
        assert exc_info.value.is_auth_required is True
        assert exc_info.value.redirect_url is None


class TestSurfaceAccessConfigFromSpec:
    """Tests for SurfaceAccessConfig.from_spec() conversion."""

    def test_from_none_spec(self) -> None:
        """None spec produces default config."""
        config = SurfaceAccessConfig.from_spec(None)
        assert config.require_auth is False
        assert config.allow_personas is None
        assert config.deny_personas is None

    def test_from_public_spec(self) -> None:
        """Public spec produces non-auth config."""
        from dazzle.core.ir import SurfaceAccessSpec

        spec = SurfaceAccessSpec(require_auth=False)
        config = SurfaceAccessConfig.from_spec(spec)
        assert config.require_auth is False

    def test_from_authenticated_spec(self) -> None:
        """Authenticated spec produces auth-required config."""
        from dazzle.core.ir import SurfaceAccessSpec

        spec = SurfaceAccessSpec(require_auth=True)
        config = SurfaceAccessConfig.from_spec(spec)
        assert config.require_auth is True
        assert config.allow_personas is None

    def test_from_persona_spec(self) -> None:
        """Persona spec preserves allow list."""
        from dazzle.core.ir import SurfaceAccessSpec

        spec = SurfaceAccessSpec(require_auth=True, allow_personas=["admin", "manager"])
        config = SurfaceAccessConfig.from_spec(spec)
        assert config.require_auth is True
        assert config.allow_personas == ["admin", "manager"]
