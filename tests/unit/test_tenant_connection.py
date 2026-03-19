"""Tests for tenant connection routing — context vars and schema resolution."""

from __future__ import annotations

import pytest


class TestTenantContextVars:
    def test_default_is_none(self) -> None:
        from dazzle_back.runtime.tenant_isolation import get_current_tenant_schema

        assert get_current_tenant_schema() is None

    def test_set_and_get(self) -> None:
        from dazzle_back.runtime.tenant_isolation import (
            _current_tenant_schema,
            get_current_tenant_schema,
            set_current_tenant_schema,
        )

        token = set_current_tenant_schema("tenant_cyfuture")
        try:
            assert get_current_tenant_schema() == "tenant_cyfuture"
        finally:
            _current_tenant_schema.reset(token)

    def test_reset_clears(self) -> None:
        from dazzle_back.runtime.tenant_isolation import (
            _current_tenant_schema,
            get_current_tenant_schema,
            set_current_tenant_schema,
        )

        token = set_current_tenant_schema("tenant_test")
        _current_tenant_schema.reset(token)
        assert get_current_tenant_schema() is None


class TestManifestBaseDomain:
    def test_base_domain_default(self) -> None:
        from dazzle.core.manifest import TenantConfig

        config = TenantConfig()
        assert config.base_domain == ""

    def test_base_domain_parsed(self, tmp_path: pytest.TempPathFactory) -> None:
        from textwrap import dedent

        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"  # type: ignore[operator]
        toml.write_text(
            dedent("""\
            [project]
            name = "test"
            version = "0.1.0"

            [tenant]
            isolation = "schema"
            resolver = "subdomain"
            base_domain = "app.example.com"
        """)
        )
        manifest = load_manifest(toml)
        assert manifest.tenant.base_domain == "app.example.com"


class TestPgBackendTenantRouting:
    def test_context_var_readable(self) -> None:
        """When context var is set, it should be readable from pg_backend's perspective."""
        from dazzle_back.runtime.tenant_isolation import (
            _current_tenant_schema,
            get_current_tenant_schema,
            set_current_tenant_schema,
        )

        token = set_current_tenant_schema("tenant_cyfuture")
        try:
            assert get_current_tenant_schema() == "tenant_cyfuture"
        finally:
            _current_tenant_schema.reset(token)

    def test_no_context_var_returns_none(self) -> None:
        """Without context var, get_current_tenant_schema returns None."""
        from dazzle_back.runtime.tenant_isolation import get_current_tenant_schema

        assert get_current_tenant_schema() is None
