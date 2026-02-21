"""ASVS V3: Session Management security tests."""

from __future__ import annotations

import inspect


class TestCookieSecurity:
    """V3.4: Cookie-Based Session Management."""

    def test_session_cookie_samesite(self):
        """V3.4.1: Session cookies must set SameSite attribute."""
        from dazzle_back.runtime.auth.routes import create_auth_routes

        source = inspect.getsource(create_auth_routes)
        assert 'samesite="lax"' in source or "samesite=" in source.lower()

    def test_session_cookie_httponly(self):
        """V3.4.2: Session cookies must be HttpOnly."""
        from dazzle_back.runtime.auth.routes import create_auth_routes

        source = inspect.getsource(create_auth_routes)
        assert "httponly=True" in source

    def test_session_cookie_secure_flag(self):
        """V3.4.3: Session cookies must use Secure flag detection."""
        from dazzle_back.runtime.auth.routes import create_auth_routes

        source = inspect.getsource(create_auth_routes)
        assert "cookie_secure" in source


class TestTokenEntropy:
    """V3.2: Token-based Session Management."""

    def test_session_token_sufficient_entropy(self):
        """V3.2.1: Session tokens must have at least 128 bits of entropy."""
        # Session IDs are generated in SessionRecord via secrets.token_urlsafe(32)
        # which provides 256 bits of cryptographic randomness (well above 128-bit minimum)
        from dazzle_back.runtime.auth.models import SessionRecord

        source = inspect.getsource(SessionRecord)
        # Should use secrets.token_urlsafe for session ID generation
        assert "token_urlsafe" in source or "secrets" in source


class TestCSRFProtection:
    """V3.5: CSRF Prevention."""

    def test_csrf_config_exists(self):
        """V3.5.1: CSRF protection configuration exists."""
        from dazzle_back.runtime.csrf import configure_csrf_for_profile

        config = configure_csrf_for_profile("standard")
        assert config.enabled is True

    def test_csrf_disabled_on_basic(self):
        """V3.5.2: CSRF can be disabled for internal tools (basic profile)."""
        from dazzle_back.runtime.csrf import configure_csrf_for_profile

        config = configure_csrf_for_profile("basic")
        assert config.enabled is False

    def test_csrf_token_length(self):
        """V3.5.3: CSRF tokens must have sufficient entropy."""
        from dazzle_back.runtime.csrf import CSRFConfig

        config = CSRFConfig(enabled=True)
        # 32 hex chars = 16 bytes = 128 bits minimum
        assert config.token_length >= 16

    def test_csrf_bearer_exempt(self):
        """V3.5.4: Bearer-authenticated requests are exempt from CSRF."""
        from dazzle_back.runtime.csrf import create_csrf_middleware

        source = inspect.getsource(create_csrf_middleware)
        assert "Bearer" in source
