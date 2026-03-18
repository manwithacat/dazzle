"""Tests for tenant configuration."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from dazzle.core.manifest import TenantConfig, load_manifest


class TestTenantConfigDefaults:
    def test_default_isolation_is_none(self) -> None:
        config = TenantConfig()
        assert config.isolation == "none"

    def test_default_resolver(self) -> None:
        config = TenantConfig()
        assert config.resolver == "subdomain"

    def test_default_header_name(self) -> None:
        config = TenantConfig()
        assert config.header_name == "X-Tenant-ID"


class TestTenantConfigFromManifest:
    def test_absent_tenant_section_gives_defaults(self, tmp_path: Path) -> None:
        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            dedent("""\
            [project]
            name = "test"
            version = "0.1.0"
        """)
        )
        manifest = load_manifest(toml)
        assert manifest.tenant.isolation == "none"

    def test_schema_isolation_parsed(self, tmp_path: Path) -> None:
        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            dedent("""\
            [project]
            name = "test"
            version = "0.1.0"

            [tenant]
            isolation = "schema"
            resolver = "header"
            header_name = "X-Custom-Tenant"
        """)
        )
        manifest = load_manifest(toml)
        assert manifest.tenant.isolation == "schema"
        assert manifest.tenant.resolver == "header"
        assert manifest.tenant.header_name == "X-Custom-Tenant"
