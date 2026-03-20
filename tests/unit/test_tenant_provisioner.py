"""Tests for TenantProvisioner — schema creation and table provisioning."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dazzle.tenant.provisioner import TenantProvisioner


class TestSchemaCreation:
    @patch("dazzle.tenant.provisioner.psycopg")
    @patch("dazzle.tenant.provisioner.pgsql")
    def test_creates_schema_and_runs_auto_migrate(
        self, mock_pgsql: MagicMock, mock_psycopg: MagicMock
    ) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_psycopg.connect.return_value = mock_conn

        # Mock pgsql.SQL and pgsql.Identifier
        mock_composed = MagicMock()
        mock_pgsql.SQL.return_value.format.return_value = mock_composed
        mock_pgsql.Identifier.return_value = MagicMock()

        appspec = MagicMock()
        e1 = MagicMock()
        e1.name = "Contact"
        e2 = MagicMock()
        e2.name = "Invoice"
        appspec.domain.entities = [e1, e2]

        provisioner = TenantProvisioner("postgresql://localhost/test", appspec)

        mock_plan = MagicMock()
        mock_plan.steps = [MagicMock(action="create_table"), MagicMock(action="create_table")]

        with (
            patch(
                "dazzle_back.runtime.migrations.auto_migrate", return_value=mock_plan
            ) as mock_migrate,
            patch("dazzle_back.converters.entity_converter.convert_entities", return_value=[]),
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
        ):
            provisioner.provision("tenant_cyfuture")

            # Schema creation SQL was executed
            assert mock_cursor.execute.call_count >= 1

            # auto_migrate was called with the tenant schema
            mock_migrate.assert_called_once()
            call_kwargs = mock_migrate.call_args
            assert call_kwargs.kwargs.get("schema") == "tenant_cyfuture"
            assert call_kwargs.kwargs.get("record_history") is False

    @patch("dazzle.tenant.provisioner.psycopg")
    def test_schema_exists_true(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {"exists": True}
        mock_psycopg.connect.return_value = mock_conn

        provisioner = TenantProvisioner("postgresql://localhost/test", MagicMock())
        assert provisioner.schema_exists("tenant_cyfuture") is True

    @patch("dazzle.tenant.provisioner.psycopg")
    def test_schema_exists_false(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {"exists": False}
        mock_psycopg.connect.return_value = mock_conn

        provisioner = TenantProvisioner("postgresql://localhost/test", MagicMock())
        assert provisioner.schema_exists("tenant_cyfuture") is False
