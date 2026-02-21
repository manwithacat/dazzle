"""ASVS V13: API and Web Service security tests."""

from __future__ import annotations


class TestRateLimiting:
    """V13.2: RESTful Web Service."""

    def test_rate_limit_config_standard(self):
        """V13.2.1: Standard profile must have rate limits configured."""
        from dazzle_back.runtime.rate_limit import configure_rate_limits_for_profile

        config = configure_rate_limits_for_profile("standard")
        assert config.auth_limit is not None
        assert config.api_limit is not None
        assert config.upload_limit is not None

    def test_rate_limit_config_strict(self):
        """V13.2.2: Strict profile must have stricter rate limits."""
        from dazzle_back.runtime.rate_limit import configure_rate_limits_for_profile

        standard = configure_rate_limits_for_profile("standard")
        strict = configure_rate_limits_for_profile("strict")

        # Parse "N/minute" and verify strict <= standard
        def _parse_per_minute(limit_str):
            if not limit_str:
                return float("inf")
            parts = limit_str.split("/")
            return int(parts[0])

        assert _parse_per_minute(strict.auth_limit) <= _parse_per_minute(standard.auth_limit)
        assert _parse_per_minute(strict.api_limit) <= _parse_per_minute(standard.api_limit)

    def test_rate_limit_disabled_basic(self):
        """V13.2.3: Basic profile has no rate limits (development use)."""
        from dazzle_back.runtime.rate_limit import configure_rate_limits_for_profile

        config = configure_rate_limits_for_profile("basic")
        assert config.auth_limit is None
        assert config.api_limit is None


class TestCSRFProtection:
    """V13.3: CSRF Prevention."""

    def test_csrf_enabled_standard(self):
        """V13.3.1: CSRF protection must be enabled on standard profile."""
        from dazzle_back.runtime.csrf import configure_csrf_for_profile

        config = configure_csrf_for_profile("standard")
        assert config.enabled is True

    def test_csrf_enabled_strict(self):
        """V13.3.2: CSRF protection must be enabled on strict profile."""
        from dazzle_back.runtime.csrf import configure_csrf_for_profile

        config = configure_csrf_for_profile("strict")
        assert config.enabled is True


class TestSecurityHeaders:
    """V13.4: Security Headers."""

    def test_x_content_type_options_all_profiles(self):
        """V13.4.1: X-Content-Type-Options: nosniff on all profiles."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        for profile in ["basic", "standard", "strict"]:
            config = configure_headers_for_profile(profile)
            assert config.x_content_type_options is True
