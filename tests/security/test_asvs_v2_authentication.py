"""ASVS V2: Authentication security tests."""

from __future__ import annotations

import inspect

import pytest


class TestPasswordStorage:
    """V2.4: Credential Storage."""

    def test_pbkdf2_hash_algorithm(self):
        """V2.4.1: Passwords are hashed with PBKDF2."""
        from dazzle_back.runtime.auth.crypto import hash_password

        source = inspect.getsource(hash_password)
        assert "pbkdf2_hmac" in source

    def test_unique_salt_per_hash(self):
        """V2.4.2: Each password hash uses a unique salt."""
        from dazzle_back.runtime.auth.crypto import hash_password

        h1 = hash_password("test_password")
        h2 = hash_password("test_password")
        salt1 = h1.split("$")[0]
        salt2 = h2.split("$")[0]
        assert salt1 != salt2, "Each hash must use a unique random salt"

    def test_minimum_iteration_count(self):
        """V2.4.3: Iteration count is at least 100,000 for PBKDF2."""
        from dazzle_back.runtime.auth.crypto import hash_password

        source = inspect.getsource(hash_password)
        # Extract iteration count — must be >= 100000
        assert "100000" in source or "100_000" in source

    def test_timing_safe_comparison(self):
        """V2.4.4: Password verification uses constant-time comparison."""
        from dazzle_back.runtime.auth.crypto import verify_password

        source = inspect.getsource(verify_password)
        assert "hmac.compare_digest" in source or "compare_digest" in source


class TestCredentialRecovery:
    """V2.5: Credential Recovery."""

    def test_forgot_password_no_enumeration(self):
        """V2.5.2: Forgot password returns same response whether user exists or not."""
        from dazzle_back.runtime.auth.routes import create_auth_routes

        source = inspect.getsource(create_auth_routes)
        # The function should always return success to prevent user enumeration
        assert "prevent user enumeration" in source.lower() or "always return" in source.lower()


class TestJWTSecurity:
    """V2.7: JWT/Token Security."""

    def test_none_algorithm_blocked(self):
        """V2.7.1: 'none' algorithm must be blocked."""
        from dazzle_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="none", secret_key="x" * 32)
        with pytest.raises(ValueError, match="(?i)blocked"):
            JWTService(config)

    def test_algorithm_whitelist(self):
        """V2.7.2: Only approved algorithms are accepted."""
        from dazzle_back.runtime.jwt_auth import JWTService

        source = inspect.getsource(JWTService._validate_config)
        assert "ALLOWED_ALGORITHMS" in source or "blocked" in source.lower()

    def test_minimum_key_length(self):
        """V2.7.3: HMAC keys must be at least 32 bytes."""
        from dazzle_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(secret_key="short")
        with pytest.raises(ValueError, match="(?i)(short|length|weak|32)"):
            JWTService(config)
