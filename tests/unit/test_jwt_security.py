"""
Security tests for JWT authentication.

Tests for common JWT vulnerabilities:
- Algorithm confusion attacks (CVE-2022-29217)
- "None" algorithm attacks
- Weak secret key detection
- Token length limits (DoS prevention)
- Signature stripping
- Issuer/audience validation bypass
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def secure_config():
    """Create a secure JWT config with proper key length."""
    from dazzle_dnr_back.runtime.jwt_auth import JWTConfig

    # 32+ bytes for HMAC algorithms
    return JWTConfig(
        secret_key="this-is-a-secure-secret-key-for-testing-purposes-at-least-32-bytes"
    )


@pytest.fixture
def jwt_service(secure_config):
    """Create JWT service with secure config."""
    from dazzle_dnr_back.runtime.jwt_auth import JWTService

    return JWTService(secure_config)


# =============================================================================
# Algorithm Security Tests
# =============================================================================


class TestAlgorithmSecurity:
    """Test algorithm-related security measures."""

    def test_none_algorithm_blocked_on_config(self) -> None:
        """Should reject 'none' algorithm in configuration."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="none", secret_key="x" * 32)

        with pytest.raises(ValueError) as exc_info:
            JWTService(config)

        assert "blocked" in str(exc_info.value).lower()

    def test_none_algorithm_case_variations_blocked(self) -> None:
        """Should reject all case variations of 'none' algorithm."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        for variant in ["None", "NONE", "nOnE"]:
            config = JWTConfig(algorithm=variant, secret_key="x" * 32)
            with pytest.raises(ValueError) as exc_info:
                JWTService(config)
            assert "blocked" in str(exc_info.value).lower()

    def test_unknown_algorithm_rejected(self) -> None:
        """Should reject unknown algorithms."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="HS999", secret_key="x" * 32)

        with pytest.raises(ValueError) as exc_info:
            JWTService(config)

        assert "not allowed" in str(exc_info.value).lower()

    def test_algorithm_confusion_attack_blocked(self, jwt_service) -> None:
        """Should reject tokens with algorithm confusion attack (alg:none in header)."""
        pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTError

        # Create a token with "none" algorithm (attack token)
        payload = {
            "sub": str(uuid4()),
            "email": "attacker@example.com",
            "roles": ["admin"],  # Escalated privileges
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "attack-jti",
            "iss": "dazzle-app",
        }

        # Manually craft a token with "none" algorithm
        header = {"alg": "none", "typ": "JWT"}
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        attack_token = f"{header_b64}.{payload_b64}."

        with pytest.raises(JWTError) as exc_info:
            jwt_service.verify_access_token(attack_token)

        assert exc_info.value.code in ("blocked_algorithm", "invalid_algorithm", "invalid_token")

    def test_algorithm_substitution_attack_blocked(self, jwt_service) -> None:
        """Should reject tokens signed with different algorithm than expected."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTError

        # Create token with HS384 when service expects HS256
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-jti",
            "iss": "dazzle-app",
        }

        # Sign with different algorithm
        different_key = "different-secret-key-at-least-32-bytes-long"
        token = jwt_module.encode(payload, different_key, algorithm="HS384")

        # This should fail because signature verification fails (different key)
        # or because of algorithm mismatch
        with pytest.raises(JWTError):
            jwt_service.verify_access_token(token)


# =============================================================================
# Secret Key Security Tests
# =============================================================================


class TestSecretKeySecurity:
    """Test secret key security measures."""

    def test_short_secret_key_rejected(self) -> None:
        """Should reject secret keys shorter than 32 bytes."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="HS256", secret_key="short-key")

        with pytest.raises(ValueError) as exc_info:
            JWTService(config)

        assert "32" in str(exc_info.value) or "bytes" in str(exc_info.value).lower()

    def test_exactly_32_byte_key_accepted(self) -> None:
        """Should accept exactly 32-byte secret key."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="HS256", secret_key="x" * 32)

        service = JWTService(config)
        assert service is not None

    def test_longer_key_accepted(self) -> None:
        """Should accept keys longer than 32 bytes."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="HS256", secret_key="x" * 64)

        service = JWTService(config)
        assert service is not None

    def test_auto_generated_key_is_secure(self) -> None:
        """Auto-generated secret key should be at least 32 bytes."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig

        config = JWTConfig()

        # token_urlsafe(32) produces ~43 characters (base64-encoded 32 bytes)
        assert len(config.secret_key) >= 32


# =============================================================================
# Token Length Security Tests
# =============================================================================


class TestTokenLengthSecurity:
    """Test token length limits (DoS prevention)."""

    def test_oversized_token_rejected(self, jwt_service) -> None:
        """Should reject tokens exceeding maximum length."""
        from dazzle_dnr_back.runtime.jwt_auth import MAX_TOKEN_LENGTH, JWTError

        # Create an oversized token
        oversized_token = "a" * (MAX_TOKEN_LENGTH + 1)

        with pytest.raises(JWTError) as exc_info:
            jwt_service.verify_access_token(oversized_token)

        assert exc_info.value.code == "token_too_large"

    def test_oversized_token_rejected_unverified_decode(self, jwt_service) -> None:
        """Should reject oversized tokens even in unverified decode."""
        from dazzle_dnr_back.runtime.jwt_auth import MAX_TOKEN_LENGTH, JWTError

        oversized_token = "a" * (MAX_TOKEN_LENGTH + 1)

        with pytest.raises(JWTError) as exc_info:
            jwt_service.decode_token_unverified(oversized_token)

        assert exc_info.value.code == "token_too_large"

    def test_normal_token_passes_length_check(self, jwt_service) -> None:
        """Normal tokens should pass length check."""
        pytest.importorskip("jwt")

        user_id = uuid4()
        token, _ = jwt_service.create_access_token(
            user_id=user_id,
            email="test@example.com",
            roles=["user"],
        )

        # Should not raise
        claims = jwt_service.verify_access_token(token)
        assert claims.sub == str(user_id)


# =============================================================================
# Token Manipulation Tests
# =============================================================================


class TestTokenManipulation:
    """Test resistance to token manipulation attacks."""

    def test_tampered_payload_rejected(self, jwt_service) -> None:
        """Should reject tokens with tampered payload."""
        pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTError

        # Create valid token
        token, _ = jwt_service.create_access_token(
            user_id=uuid4(),
            email="user@example.com",
            roles=["user"],
        )

        # Tamper with the payload (change email)
        parts = token.split(".")
        # Decode payload, modify, re-encode
        payload_data = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        payload_data["email"] = "admin@example.com"
        payload_data["roles"] = ["admin"]
        tampered_payload = (
            base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=").decode()
        )

        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

        with pytest.raises(JWTError) as exc_info:
            jwt_service.verify_access_token(tampered_token)

        assert exc_info.value.code == "invalid_token"

    def test_missing_signature_rejected(self, jwt_service) -> None:
        """Should reject tokens with missing signature."""
        pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTError

        # Create valid token then strip signature
        token, _ = jwt_service.create_access_token(
            user_id=uuid4(),
            email="user@example.com",
            roles=["user"],
        )

        parts = token.split(".")
        stripped_token = f"{parts[0]}.{parts[1]}."

        with pytest.raises(JWTError):
            jwt_service.verify_access_token(stripped_token)

    def test_malformed_header_rejected(self, jwt_service) -> None:
        """Should reject tokens with malformed headers."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTError

        # Various malformed tokens
        malformed_tokens = [
            "not-a-jwt",
            "only.two",
            "...",
            "",
            "aaa.bbb.ccc",  # Invalid base64
            base64.urlsafe_b64encode(b"not json").decode() + ".payload.signature",
        ]

        for token in malformed_tokens:
            with pytest.raises(JWTError) as exc_info:
                jwt_service.verify_access_token(token)
            assert exc_info.value.code in ("invalid_token", "token_too_large")


