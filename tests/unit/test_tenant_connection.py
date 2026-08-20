"""Tests for tenant connection routing — context vars and schema resolution."""

import pytest


class TestTenantContextVars:
    def test_default_is_none(self) -> None:
        from dazzle.http.runtime.tenant_isolation import get_current_tenant_schema

        assert get_current_tenant_schema() is None

    def test_set_and_get(self) -> None:
        from dazzle.http.runtime.tenant_isolation import (
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
        from dazzle.http.runtime.tenant_isolation import (
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
        from dazzle.http.runtime.tenant_isolation import (
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
        from dazzle.http.runtime.tenant_isolation import get_current_tenant_schema

        assert get_current_tenant_schema() is None


class TestSchemaIsolationFailClosed:
    """#1651 — schema isolation must not silently lease public for entity SQL."""

    def test_none_isolation_unbound_is_none(self) -> None:
        from dazzle.http.runtime.tenant_isolation import resolve_schema_lease

        assert (
            resolve_schema_lease(
                isolation="none",
                platform=False,
                tenant_schema=None,
                instance_search_path=None,
            )
            is None
        )

    def test_schema_isolation_unbound_raises(self) -> None:
        from dazzle.http.runtime.tenant_isolation import (
            TenantContextError,
            resolve_schema_lease,
        )

        with pytest.raises(TenantContextError, match="bound tenant"):
            resolve_schema_lease(
                isolation="schema",
                platform=False,
                tenant_schema=None,
                instance_search_path=None,
            )

    def test_schema_isolation_bound_tenant_rides(self) -> None:
        from dazzle.http.runtime.tenant_isolation import resolve_schema_lease

        assert (
            resolve_schema_lease(
                isolation="schema",
                platform=False,
                tenant_schema="tenant_cyfuture",
                instance_search_path=None,
            )
            == "tenant_cyfuture"
        )

    def test_schema_isolation_instance_search_path_rides(self) -> None:
        from dazzle.http.runtime.tenant_isolation import resolve_schema_lease

        assert (
            resolve_schema_lease(
                isolation="schema",
                platform=False,
                tenant_schema=None,
                instance_search_path="tenant_abc",
            )
            == "tenant_abc"
        )

    def test_platform_lease_is_public(self) -> None:
        from dazzle.http.runtime.tenant_isolation import resolve_schema_lease

        assert (
            resolve_schema_lease(
                isolation="schema",
                platform=True,
                tenant_schema=None,
                instance_search_path=None,
            )
            == "public"
        )

    def test_platform_wins_over_bound_tenant(self) -> None:
        from dazzle.http.runtime.tenant_isolation import resolve_schema_lease

        assert (
            resolve_schema_lease(
                isolation="schema",
                platform=True,
                tenant_schema="tenant_cyfuture",
                instance_search_path=None,
            )
            == "public"
        )

    def test_bound_tenant_schema_sets_and_resets(self) -> None:
        from dazzle.http.runtime.tenant_isolation import (
            bound_tenant_schema,
            get_current_tenant_schema,
        )

        assert get_current_tenant_schema() is None
        with bound_tenant_schema("tenant_demo"):
            assert get_current_tenant_schema() == "tenant_demo"
        assert get_current_tenant_schema() is None

    def test_bound_tenant_schema_rejects_leftover_name(self) -> None:
        from dazzle.http.runtime.tenant_isolation import (
            TenantContextError,
            bound_tenant_schema,
        )

        with pytest.raises(TenantContextError, match="invalid schema name"):
            with bound_tenant_schema("zzz; drop"):
                pass

    def test_connection_raises_before_connect(self) -> None:
        """A missing tenant must not open a TCP session onto public."""
        from unittest.mock import patch

        from dazzle.http.runtime.pg_backend import PostgresBackend
        from dazzle.http.runtime.tenant_isolation import TenantContextError

        backend = PostgresBackend("postgresql://localhost:5432/test_db", isolation="schema")
        with patch("psycopg.connect") as mock_connect:
            with pytest.raises(TenantContextError, match="bound tenant"):
                with backend.connection():
                    pass
        mock_connect.assert_not_called()

    def test_connection_with_bound_tenant_connects(self) -> None:
        from unittest.mock import MagicMock, patch

        from dazzle.http.runtime.pg_backend import PostgresBackend
        from dazzle.http.runtime.tenant_isolation import bound_tenant_schema

        backend = PostgresBackend("postgresql://localhost:5432/test_db", isolation="schema")
        mock_conn = MagicMock()
        mock_conn.closed = False
        with patch("psycopg.connect", return_value=mock_conn) as mock_connect:
            with bound_tenant_schema("tenant_cyfuture"):
                with backend.connection() as conn:
                    assert conn is not None
        mock_connect.assert_called_once()
        composed = mock_conn.execute.call_args[0][0]
        assert "tenant_cyfuture" in str(composed)

    def test_platform_connection_sets_public_only(self) -> None:
        from unittest.mock import MagicMock, patch

        from psycopg.sql import SQL

        from dazzle.http.runtime.pg_backend import PostgresBackend

        backend = PostgresBackend("postgresql://localhost:5432/test_db", isolation="schema")
        mock_conn = MagicMock()
        mock_conn.closed = False
        with patch("psycopg.connect", return_value=mock_conn):
            with backend.connection(platform=True):
                pass
        executed = mock_conn.execute.call_args[0][0]
        assert isinstance(executed, SQL)
        assert "public" in str(executed)

    def test_persistent_connection_refuses_schema_isolation(self) -> None:
        from unittest.mock import patch

        from dazzle.http.runtime.pg_backend import PostgresBackend
        from dazzle.http.runtime.tenant_isolation import TenantContextError

        backend = PostgresBackend("postgresql://localhost:5432/test_db", isolation="schema")
        with patch("psycopg.connect") as mock_connect:
            with pytest.raises(TenantContextError, match="not tenant-safe"):
                backend.get_persistent_connection()
        mock_connect.assert_not_called()

    def test_server_constructs_backend_with_schema_isolation(self) -> None:
        from unittest.mock import MagicMock, patch

        from dazzle.core import ir
        from dazzle.core.manifest import TenantConfig
        from dazzle.http.runtime.server import DazzleBackendApp, ServerConfig

        entity = ir.EntitySpec(
            name="Contact",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
        )
        appspec = ir.AppSpec(name="cyfuture", domain=ir.DomainSpec(entities=[entity]))
        builder = DazzleBackendApp(
            appspec,
            config=ServerConfig(
                database_url="postgresql://example/test",
                tenant_config=TenantConfig(isolation="schema"),
            ),
        )
        mock_backend = MagicMock()
        mock_backend.connection.return_value.__enter__.return_value = MagicMock()
        mock_backend.connection.return_value.__exit__.return_value = False
        mock_registry = MagicMock()
        with (
            patch("dazzle.tenant.registry.TenantRegistry", return_value=mock_registry),
            patch(
                "dazzle.http.runtime.pg_backend.PostgresBackend",
                return_value=mock_backend,
            ) as mock_pg,
            patch("dazzle.http.runtime.framework_schema.ensure_framework_schema"),
            patch("sqlalchemy.create_engine", return_value=MagicMock()),
            patch.dict("os.environ", {"DAZZLE_ENV": "development"}, clear=False),
        ):
            builder._create_app()
            builder._setup_models()
            builder._setup_database()
        assert mock_pg.call_args.kwargs.get("isolation") == "schema"
