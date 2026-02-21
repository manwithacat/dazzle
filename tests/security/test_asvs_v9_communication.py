"""ASVS V9: Communication security tests."""

from __future__ import annotations


class TestTransportSecurity:
    """V9.1: Client Communication Security."""

    def test_hsts_enabled_standard(self):
        """V9.1.1: HSTS must be enabled on standard profile."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("standard")
        assert config.enable_hsts is True

    def test_hsts_max_age_minimum(self):
        """V9.1.2: HSTS max-age must be at least 1 year (31536000 seconds)."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("standard")
        assert config.hsts_max_age >= 31536000

    def test_hsts_disabled_basic(self):
        """V9.1.3: HSTS can be disabled for internal tools (basic profile)."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("basic")
        assert config.enable_hsts is False


class TestCORSSecurity:
    """V9.2: Server Communication Security."""

    def test_no_wildcard_cors_strict(self):
        """V9.2.1: Strict profile must not use wildcard CORS origins."""
        from dazzle_back.runtime.security_middleware import configure_cors_for_profile

        config = configure_cors_for_profile("strict")
        assert config.allow_origins != ["*"]

    def test_basic_profile_wildcard_allowed(self):
        """V9.2.2: Basic profile allows wildcard CORS for development."""
        from dazzle_back.runtime.security_middleware import configure_cors_for_profile

        config = configure_cors_for_profile("basic")
        assert config.allow_origins == ["*"]


class TestSecurityHeaders:
    """V9.3: HTTP Security Headers."""

    def test_x_frame_options_set(self):
        """V9.3.1: X-Frame-Options must be set."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        for profile in ["standard", "strict"]:
            config = configure_headers_for_profile(profile)
            assert config.x_frame_options in ("DENY", "SAMEORIGIN")

    def test_x_content_type_options(self):
        """V9.3.2: X-Content-Type-Options: nosniff must be enabled."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        for profile in ["basic", "standard", "strict"]:
            config = configure_headers_for_profile(profile)
            assert config.x_content_type_options is True

    def test_csp_enabled_strict(self):
        """V9.3.3: Content Security Policy must be enabled on strict profile."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("strict")
        assert config.enable_csp is True
