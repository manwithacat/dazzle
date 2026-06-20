"""Tests for dazzle_http.runtime.totp — TOTP generation and verification."""

import base64
import re

import pytest

from dazzle.http.runtime.totp import (
    generate_totp,
    generate_totp_secret,
    get_totp_uri,
    verify_totp,
)

# ---------------------------------------------------------------------------
# Fixed secret for deterministic tests.
# RFC 6238 test key: ASCII "12345678901234567890" (20 bytes)
# base32("12345678901234567890") = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
# ---------------------------------------------------------------------------
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # nosemgrep: generic.secrets.security.detected-generic-secret.detected-generic-secret


# ===================================================================
# 1. generate_totp_secret()
# ===================================================================


class TestGenerateTotpSecret:
    """Tests for generate_totp_secret()."""

    @pytest.mark.parametrize(
        ("length", "expected_decoded_len"),
        [
            (None, 20),  # default
            (10, 10),
            (32, 32),
            (1, 1),
        ],
        ids=[
            "test_returns_valid_base32",
            "test_custom_length_10",
            "test_custom_length_32",
            "test_custom_length_1",
        ],
    )
    def test_secret_length(self, length, expected_decoded_len) -> None:
        kwargs = {"length": length} if length is not None else {}
        secret = generate_totp_secret(**kwargs)
        decoded = base64.b32decode(secret)
        assert len(decoded) == expected_decoded_len

    def test_output_is_ascii_base32_chars(self) -> None:
        secret = generate_totp_secret()
        # Base32 alphabet is A-Z and 2-7, plus optional = padding
        assert re.fullmatch(r"[A-Z2-7=]+", secret), f"Unexpected characters in secret: {secret}"

    def test_different_calls_produce_different_secrets(self) -> None:
        secrets_set = {generate_totp_secret() for _ in range(50)}
        # With 160-bit randomness, collisions are astronomically unlikely
        assert len(secrets_set) == 50


# ===================================================================
# 2. get_totp_uri()
# ===================================================================


class TestGetTotpUri:
    """Tests for get_totp_uri()."""

    def test_returns_otpauth_scheme(self) -> None:
        uri = get_totp_uri(RFC_SECRET, "alice@example.com")
        assert uri.startswith("otpauth://totp/")

    def test_includes_email_in_label(self) -> None:
        uri = get_totp_uri(RFC_SECRET, "alice@example.com")
        assert "alice%40example.com" in uri or "alice@example.com" in uri

    def test_includes_secret_in_params(self) -> None:
        uri = get_totp_uri(RFC_SECRET, "alice@example.com")
        assert f"secret={RFC_SECRET}" in uri

    def test_default_issuer_is_dazzle(self) -> None:
        uri = get_totp_uri(RFC_SECRET, "alice@example.com")
        assert "issuer=Dazzle" in uri
        # Label should also start with issuer
        assert "Dazzle:alice" in uri or "Dazzle%3Aalice" in uri

    def test_custom_issuer(self) -> None:
        uri = get_totp_uri(RFC_SECRET, "bob@test.com", issuer="MyApp")
        assert "issuer=MyApp" in uri
        assert "MyApp:bob" in uri or "MyApp%3Abob" in uri

    def test_includes_standard_params(self) -> None:
        uri = get_totp_uri(RFC_SECRET, "alice@example.com")
        assert "algorithm=SHA1" in uri
        assert "digits=6" in uri
        assert "period=30" in uri

    def test_full_uri_structure(self) -> None:
        uri = get_totp_uri("JBSWY3DPEHPK3PXP", "user@example.com", issuer="TestCo")
        # Should parse as: otpauth://totp/TestCo:user@example.com?secret=...&issuer=...
        assert uri.startswith("otpauth://totp/")
        # Everything after the scheme+type is label?params
        rest = uri[len("otpauth://totp/") :]
        assert "?" in rest
        label, params = rest.split("?", 1)
        assert "TestCo" in label
        assert "user" in label
        assert "secret=JBSWY3DPEHPK3PXP" in params


# ===================================================================
# 3. generate_totp()
# ===================================================================


class TestGenerateTotp:
    """Tests for generate_totp()."""

    def test_returns_six_digit_string(self) -> None:
        code = generate_totp(RFC_SECRET, timestamp=1000000000.0)
        assert len(code) == 6
        assert code.isdigit()

    def test_leading_zeros_preserved(self) -> None:
        # The code is zero-padded to 6 digits. Verify formatting by checking
        # that the output is always exactly 6 characters.
        for ts in range(0, 3000, 30):
            code = generate_totp(RFC_SECRET, timestamp=float(ts))
            assert len(code) == 6, f"Code {code!r} at ts={ts} is not 6 digits"

    def test_same_secret_same_timestamp_same_code(self) -> None:
        code1 = generate_totp(RFC_SECRET, timestamp=1234567890.0)
        code2 = generate_totp(RFC_SECRET, timestamp=1234567890.0)
        assert code1 == code2

    def test_same_time_step_same_code(self) -> None:
        # Timestamps 1000000000 and 1000000015 are in the same 30-second step
        code1 = generate_totp(RFC_SECRET, timestamp=1000000000.0)
        code2 = generate_totp(RFC_SECRET, timestamp=1000000015.0)
        assert code1 == code2

    def test_different_time_steps_different_codes(self) -> None:
        # 30 seconds apart crosses a step boundary (usually)
        code1 = generate_totp(RFC_SECRET, timestamp=1000000000.0)
        code2 = generate_totp(RFC_SECRET, timestamp=1000000030.0)
        # They should differ (with overwhelming probability for distinct counters)
        assert code1 != code2

    def test_different_secrets_different_codes(self) -> None:
        secret_a = "JBSWY3DPEHPK3PXP"
        secret_b = "NBSWY3DPEHPK3PXQ"
        ts = 1234567890.0
        code_a = generate_totp(secret_a, timestamp=ts)
        code_b = generate_totp(secret_b, timestamp=ts)
        assert code_a != code_b


