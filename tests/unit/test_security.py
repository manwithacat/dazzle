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
        assert config.enable_csp is False  # Can break apps
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
        """Test standard profile has reasonable headers."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("standard")

        assert config.enable_hsts is True
        assert config.enable_csp is False
        assert config.x_frame_options == "DENY"

    def test_strict_headers_config(self) -> None:
        """Test strict profile has full headers."""
        from dazzle_back.runtime.security_middleware import configure_headers_for_profile

        config = configure_headers_for_profile("strict")

        assert config.enable_hsts is True
        assert config.enable_csp is True
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
# Tenant Isolation Tests
# =============================================================================


class TestTenantIsolation:
    """Tests for tenant database isolation."""

    def test_tenant_path_generation(self) -> None:
        """Test tenant database path generation."""
        from dazzle_back.runtime.tenant_isolation import TenantDatabaseManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TenantDatabaseManager(base_dir=tmpdir)
            path = manager._get_tenant_path("tenant-123")

            assert "tenant-123" in str(path)
            assert path.name == "data.db"

    def test_tenant_path_sanitization(self) -> None:
        """Test tenant ID is sanitized to prevent path traversal."""
        from dazzle_back.runtime.tenant_isolation import TenantDatabaseManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TenantDatabaseManager(base_dir=tmpdir)

            # Should work with alphanumeric and dashes
            path = manager._get_tenant_path("tenant-123-abc")
            assert "tenant-123-abc" in str(path)

            # Path traversal characters are stripped, path is sanitized
            # The sanitization removes special chars, so "../../../etc/passwd" becomes "etcpasswd"
            path = manager._get_tenant_path("../../../etc/passwd")
            # Should NOT contain any path traversal
            assert ".." not in str(path)
            assert "/" not in path.name

            # Empty string should raise
            with pytest.raises(ValueError):
                manager._get_tenant_path("")

    def test_list_tenants_empty(self) -> None:
        """Test listing tenants when none exist."""
        from dazzle_back.runtime.tenant_isolation import TenantDatabaseManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TenantDatabaseManager(base_dir=tmpdir)
            tenants = manager.list_tenants()

            assert tenants == []

    def test_tenant_exists_false(self) -> None:
        """Test tenant_exists returns False for non-existent tenant."""
        from dazzle_back.runtime.tenant_isolation import TenantDatabaseManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TenantDatabaseManager(base_dir=tmpdir)

            assert manager.tenant_exists("tenant-123") is False

    def test_delete_nonexistent_tenant(self) -> None:
        """Test deleting non-existent tenant returns False."""
        from dazzle_back.runtime.tenant_isolation import TenantDatabaseManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TenantDatabaseManager(base_dir=tmpdir)

            assert manager.delete_tenant("tenant-123") is False

    def test_get_tenant_manager_creates_manager(self) -> None:
        """Test get_tenant_manager creates a DatabaseManager."""
        from dazzle_back.runtime.tenant_isolation import TenantDatabaseManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TenantDatabaseManager(base_dir=tmpdir)
            tenant_db = manager.get_tenant_manager("tenant-123")

            assert tenant_db is not None
            assert "tenant-123" in str(tenant_db.db_path)

    def test_get_tenant_manager_cached(self) -> None:
        """Test get_tenant_manager returns cached manager."""
        from dazzle_back.runtime.tenant_isolation import TenantDatabaseManager

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TenantDatabaseManager(base_dir=tmpdir)
            db1 = manager.get_tenant_manager("tenant-123")
            db2 = manager.get_tenant_manager("tenant-123")

            assert db1 is db2


# =============================================================================
# Security Docs Tests
# =============================================================================


class TestSecurityDocs:
    """Tests for SECURITY.md generation."""

    def test_generate_basic_security_md(self) -> None:
        """Test generating SECURITY.md for basic profile."""
        from unittest.mock import MagicMock

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
        from unittest.mock import MagicMock

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
        from unittest.mock import MagicMock

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
        from unittest.mock import MagicMock

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
