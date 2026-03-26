"""Tests for TenantProvisioner — schema creation and table provisioning."""

from unittest.mock import MagicMock, patch

from dazzle.tenant.provisioner import TenantProvisioner


class TestSchemaCreation:
    @patch("dazzle.tenant.provisioner.psycopg")
    @patch("dazzle.tenant.provisioner.pgsql")
    def test_creates_schema_and_runs_alembic_upgrade(
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

        with patch("alembic.command.upgrade") as mock_upgrade:
            provisioner.provision("tenant_cyfuture")

            # Schema creation SQL was executed
            assert mock_cursor.execute.call_count >= 1

            # Alembic upgrade was called
            mock_upgrade.assert_called_once()
            call_args = mock_upgrade.call_args
            cfg = call_args[0][0]
            assert call_args[0][1] == "head"
            assert cfg.attributes["tenant_schema"] == "tenant_cyfuture"

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
