"""
Unit tests for DAZZLE security features (v0.11.0).

Tests:
- SecurityConfig and SecurityProfile
- Security middleware configuration
- Surface access control
- Tenant isolation
- SECURITY.md generation
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# =============================================================================
# SecurityConfig Tests
# =============================================================================


class TestSecurityConfig:
    """Tests for security configuration types."""

    def test_security_profile_values(self) -> None:
        """Test that security profiles have correct values."""
        from dazzle.core.ir.security import SecurityProfile

        assert SecurityProfile.BASIC.value == "basic"
        assert SecurityProfile.STANDARD.value == "standard"
        assert SecurityProfile.STRICT.value == "strict"

    def test_basic_profile_defaults(self) -> None:
        """Test basic profile has permissive defaults."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile

        config = SecurityConfig.from_profile(SecurityProfile.BASIC)

        assert config.profile == SecurityProfile.BASIC
        assert config.cors_origins == ["*"]
        assert config.enable_hsts is False
        assert config.enable_csp is False
        assert config.require_auth_by_default is False
        assert config.tenant_isolation is False

    def test_standard_profile_defaults(self) -> None:
        """Test standard profile has reasonable security."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile

        config = SecurityConfig.from_profile(SecurityProfile.STANDARD)

        assert config.profile == SecurityProfile.STANDARD
        assert config.cors_origins is None  # Same-origin only
        assert config.enable_hsts is True
        # Post-#833: standard profile enables CSP — runtime middleware
        # switches to Report-Only mode so violations surface without blocking.
        assert config.enable_csp is True
        assert config.require_auth_by_default is True
        assert config.tenant_isolation is False

    def test_strict_profile_defaults(self) -> None:
        """Test strict profile has maximum security."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile

        config = SecurityConfig.from_profile(SecurityProfile.STRICT)

        assert config.profile == SecurityProfile.STRICT
        assert config.enable_hsts is True
        assert config.enable_csp is True
        assert config.require_auth_by_default is True

    def test_strict_profile_with_multi_tenant(self) -> None:
        """Test strict profile enables tenant isolation when multi_tenant=True."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile

        config = SecurityConfig.from_profile(SecurityProfile.STRICT, multi_tenant=True)

        assert config.tenant_isolation is True

    def test_custom_cors_origins(self) -> None:
        """Test custom CORS origins override profile defaults."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile

        custom_origins = ["https://app.example.com", "https://admin.example.com"]
        config = SecurityConfig.from_profile(
            SecurityProfile.STANDARD,
            cors_origins=custom_origins,
        )

        assert config.cors_origins == custom_origins


# =============================================================================
# Security Middleware Tests
# =============================================================================


