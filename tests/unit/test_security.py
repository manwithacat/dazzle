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


def test_security_config_combined() -> None:
    """Combined SecurityConfig contract:
    - SecurityProfile enum string values are 'basic'/'standard'/'strict'.
    - BASIC profile is permissive (no HSTS/CSP/auth, cors=*).
    - STANDARD enables HSTS + CSP (Report-Only) + auth.
    - STRICT enables HSTS + CSP + auth.
    - STRICT + multi_tenant=True enables tenant_isolation.
    - Custom cors_origins override profile defaults.
    """
    from dazzle.core.ir.security import SecurityConfig, SecurityProfile

    # Enum values.
    assert SecurityProfile.BASIC.value == "basic"
    assert SecurityProfile.STANDARD.value == "standard"
    assert SecurityProfile.STRICT.value == "strict"

    # BASIC defaults — permissive.
    basic = SecurityConfig.from_profile(SecurityProfile.BASIC)
    assert basic.profile == SecurityProfile.BASIC
    assert basic.cors_origins == ["*"]
    assert basic.enable_hsts is False
    assert basic.enable_csp is False
    assert basic.require_auth_by_default is False
    assert basic.tenant_isolation is False

    # STANDARD — same-origin, HSTS + CSP, auth on.
    standard = SecurityConfig.from_profile(SecurityProfile.STANDARD)
    assert standard.profile == SecurityProfile.STANDARD
    assert standard.cors_origins is None
    assert standard.enable_hsts is True
    assert standard.enable_csp is True  # #833 — runtime emits Report-Only
    assert standard.require_auth_by_default is True
    assert standard.tenant_isolation is False

    # STRICT defaults.
    strict = SecurityConfig.from_profile(SecurityProfile.STRICT)
    assert strict.profile == SecurityProfile.STRICT
    assert strict.enable_hsts is True
    assert strict.enable_csp is True
    assert strict.require_auth_by_default is True

    # STRICT + multi_tenant.
    strict_mt = SecurityConfig.from_profile(SecurityProfile.STRICT, multi_tenant=True)
    assert strict_mt.tenant_isolation is True

    # Custom cors_origins override.
    custom = ["https://app.example.com", "https://admin.example.com"]
    custom_cfg = SecurityConfig.from_profile(SecurityProfile.STANDARD, cors_origins=custom)
    assert custom_cfg.cors_origins == custom


# =============================================================================
# Security Middleware Tests
# =============================================================================


def test_cors_config_combined() -> None:
    """Combined configure_cors_for_profile contract for all 3 profiles
    + custom-origins override + credentials toggling."""
    from dazzle_back.runtime.security_middleware import configure_cors_for_profile

    # BASIC — wildcard origins forbid credentials.
    basic = configure_cors_for_profile("basic")
    assert basic.allow_origins == ["*"]
    assert basic.allow_credentials is False

    # BASIC with explicit origins → credentials allowed.
    basic_custom = configure_cors_for_profile("basic", custom_origins=["https://myapp.com"])
    assert basic_custom.allow_origins == ["https://myapp.com"]
    assert basic_custom.allow_credentials is True

    # STANDARD — same-origin, credentials on, headers include Authorization + X-Tenant-ID.
    standard = configure_cors_for_profile("standard")
    assert standard.allow_origins is None
    assert standard.allow_credentials is True
    assert "Authorization" in standard.allow_headers
    assert "X-Tenant-ID" in standard.allow_headers

    # STRICT — same-origin, X-Request-ID exposed.
    strict = configure_cors_for_profile("strict")
    assert strict.allow_origins is None
    assert "X-Request-ID" in strict.expose_headers

    # Custom origins override (positional arg).
    custom = configure_cors_for_profile("basic", ["https://example.com"])
    assert custom.allow_origins == ["https://example.com"]


def test_headers_config_combined() -> None:
    """Combined configure_headers_for_profile contract for all 3 profiles."""
    from dazzle_back.runtime.security_middleware import configure_headers_for_profile

    # BASIC — minimal: no HSTS/CSP, frame=SAMEORIGIN.
    basic = configure_headers_for_profile("basic")
    assert basic.enable_hsts is False
    assert basic.enable_csp is False
    assert basic.x_frame_options == "SAMEORIGIN"

    # STANDARD — HSTS+CSP, Report-Only (#833), frame=DENY.
    standard = configure_headers_for_profile("standard")
    assert standard.enable_hsts is True
    assert standard.enable_csp is True
    assert standard.csp_report_only is True
    assert standard.x_frame_options == "DENY"

    # STRICT — HSTS+CSP enforced (not Report-Only).
    strict = configure_headers_for_profile("strict")
    assert strict.enable_hsts is True
    assert strict.enable_csp is True
    assert strict.csp_report_only is False
    assert strict.x_frame_options == "DENY"


# =============================================================================
# Surface Access Tests
# =============================================================================


def test_surface_access_combined() -> None:
    """Combined check_surface_access contract:
    - require_auth=False allows anyone (None user OK).
    - require_auth=True without user → denied (is_auth_required=True).
    - require_auth=True with user → allowed.
    - allow_personas: matching persona allowed; non-matching denied.
    - deny_personas: denied persona always denied (precedence over allow).
    - redirect_unauthenticated provides redirect_url for UI requests.
    """
    from dazzle_back.runtime.surface_access import (
        SurfaceAccessConfig,
        SurfaceAccessDenied,
        check_surface_access,
    )

    # No auth required — None user OK.
    check_surface_access(SurfaceAccessConfig(require_auth=False), None)

    # Auth required, no user → denied with is_auth_required=True.
    cfg_auth = SurfaceAccessConfig(require_auth=True)
    with pytest.raises(SurfaceAccessDenied) as exc:
        check_surface_access(cfg_auth, None)
    assert exc.value.is_auth_required is True
    assert "Authentication required" in exc.value.reason

    # Auth required, user present → allowed.
    check_surface_access(cfg_auth, {"id": "user-123"})

    # allow_personas match → allowed.
    cfg_allow = SurfaceAccessConfig(require_auth=True, allow_personas=["admin", "manager"])
    check_surface_access(cfg_allow, {"id": "user-123"}, ["admin"])

    # allow_personas no match → denied (is_auth_required=False).
    cfg_strict = SurfaceAccessConfig(require_auth=True, allow_personas=["admin"])
    with pytest.raises(SurfaceAccessDenied) as exc2:
        check_surface_access(cfg_strict, {"id": "user-123"}, ["viewer"])
    assert exc2.value.is_auth_required is False
    assert "admin" in exc2.value.reason

    # deny_personas → denied.
    cfg_deny = SurfaceAccessConfig(require_auth=True, deny_personas=["blocked"])
    with pytest.raises(SurfaceAccessDenied) as exc3:
        check_surface_access(cfg_deny, {"id": "user-123"}, ["blocked"])
    assert "blocked" in exc3.value.reason

    # deny precedence over allow.
    cfg_both = SurfaceAccessConfig(
        require_auth=True, allow_personas=["admin"], deny_personas=["suspended"]
    )
    with pytest.raises(SurfaceAccessDenied):
        check_surface_access(cfg_both, {"id": "user-123"}, ["admin", "suspended"])

    # redirect_url for UI request.
    cfg_redir = SurfaceAccessConfig(require_auth=True, redirect_unauthenticated="/login")
    with pytest.raises(SurfaceAccessDenied) as exc4:
        check_surface_access(cfg_redir, None, is_api_request=False)
    assert exc4.value.redirect_url == "/login"


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