# =============================================================================
# Issuer/Audience Validation Tests
# =============================================================================


class TestIssuerAudienceValidation:
    """Test issuer and audience validation."""

    def test_wrong_issuer_rejected(self) -> None:
        """Should reject tokens with wrong issuer."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        secret = "x" * 32
        config = JWTConfig(secret_key=secret, issuer="my-app")
        service = JWTService(config)

        # Create token with different issuer
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-jti",
            "iss": "attacker-app",  # Wrong issuer
        }
        token = jwt_module.encode(payload, secret, algorithm="HS256")

        with pytest.raises(JWTError) as exc_info:
            service.verify_access_token(token)

        assert exc_info.value.code == "invalid_token"

    def test_wrong_audience_rejected(self) -> None:
        """Should reject tokens with wrong audience."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        secret = "x" * 32
        config = JWTConfig(secret_key=secret, audience="my-audience")
        service = JWTService(config)

        # Create token with wrong audience
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-jti",
            "iss": "dazzle-app",
            "aud": "wrong-audience",  # Wrong audience
        }
        token = jwt_module.encode(payload, secret, algorithm="HS256")

        with pytest.raises(JWTError) as exc_info:
            service.verify_access_token(token)

        assert exc_info.value.code == "invalid_token"


# =============================================================================
# Required Claims Tests
# =============================================================================


