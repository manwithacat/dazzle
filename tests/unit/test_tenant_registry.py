"""Tests for TenantRegistry — CRUD on public.tenants."""

from unittest.mock import MagicMock, patch

import pytest

from dazzle.tenant.registry import TenantRecord, TenantRegistry


class TestTenantRecord:
    def test_fields(self) -> None:
        record = TenantRecord(
            id="uuid-1",
            slug="cyfuture",
            display_name="CyFuture UK",
            schema_name="tenant_cyfuture",
            status="active",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        assert record.slug == "cyfuture"
        assert record.schema_name == "tenant_cyfuture"


class TestTenantRegistryCreate:
    @patch("dazzle.tenant.registry.psycopg")
    def test_create_tenant(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {
            "id": "uuid-1",
            "slug": "cyfuture",
            "display_name": "CyFuture UK",
            "schema_name": "tenant_cyfuture",
            "status": "active",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        record = registry.create("cyfuture", "CyFuture UK")

        assert record.slug == "cyfuture"
        assert record.schema_name == "tenant_cyfuture"
        assert mock_cursor.execute.called

    @patch("dazzle.tenant.registry.psycopg")
    def test_create_validates_slug(self, mock_psycopg: MagicMock) -> None:
        registry = TenantRegistry("postgresql://localhost/test")
        with pytest.raises(ValueError, match="Slug must match"):
            registry.create("INVALID", "Bad Tenant")


class TestTenantRegistryList:
    @patch("dazzle.tenant.registry.psycopg")
    def test_list_tenants(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchall.return_value = [
            {
                "id": "uuid-1",
                "slug": "cyfuture",
                "display_name": "CyFuture UK",
                "schema_name": "tenant_cyfuture",
                "status": "active",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
            },
        ]
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        tenants = registry.list()

        assert len(tenants) == 1
        assert tenants[0].slug == "cyfuture"


class TestTenantRegistryGet:
    @patch("dazzle.tenant.registry.psycopg")
    def test_get_existing_tenant(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {
            "id": "uuid-1",
            "slug": "acme",
            "display_name": "Acme Corp",
            "schema_name": "tenant_acme",
            "status": "active",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        record = registry.get("acme")

        assert record is not None
        assert record.slug == "acme"
        assert record.display_name == "Acme Corp"

    @patch("dazzle.tenant.registry.psycopg")
    def test_get_missing_tenant_returns_none(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = None
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        record = registry.get("nonexistent")

        assert record is None


class TestTenantRegistryUpdateStatus:
    @patch("dazzle.tenant.registry.psycopg")
    def test_update_status(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {
            "id": "uuid-1",
            "slug": "cyfuture",
            "display_name": "CyFuture UK",
            "schema_name": "tenant_cyfuture",
            "status": "suspended",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-02",
        }
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        record = registry.update_status("cyfuture", "suspended")

        assert record.status == "suspended"
        assert mock_cursor.execute.called

    @patch("dazzle.tenant.registry.psycopg")
    def test_update_status_raises_for_missing_tenant(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = None
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        with pytest.raises(ValueError, match="not found"):
            registry.update_status("ghost", "active")


class TestTenantRegistryEnsureTable:
    @patch("dazzle.tenant.registry.psycopg")
    def test_ensure_table(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        registry.ensure_table()

        assert mock_cursor.execute.called
        mock_conn.commit.assert_called_once()
