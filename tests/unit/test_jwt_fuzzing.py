"""
Property-based fuzzing tests for JWT authentication.

Uses Hypothesis to generate random inputs and test crash resistance.
"""

from __future__ import annotations

import base64
import json
import string
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# =============================================================================
# Strategy Definitions
# =============================================================================


# Random JWT-like strings with 3 parts
jwt_like_string = st.from_regex(
    r"[A-Za-z0-9_-]{5,100}\.[A-Za-z0-9_-]{5,100}\.[A-Za-z0-9_-]{0,100}", fullmatch=True
)

# Random algorithm names (valid and invalid)
algorithm_names = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=10)

# Random secret keys
secret_keys = st.text(min_size=0, max_size=128)

# Random email-like strings
email_like = st.from_regex(r"[a-z0-9]+@[a-z0-9]+\.[a-z]{2,4}", fullmatch=True)

# Random role lists
role_lists = st.lists(
    st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=20), max_size=10
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def secure_jwt_service():
    """Create a secure JWT service for testing."""
    from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

    config = JWTConfig(secret_key="this-is-a-secure-secret-key-for-fuzzing-at-least-32-bytes")
    return JWTService(config)


# =============================================================================
# Token Verification Crash Resistance
# =============================================================================


class TestTokenVerificationFuzzing:
    """Fuzz test token verification for crash resistance."""

    @given(token=st.text(min_size=0, max_size=20000))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_verify_arbitrary_text_no_crash(self, token: str) -> None:
        """Token verification should never crash on arbitrary input."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        config = JWTConfig(secret_key="x" * 32)
        service = JWTService(config)

        try:
            service.verify_access_token(token)
        except JWTError:
            pass  # Expected - invalid tokens should raise JWTError
        except RuntimeError as e:
            if "PyJWT" in str(e):
                pytest.skip("PyJWT not installed")
            raise

    @given(token=jwt_like_string)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_verify_jwt_like_strings_no_crash(self, token: str) -> None:
        """Token verification should not crash on JWT-like strings."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        config = JWTConfig(secret_key="x" * 32)
        service = JWTService(config)

        try:
            service.verify_access_token(token)
        except JWTError:
            pass  # Expected
        except RuntimeError as e:
            if "PyJWT" in str(e):
                pytest.skip("PyJWT not installed")
            raise

    @given(token=st.binary(min_size=0, max_size=1000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_verify_binary_data_no_crash(self, token: bytes) -> None:
        """Token verification should not crash on binary data."""
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        config = JWTConfig(secret_key="x" * 32)
        service = JWTService(config)

        try:
            # Try to decode as string (may fail)
            token_str = token.decode("utf-8", errors="replace")
            service.verify_access_token(token_str)
        except JWTError:
            pass  # Expected
        except RuntimeError as e:
            if "PyJWT" in str(e):
                pytest.skip("PyJWT not installed")
            raise


# =============================================================================
# Token Creation Fuzzing
# =============================================================================


class TestTokenCreationFuzzing:
    """Fuzz test token creation with random inputs."""

    @given(
        email=email_like,
        roles=role_lists,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_create_token_with_random_email_roles(
        self,
        email: str,
        roles: list[str],
    ) -> None:
        """Token creation should handle various email and role combinations."""
        pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(secret_key="x" * 32)
        service = JWTService(config)

        user_id = uuid4()
        token, claims = service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
        )

        assert token
        assert claims.email == email
        assert claims.roles == roles

        # Verify the token we just created
        verified = service.verify_access_token(token)
        assert verified.email == email

    @given(tenant_id=st.one_of(st.none(), st.text(min_size=1, max_size=50)))
    @settings(max_examples=50)
    def test_create_token_with_tenant_id(self, tenant_id: str | None) -> None:
        """Token creation should handle various tenant IDs."""
        pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(secret_key="x" * 32)
        service = JWTService(config)

        token, claims = service.create_access_token(
            user_id=uuid4(),
            email="test@example.com",
            roles=["user"],
            tenant_id=tenant_id,
        )

        assert claims.tenant_id == tenant_id


# =============================================================================
# Configuration Fuzzing
# =============================================================================


class TestConfigurationFuzzing:
    """Fuzz test configuration handling."""

    @given(algorithm=algorithm_names)
    @settings(max_examples=100)
    def test_random_algorithm_handled_safely(self, algorithm: str) -> None:
        """Random algorithm names should either work or raise ValueError."""
        from dazzle_dnr_back.runtime.jwt_auth import ALLOWED_ALGORITHMS, JWTConfig, JWTService

        config = JWTConfig(
            algorithm=algorithm,
            secret_key="x" * 32,
            private_key="fake-key" if algorithm.startswith(("RS", "ES")) else None,
            public_key="fake-key" if algorithm.startswith(("RS", "ES")) else None,
        )

        if algorithm in ALLOWED_ALGORITHMS:
            # Should succeed (if keys are valid for RS/ES algorithms)
            try:
                service = JWTService(config)
                assert service is not None
            except ValueError:
                # May fail due to invalid keys for RS/ES
                pass
        else:
            # Should raise ValueError for unknown/blocked algorithms
            with pytest.raises(ValueError):
                JWTService(config)

    @given(secret=secret_keys)
    @settings(max_examples=100)
    def test_random_secret_key_length_validation(self, secret: str) -> None:
        """Secret key length should be validated."""
        from dazzle_dnr_back.runtime.jwt_auth import MIN_HMAC_SECRET_LENGTH, JWTConfig, JWTService

        config = JWTConfig(algorithm="HS256", secret_key=secret)

        if len(secret) >= MIN_HMAC_SECRET_LENGTH:
            service = JWTService(config)
            assert service is not None
        else:
            with pytest.raises(ValueError):
                JWTService(config)


# =============================================================================
# Payload Fuzzing
# =============================================================================


class TestPayloadFuzzing:
    """Fuzz test with crafted payloads."""

    @given(
        sub=st.text(min_size=0, max_size=100),
        email=st.text(min_size=0, max_size=100),
        exp_offset=st.integers(min_value=-86400 * 365, max_value=86400 * 365),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_crafted_payload_handling(
        self,
        sub: str,
        email: str,
        exp_offset: int,
    ) -> None:
        """Verification should handle crafted payloads without crashing."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        secret = "x" * 32
        config = JWTConfig(secret_key=secret)
        service = JWTService(config)

        now = datetime.now(UTC)
        payload = {
            "sub": sub,
            "email": email,
            "roles": [],
            "exp": int((now + timedelta(seconds=exp_offset)).timestamp()),
            "iat": int(now.timestamp()),
            "jti": str(uuid4()),
            "iss": "dazzle-app",
        }

        token = jwt_module.encode(payload, secret, algorithm="HS256")

        try:
            claims = service.verify_access_token(token)
            # If it passes, claims should match
            assert claims.sub == sub
            assert claims.email == email
        except JWTError:
            # Expected for invalid/expired tokens
            pass


# =============================================================================
# Header Manipulation Fuzzing
# =============================================================================


class TestHeaderFuzzing:
    """Fuzz test header manipulation resistance."""

    @given(alg=st.text(min_size=0, max_size=20))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_forged_header_algorithm(self, alg: str) -> None:
        """Forged algorithm headers should be rejected."""
        pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import (
            JWTConfig,
            JWTError,
            JWTService,
        )

        secret = "x" * 32
        config = JWTConfig(secret_key=secret)
        service = JWTService(config)

        # Create a payload
        now = datetime.now(UTC)
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "jti": "test-jti",
            "iss": "dazzle-app",
        }

        # Manually craft token with arbitrary algorithm header
        header = {"alg": alg, "typ": "JWT"}
        try:
            header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
            payload_b64 = (
                base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
            )
            crafted_token = f"{header_b64}.{payload_b64}.fakesignature"
        except Exception:
            # Skip if we can't even create the token
            return

        try:
            service.verify_access_token(crafted_token)
            # Should only succeed if alg matches expected and signature is valid
            # In practice, this will fail because signature is fake
            pytest.fail("Should have rejected token with forged header")
        except JWTError:
            pass  # Expected

    @given(
        extra_header=st.dictionaries(
            keys=st.text(alphabet=string.ascii_letters, min_size=1, max_size=10),
            values=st.text(min_size=0, max_size=100),
            max_size=5,
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_extra_header_fields(self, extra_header: dict) -> None:
        """Extra header fields should not bypass security."""
        pytest.importorskip("jwt")
        from dazzle_dnr_back.runtime.jwt_auth import JWTConfig, JWTError, JWTService

        secret = "x" * 32
        config = JWTConfig(secret_key=secret)
        service = JWTService(config)

        now = datetime.now(UTC)
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "jti": "test-jti",
            "iss": "dazzle-app",
        }

        # Create token with extra header fields
        header = {"alg": "HS256", "typ": "JWT", **extra_header}
        try:
            header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
            payload_b64 = (
                base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
            )
            crafted_token = f"{header_b64}.{payload_b64}.fakesig"
        except Exception:
            return

        try:
            service.verify_access_token(crafted_token)
            pytest.fail("Should have rejected token with invalid signature")
        except JWTError:
            pass


# =============================================================================
# Token Store Fuzzing
# =============================================================================


class TestTokenStoreFuzzing:
    """Fuzz test token store operations."""

    @given(token=st.text(min_size=0, max_size=1000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_validate_random_token_no_crash(self, token: str, tmp_path) -> None:
        """Token store should handle random validation queries."""
        # Use unique path per test to avoid collisions
        import tempfile

        from dazzle_dnr_back.runtime.token_store import TokenStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = TokenStore(db_path=f"{tmpdir}/tokens.db")
            result = store.validate_token(token)
            # Should return None for invalid tokens
            assert result is None

    @given(
        ip=st.one_of(st.none(), st.text(min_size=0, max_size=50)),
        ua=st.one_of(st.none(), st.text(min_size=0, max_size=200)),
        device=st.one_of(st.none(), st.text(min_size=0, max_size=50)),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_create_token_with_random_metadata(
        self,
        ip: str | None,
        ua: str | None,
        device: str | None,
        tmp_path,
    ) -> None:
        """Token creation should handle various metadata combinations."""
        import tempfile

        from dazzle_dnr_back.runtime.auth import UserRecord
        from dazzle_dnr_back.runtime.token_store import TokenStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = TokenStore(db_path=f"{tmpdir}/tokens.db")
            user = UserRecord(
                id=uuid4(),
                email="test@example.com",
                password_hash="hash",
                roles=["user"],
            )

            token = store.create_token(
                user,
                ip_address=ip,
                user_agent=ua,
                device_id=device,
            )

            assert token
            record = store.validate_token(token)
            assert record is not None
            assert record.user_id == user.id