class TestRequiredClaims:
    """Test that required claims are enforced."""

    def test_missing_sub_rejected(self) -> None:
        """Should reject tokens missing 'sub' claim."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        secret = "x" * 32
        config = JWTConfig(secret_key=secret)
        service = JWTService(config)

        payload = {
            # Missing "sub"
            "email": "test@example.com",
            "roles": [],
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": "test-jti",
            "iss": "dazzle-app",
        }
        token = jwt_module.encode(payload, secret, algorithm="HS256")

        with pytest.raises(JWTError) as exc_info:
            service.verify_access_token(token)

        assert exc_info.value.code == "invalid_token"

    def test_missing_jti_rejected(self) -> None:
        """Should reject tokens missing 'jti' claim (needed for revocation)."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        secret = "x" * 32
        config = JWTConfig(secret_key=secret)
        service = JWTService(config)

        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            # Missing "jti"
            "iss": "dazzle-app",
        }
        token = jwt_module.encode(payload, secret, algorithm="HS256")

        with pytest.raises(JWTError) as exc_info:
            service.verify_access_token(token)

        assert exc_info.value.code == "invalid_token"


# =============================================================================
# Timing Attack Tests
# =============================================================================


class TestTimingAttacks:
    """Test resistance to timing attacks."""

    def test_expired_token_detected(self) -> None:
        """Should reject expired tokens."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        secret = "x" * 32
        config = JWTConfig(secret_key=secret)
        service = JWTService(config)

        # Create token that expired 1 hour ago
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
            "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
            "jti": "test-jti",
            "iss": "dazzle-app",
        }
        token = jwt_module.encode(payload, secret, algorithm="HS256")

        with pytest.raises(JWTError) as exc_info:
            service.verify_access_token(token)

        assert exc_info.value.code == "token_expired"

    def test_future_iat_with_leeway(self) -> None:
        """Should allow tokens with iat slightly in future (clock skew)."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        secret = "x" * 32
        config = JWTConfig(secret_key=secret, leeway_seconds=60)
        service = JWTService(config)

        # Create token with iat 30 seconds in future (within 60s leeway)
        now = datetime.now(UTC)
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int((now + timedelta(seconds=30)).timestamp()),  # 30s in future
            "jti": "test-jti",
            "iss": "dazzle-app",
        }
        token = jwt_module.encode(payload, secret, algorithm="HS256")

        # Should succeed with leeway
        claims = service.verify_access_token(token)
        assert claims is not None


# =============================================================================
# RS256 Configuration Tests
# =============================================================================


class TestAsymmetricAlgorithms:
    """Test asymmetric algorithm configuration."""

    def test_rs256_requires_private_key(self) -> None:
        """RS256 should require private key."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="RS256", public_key="fake-public-key")

        with pytest.raises(ValueError) as exc_info:
            JWTService(config)

        assert "private_key" in str(exc_info.value).lower()

    def test_rs256_requires_public_key(self) -> None:
        """RS256 should require public key."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="RS256", private_key="fake-private-key")

        with pytest.raises(ValueError) as exc_info:
            JWTService(config)

        assert (
            "public_key" in str(exc_info.value).lower()
            or "private_key" in str(exc_info.value).lower()
        )

    def test_es256_requires_keys(self) -> None:
        """ES256 (ECDSA) should require both keys."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(algorithm="ES256")

        with pytest.raises(ValueError):
            JWTService(config)