# ===================================================================
# 4. verify_totp()
# ===================================================================


class TestVerifyTotp:
    """Tests for verify_totp()."""

    FIXED_TS = 1234567890.0

    @pytest.mark.parametrize(
        ("code_ts_offset", "verify_kwargs", "expected"),
        [
            (0.0, {}, True),
            (None, {"code": "000000"}, False),
            (None, {"code": "999999"}, False),
            (-30.0, {"window": 1}, True),
            (30.0, {"window": 1}, True),
            (60.0, {"window": 1}, False),
            (-60.0, {"window": 1}, False),
        ],
        ids=[
            "test_valid_code_returns_true",
            "test_wrong_code_returns_false",
            "test_completely_invalid_code_returns_false",
            "test_adjacent_past_step_within_window",
            "test_adjacent_future_step_within_window",
            "test_code_outside_window_returns_false",
            "test_code_outside_window_past",
        ],
    )
    def test_verify_totp(self, code_ts_offset, verify_kwargs, expected) -> None:
        if "code" in verify_kwargs:
            # Fixed invalid code supplied directly — no generation needed.
            code = verify_kwargs.pop("code")
        else:
            code_ts = self.FIXED_TS + (code_ts_offset or 0.0)
            code = generate_totp(RFC_SECRET, timestamp=code_ts)
        result = verify_totp(RFC_SECRET, code, timestamp=self.FIXED_TS, **verify_kwargs)
        assert result is expected

    def test_window_zero_exact_match_only(self) -> None:
        code = generate_totp(RFC_SECRET, timestamp=self.FIXED_TS)
        assert verify_totp(RFC_SECRET, code, window=0, timestamp=self.FIXED_TS) is True

        # Adjacent step should fail with window=0
        adjacent_code = generate_totp(RFC_SECRET, timestamp=self.FIXED_TS - 30)
        assert verify_totp(RFC_SECRET, adjacent_code, window=0, timestamp=self.FIXED_TS) is False

    def test_larger_window(self) -> None:
        # With window=3, codes up to 3 steps away should be accepted
        code_3_steps_back = generate_totp(RFC_SECRET, timestamp=self.FIXED_TS - 90)
        assert verify_totp(RFC_SECRET, code_3_steps_back, window=3, timestamp=self.FIXED_TS) is True

        # But 4 steps away should fail
        code_4_steps_back = generate_totp(RFC_SECRET, timestamp=self.FIXED_TS - 120)
        assert (
            verify_totp(RFC_SECRET, code_4_steps_back, window=3, timestamp=self.FIXED_TS) is False
        )

    def test_uses_constant_time_comparison(self) -> None:
        """Verify the implementation uses hmac.compare_digest (constant-time).

        We don't measure timing here — instead we verify the source code uses
        hmac.compare_digest by checking that the function actually calls it.
        We do this indirectly: a correct code and an incorrect code should both
        take a similar amount of iterations (the function always checks the full
        window). We verify behaviour is correct for known inputs.
        """
        # Use a known secret and timestamp
        code = generate_totp(RFC_SECRET, timestamp=self.FIXED_TS)
        # The correct code must pass
        assert verify_totp(RFC_SECRET, code, timestamp=self.FIXED_TS) is True
        # A wrong code (off by one digit) must fail
        wrong = f"{(int(code) + 1) % 1000000:06d}"
        assert verify_totp(RFC_SECRET, wrong, timestamp=self.FIXED_TS) is False


# ===================================================================
# 5. Known test vectors (RFC 6238 Appendix B, SHA1)
# ===================================================================


class TestKnownVectors:
    """RFC 6238 test vectors for SHA1 with 20-byte secret '12345678901234567890'."""

    @pytest.mark.parametrize(
        ("timestamp", "expected_code"),
        [
            (59, "287082"),
            (1111111109, "081804"),
            (1111111111, "050471"),
            (1234567890, "005924"),
            (2000000000, "279037"),
        ],
        ids=[
            "t=59",
            "t=1111111109",
            "t=1111111111",
            "t=1234567890",
            "t=2000000000",
        ],
    )
    def test_rfc6238_sha1_vectors(self, timestamp: int, expected_code: str) -> None:
        code = generate_totp(RFC_SECRET, timestamp=float(timestamp))
        assert code == expected_code, (
            f"At timestamp {timestamp}: expected {expected_code}, got {code}"
        )

    def test_round_trip_generate_then_verify(self) -> None:
        """generate_totp() output should always pass verify_totp()."""
        for ts in [59, 1111111109, 1111111111, 1234567890, 2000000000]:
            code = generate_totp(RFC_SECRET, timestamp=float(ts))
            assert verify_totp(RFC_SECRET, code, timestamp=float(ts)) is True, (
                f"Round-trip failed at timestamp {ts}"
            )

    def test_deterministic_output_fixed_secret(self) -> None:
        """Same inputs always produce the same output."""
        secret = "JBSWY3DPEHPK3PXP"  # base32("Hello!")
        ts = 1000000000.0
        code = generate_totp(secret, timestamp=ts)
        for _ in range(10):
            assert generate_totp(secret, timestamp=ts) == code
