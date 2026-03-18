"""Tests for tenant configuration."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from dazzle.core.manifest import TenantConfig, load_manifest
from dazzle.tenant.config import slug_to_schema_name, validate_slug


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


class TestSlugValidation:
    def test_valid_slug(self) -> None:
        validate_slug("cyfuture_uk")

    def test_valid_single_char_start(self) -> None:
        validate_slug("ab")

    def test_rejects_uppercase(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("CyFuture")

    def test_rejects_starts_with_number(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("1invalid")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("a" * 57)

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("")

    def test_rejects_special_chars(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("my-tenant")

    def test_max_valid_length(self) -> None:
        validate_slug("a" * 56)


class TestSlugToSchemaName:
    def test_prefixes_with_tenant(self) -> None:
        assert slug_to_schema_name("cyfuture") == "tenant_cyfuture"

    def test_total_length_within_pg_limit(self) -> None:
        schema = slug_to_schema_name("a" * 56)
        assert len(schema) <= 63
