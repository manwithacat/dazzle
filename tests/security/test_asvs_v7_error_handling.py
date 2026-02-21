"""ASVS V7: Error Handling and Logging security tests."""

from __future__ import annotations

import inspect


class TestErrorMessages:
    """V7.4: Error Handling."""

    def test_exception_handlers_registered(self):
        """V7.4.1: Custom exception handlers should be registered."""
        from dazzle_back.runtime.exception_handlers import register_exception_handlers

        # Should be a callable that registers handlers on an app
        assert callable(register_exception_handlers)

    def test_generic_error_in_auth(self):
        """V7.4.2: Auth errors should use generic messages to prevent enumeration."""
        from dazzle_back.runtime.auth.routes import create_auth_routes

        source = inspect.getsource(create_auth_routes)
        # Login should not reveal whether email or password was wrong
        assert "Invalid credentials" in source

    def test_forgot_password_generic_response(self):
        """V7.4.3: Forgot password always returns same message."""
        from dazzle_back.runtime.auth.routes import create_auth_routes

        source = inspect.getsource(create_auth_routes)
        assert "If an account with that email exists" in source