class TestSecurityMiddleware:
    """Tests for security middleware configuration."""

    def test_basic_cors_config(self) -> None:
        """Test basic profile CORS configuration."""
        from dazzle_back.runtime.security_middleware import configure_cors_for_profile

        config = configure_cors_for_profile("basic")

        assert config.allow_origins == ["*"]
        # credentials must be False when origins=["*"] (CORS spec violation)
        assert config.allow_credentials is False

    def test_basic_cors_with_explicit_origins_allows_credentials(self) -> None:
        """Basic profile with explicit origins should allow credentials."""
        from dazzle_back.runtime.security_middleware import configure_cors_for_profile

        config = configure_cors_for_profile("basic", custom_origins=["https://myapp.com"])

        assert config.allow_origins == ["https://myapp.com"]
        assert config.allow_credentials is True

    def test_standard_cors_config(self) -> None:
        """Test standard profile CORS configuration."""
        from dazzle_back.runtime.security_middleware import configure_cors_for_profile

        config = configure_cors_for_profile("standard")

        assert config.allow_origins is None  # Same-origin
        assert config.allow_credentials is True
        assert "Authorization" in config.allow_headers
        assert "X-Tenant-ID" in config.allow_headers

    def test_strict_cors_config(self) -> None:
        """Test strict profile CORS configuration."""
        from dazzle_back.runtime.security_middleware import configure_cors_for_profile

        config = configure_cors_for_profile("strict")

        assert config.allow_origins is None  # Must be explicitly set
        assert "X-Request-ID" in config.expose_headers

    def test_custom_origins_override(self) -> None:
        """Test custom origins override profile defaults."""
        from dazzle_back.runtime.security_middleware import configure_cors_for_profile

        custom = ["https://example.com"]
        config = configure_cors_for_profile("basic", custom)

        assert config.allow_origins == custom

    def test_basic_headers_config(self) -> None:
        """Test basic profile has minimal headers."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("basic")

        assert config.enable_hsts is False
        assert config.enable_csp is False
        assert config.x_frame_options == "SAMEORIGIN"

    def test_standard_headers_config(self) -> None:
        """Standard profile emits CSP in Report-Only mode (#833)."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("standard")

        assert config.enable_hsts is True
        assert config.enable_csp is True
        assert config.csp_report_only is True
        assert config.x_frame_options == "DENY"

    def test_strict_headers_config(self) -> None:
        """Strict profile enforces CSP (not report-only)."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("strict")

        assert config.enable_hsts is True
        assert config.enable_csp is True
        assert config.csp_report_only is False
        assert config.x_frame_options == "DENY"


# =============================================================================
# Surface Access Tests
# =============================================================================


class TestSurfaceAccess:
    """Tests for surface access control."""

    def test_no_auth_required(self) -> None:
        """Test access allowed when auth not required."""
        from dazzle_back.runtime.surface_access import (
            SurfaceAccessConfig,
            check_surface_access,
        )

        config = SurfaceAccessConfig(require_auth=False)
        # Should not raise
        check_surface_access(config, None)

    def test_auth_required_no_user(self) -> None:
        """Test access denied when auth required but no user."""
        from dazzle_back.runtime.surface_access import (
            SurfaceAccessConfig,
            SurfaceAccessDenied,
            check_surface_access,
        )

        config = SurfaceAccessConfig(require_auth=True)
        with pytest.raises(SurfaceAccessDenied) as exc:
            check_surface_access(config, None)

        assert exc.value.is_auth_required is True
        assert "Authentication required" in exc.value.reason

    def test_auth_required_with_user(self) -> None:
        """Test access allowed for authenticated user."""
        from dazzle_back.runtime.surface_access import (
            SurfaceAccessConfig,
            check_surface_access,
        )

        config = SurfaceAccessConfig(require_auth=True)
        # Should not raise
        check_surface_access(config, {"id": "user-123"})

    def test_allow_personas_match(self) -> None:
        """Test access allowed when user has allowed persona."""
        from dazzle_back.runtime.surface_access import (
            SurfaceAccessConfig,
            check_surface_access,
        )

        config = SurfaceAccessConfig(
            require_auth=True,
            allow_personas=["admin", "manager"],
        )
        # Should not raise
        check_surface_access(config, {"id": "user-123"}, ["admin"])

    def test_allow_personas_no_match(self) -> None:
        """Test access denied when user lacks allowed persona."""
        from dazzle_back.runtime.surface_access import (
            SurfaceAccessConfig,
            SurfaceAccessDenied,
            check_surface_access,
        )

        config = SurfaceAccessConfig(
            require_auth=True,
            allow_personas=["admin"],
        )
        with pytest.raises(SurfaceAccessDenied) as exc:
            check_surface_access(config, {"id": "user-123"}, ["viewer"])

        assert exc.value.is_auth_required is False
        assert "admin" in exc.value.reason

    def test_deny_personas(self) -> None:
        """Test access denied when user has denied persona."""
        from dazzle_back.runtime.surface_access import (
            SurfaceAccessConfig,
            SurfaceAccessDenied,
            check_surface_access,
        )

        config = SurfaceAccessConfig(
            require_auth=True,
            deny_personas=["blocked"],
        )
        with pytest.raises(SurfaceAccessDenied) as exc:
            check_surface_access(config, {"id": "user-123"}, ["blocked"])

        assert "blocked" in exc.value.reason

    def test_deny_takes_precedence(self) -> None:
        """Test deny list takes precedence over allow list."""
        from dazzle_back.runtime.surface_access import (
            SurfaceAccessConfig,
            SurfaceAccessDenied,
            check_surface_access,
        )

        config = SurfaceAccessConfig(
            require_auth=True,
            allow_personas=["admin"],
            deny_personas=["suspended"],
        )
        with pytest.raises(SurfaceAccessDenied):
            # User is admin but also suspended
            check_surface_access(config, {"id": "user-123"}, ["admin", "suspended"])

    def test_redirect_url_for_ui(self) -> None:
        """Test redirect URL provided for UI requests."""
        from dazzle_back.runtime.surface_access import (
            SurfaceAccessConfig,
            SurfaceAccessDenied,
            check_surface_access,
        )

        config = SurfaceAccessConfig(
            require_auth=True,
            redirect_unauthenticated="/login",
        )
        with pytest.raises(SurfaceAccessDenied) as exc:
            check_surface_access(config, None, is_api_request=False)

        assert exc.value.redirect_url == "/login"


# =============================================================================
# Tenant Isolation Tests (PostgreSQL schema-based)
# =============================================================================


class TestTenantIsolation:
    """Tests for tenant schema isolation — context vars and slug validation."""

    def test_tenant_schema_generation(self) -> None:
        """Test tenant schema name generation via dazzle.tenant."""
        from dazzle.tenant.config import slug_to_schema_name

        assert slug_to_schema_name("cyfuture") == "tenant_cyfuture"
        assert slug_to_schema_name("smith_co") == "tenant_smith_co"

    def test_tenant_slug_validation(self) -> None:
        """Test tenant slug validation rejects invalid input."""
        from dazzle.tenant.config import validate_slug

        # Valid slugs
        validate_slug("cyfuture")
        validate_slug("smith_co")

        # Invalid slugs
        with pytest.raises(ValueError):
            validate_slug("")
        with pytest.raises(ValueError):
            validate_slug("../../../etc/passwd")
        with pytest.raises(ValueError):
            validate_slug("smith-co")  # hyphens not allowed

    def test_context_var_set_and_get(self) -> None:
        """Test tenant context var lifecycle."""
        from dazzle_back.runtime.tenant_isolation import (
            _current_tenant_schema,
            get_current_tenant_schema,
            set_current_tenant_schema,
        )

        assert get_current_tenant_schema() is None
        token = set_current_tenant_schema("tenant_cyfuture")
        try:
            assert get_current_tenant_schema() == "tenant_cyfuture"
        finally:
            _current_tenant_schema.reset(token)
        assert get_current_tenant_schema() is None


# =============================================================================
# Security Docs Tests
# =============================================================================


class TestSecurityDocs:
    """Tests for SECURITY.md generation."""

    def test_generate_basic_security_md(self) -> None:
        """Test generating SECURITY.md for basic profile."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile
        from dazzle.specs.security_docs import generate_security_md

        app_spec = MagicMock()
        app_spec.name = "TestApp"
        app_spec.surfaces = []
        app_spec.security = SecurityConfig.from_profile(SecurityProfile.BASIC)

        content = generate_security_md(app_spec)

        assert "TestApp" in content
        assert "basic" in content
        assert "Permissive" in content
        assert "Only appropriate for development" in content

    def test_generate_strict_security_md(self) -> None:
        """Test generating SECURITY.md for strict profile."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile
        from dazzle.specs.security_docs import generate_security_md

        app_spec = MagicMock()
        app_spec.name = "SecureApp"
        app_spec.surfaces = []
        app_spec.security = SecurityConfig.from_profile(
            SecurityProfile.STRICT,
            multi_tenant=True,
        )

        content = generate_security_md(app_spec)

        assert "strict" in content
        assert "Strict-Transport-Security" in content
        assert "Content-Security-Policy" in content
        assert "Tenant Isolation" in content
        assert "Enabled" in content

    def test_generate_protected_surfaces_table(self) -> None:
        """Test generating protected surfaces table."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile
        from dazzle.specs.security_docs import generate_security_md

        access = MagicMock()
        access.require_auth = True
        access.allow_personas = ["admin", "manager"]
        access.deny_personas = []
        access.redirect_unauthenticated = "/login"

        surface = MagicMock()
        surface.name = "admin_dashboard"
        surface.access = access

        app_spec = MagicMock()
        app_spec.name = "TestApp"
        app_spec.surfaces = [surface]
        app_spec.security = SecurityConfig.from_profile(SecurityProfile.STANDARD)

        content = generate_security_md(app_spec)

        assert "Protected Surfaces" in content
        assert "admin_dashboard" in content
        assert "admin" in content
        assert "/login" in content

    def test_write_security_md(self) -> None:
        """Test writing SECURITY.md to file."""
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile
        from dazzle.specs.security_docs import write_security_md

        app_spec = MagicMock()
        app_spec.name = "TestApp"
        app_spec.surfaces = []
        app_spec.security = SecurityConfig.from_profile(SecurityProfile.BASIC)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "SECURITY.md"
            result = write_security_md(app_spec, str(output_path))

            assert Path(result).exists()
            content = Path(result).read_text()
            assert "TestApp" in content


# =============================================================================
# Parser Tests
# =============================================================================


class TestSecurityParser:
    """Tests for security_profile parsing."""

    def test_parse_security_profile(self) -> None:
        """Test parsing security_profile in app config."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """
module test_app
app TestApp "Test Application":
  description: "Test app"
  security_profile: standard
  multi_tenant: true

entity Task "Task":
  id: uuid pk
  title: str(200) required
"""
        _, _, _, app_config, _, _ = parse_dsl(dsl, Path("test.dsl"))

        assert app_config is not None
        assert app_config.security_profile == "standard"
        assert app_config.multi_tenant is True

    def test_parse_security_profile_strict(self) -> None:
        """Test parsing strict security profile."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """
module secure_app
app SecureApp "Secure Application":
  security_profile: strict

entity User "User":
  id: uuid pk
  name: str(100) required
"""
        _, _, _, app_config, _, _ = parse_dsl(dsl, Path("test.dsl"))

        assert app_config is not None
        assert app_config.security_profile == "strict"

    def test_default_security_profile(self) -> None:
        """Test default security profile is basic."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """
module basic_app
app BasicApp "Basic Application":
  description: "No security profile specified"

entity Task "Task":
  id: uuid pk
  title: str(200) required
"""
        _, _, _, app_config, _, _ = parse_dsl(dsl, Path("test.dsl"))

        assert app_config is not None
        assert app_config.security_profile == "basic"


# =============================================================================
# CSP Default Directives + Report-Only Mode (#833)
# =============================================================================


def _csp_tokens(csp: str, directive: str) -> list[str]:
    """Return the whitespace-separated token list for a CSP directive.

    Parsing into tokens (rather than substring-matching the raw header) keeps
    membership tests exact — required to avoid CodeQL's
    py/incomplete-url-substring-sanitization false positive on `"url" in csp`.
    """
    for part in csp.split("; "):
        name, _, rest = part.partition(" ")
        if name == directive:
            return rest.split()
    return []


def _csp_all_tokens(csp: str) -> list[str]:
    tokens: list[str] = []
    for part in csp.split("; "):
        _, _, rest = part.partition(" ")
        tokens.extend(rest.split())
    return tokens


class TestCSPDefaults:
    """Default CSP directives must align with what the bundled shells load."""

    def test_defaults_allow_google_fonts(self) -> None:
        from dazzle_back.runtime.security_middleware import _build_csp_header

        tokens = _csp_all_tokens(_build_csp_header(None))
        assert "https://fonts.googleapis.com" in tokens
        assert "https://fonts.gstatic.com" in tokens

    def test_defaults_allow_jsdelivr_for_mermaid(self) -> None:
        """diagram.html lazy-loads mermaid from jsdelivr — CSP must permit it."""
        from dazzle_back.runtime.security_middleware import _build_csp_header

        csp = _build_csp_header(None)
        script_src = _csp_tokens(csp, "script-src")
        assert "https://cdn.jsdelivr.net" in script_src

    def test_defaults_do_not_allow_tailwind_cdn(self) -> None:
        """Post-#832, cdn.tailwindcss.com must NOT be in the defaults."""
        from dazzle_back.runtime.security_middleware import _build_csp_header

        tokens = _csp_all_tokens(_build_csp_header(None))
        assert not any("cdn.tailwindcss.com" in t for t in tokens)

    def test_custom_directives_override_defaults(self) -> None:
        from dazzle_back.runtime.security_middleware import _build_csp_header

        csp = _build_csp_header({"script-src": "'self'"})
        directives = {d.split(" ", 1)[0]: d for d in csp.split("; ")}
        assert directives["script-src"] == "script-src 'self'"


class TestCSPReportOnly:
    """The middleware must emit the Report-Only header when configured."""

    def test_enforcing_header_by_default(self) -> None:
        from dazzle_back.runtime.security_middleware import (
            SecurityHeadersConfig,
            create_security_headers_middleware,
        )

        config = SecurityHeadersConfig(enable_csp=True, csp_report_only=False)
        middleware = create_security_headers_middleware(config)
        # Structural smoke test — the middleware class carries the config.
        assert middleware is not None

    def test_report_only_config_exists(self) -> None:
        from dazzle_back.runtime.security_middleware import SecurityHeadersConfig

        config = SecurityHeadersConfig(enable_csp=True, csp_report_only=True)
        assert config.csp_report_only is True

    def test_standard_profile_uses_report_only(self) -> None:
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("standard")
        assert config.enable_csp is True
        assert config.csp_report_only is True

    def test_strict_profile_enforces(self) -> None:
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("strict")
        assert config.enable_csp is True
        assert config.csp_report_only is False
