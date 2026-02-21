"""ASVS V6: Stored Cryptography security tests."""

from __future__ import annotations

import inspect

import pytest


class TestCryptographicAlgorithms:
    """V6.2: Algorithms."""

    def test_pbkdf2_sha256_used(self):
        """V6.2.1: PBKDF2 must use SHA-256 or stronger."""
        from dazzle_back.runtime.auth.crypto import hash_password

        source = inspect.getsource(hash_password)
        assert '"sha256"' in source or "'sha256'" in source

    def test_jwt_uses_approved_algorithm(self):
        """V6.2.2: JWT must use approved cryptographic algorithms."""
        from dazzle_back.runtime.jwt_auth import ALLOWED_ALGORITHMS

        approved = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
        for algo in ALLOWED_ALGORITHMS:
            assert algo in approved, f"Unapproved algorithm: {algo}"


class TestKeyManagement:
    """V6.4: Secret Management."""

    def test_minimum_hmac_key_length(self):
        """V6.4.1: HMAC secret keys must be at least 32 bytes."""
        from dazzle_back.runtime.jwt_auth import JWTConfig, JWTService

        # Short key should be rejected
        config = JWTConfig(secret_key="too-short")
        with pytest.raises(ValueError):
            JWTService(config)

    def test_salt_generation_uses_secrets(self):
        """V6.4.2: Salt generation must use cryptographically secure randomness."""
        from dazzle_back.runtime.auth.crypto import hash_password

        source = inspect.getsource(hash_password)
        assert "secrets.token_hex" in source or "secrets" in source


class TestTimingSafety:
    """V6.3: Random Values."""

    def test_password_verify_timing_safe(self):
        """V6.3.1: Password comparison must be timing-safe."""
        from dazzle_back.runtime.auth.crypto import verify_password

        source = inspect.getsource(verify_password)
        assert "hmac.compare_digest" in source
