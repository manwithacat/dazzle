"""Tests for TenantRegistry — CRUD on public.tenants."""

from unittest.mock import MagicMock, patch

import pytest

from dazzle.tenant.registry import TenantRegistry


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


class TestTenantRegistryIsTest:
    @patch("dazzle.tenant.registry.psycopg")
    def test_create_defaults_is_test_false(self, mock_psycopg: MagicMock) -> None:
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
            "config": {},
            "is_test": False,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        record = registry.create("cyfuture", "CyFuture UK")

        assert record.is_test is False
        # The INSERT carries is_test as its fourth bind value.
        args, _ = mock_cursor.execute.call_args
        assert args[1] == ("cyfuture", "CyFuture UK", "tenant_cyfuture", False)

    @patch("dazzle.tenant.registry.psycopg")
    def test_create_is_test_true(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {
            "id": "uuid-2",
            "slug": "qa_run_1",
            "display_name": "QA run 1",
            "schema_name": "tenant_qa_run_1",
            "status": "active",
            "config": {},
            "is_test": True,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        # allow_reserved is required because qa_ is reserved (Task 1).
        record = registry.create("qa_run_1", "QA run 1", is_test=True, allow_reserved=True)

        assert record.is_test is True
        args, _ = mock_cursor.execute.call_args
        assert args[1] == ("qa_run_1", "QA run 1", "tenant_qa_run_1", True)

    @patch("dazzle.tenant.registry.psycopg")
    def test_row_to_record_tolerates_missing_is_test(self, mock_psycopg: MagicMock) -> None:
        # Defensive: a row read before the column existed must default False.
        from dazzle.tenant.registry import _row_to_record

        record = _row_to_record(
            {
                "id": "uuid-3",
                "slug": "legacy",
                "display_name": "Legacy",
                "schema_name": "tenant_legacy",
                "status": "active",
                "config": {},
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
            }
        )
        assert record.is_test is False


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
        # Three statements: CREATE TABLE + ALTER config + ALTER is_test (#1339).
        assert mock_cursor.execute.call_count == 3
        mock_conn.commit.assert_called_once()
