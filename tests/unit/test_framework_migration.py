"""Tests for framework entity column sync (#712)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dazzle_back.runtime.migrations import (
    ColumnInfo,
    _field_to_pg_ddl,
    ensure_framework_entity_columns,
)


def _make_field(name: str, kind: str, max_length: int | None = None, default: str | None = None):
    """Build a minimal mock FieldSpec."""
    field = MagicMock()
    field.name = name
    field.type = MagicMock()
    field.type.kind = kind
    field.type.max_length = max_length
    field.default = default
    return field


def _make_entity(name: str, domain: str, fields: list):
    """Build a minimal mock EntitySpec."""
    entity = MagicMock()
    entity.name = name
    entity.domain = domain
    entity.fields = fields
    return entity


class TestFieldToPgDdl:
    def test_uuid(self):
        assert _field_to_pg_ddl(_make_field("id", "uuid")) == "UUID"

    def test_str_with_length(self):
        assert _field_to_pg_ddl(_make_field("name", "str", max_length=200)) == "VARCHAR(200)"

    def test_str_without_length(self):
        assert _field_to_pg_ddl(_make_field("name", "str")) == "VARCHAR"

    def test_text(self):
        assert _field_to_pg_ddl(_make_field("desc", "text")) == "TEXT"

    def test_bool(self):
        assert _field_to_pg_ddl(_make_field("active", "bool")) == "BOOLEAN"

    def test_datetime(self):
        assert _field_to_pg_ddl(_make_field("ts", "datetime")) == "TIMESTAMPTZ"

    def test_float(self):
        assert _field_to_pg_ddl(_make_field("val", "float")) == "DOUBLE PRECISION"

    def test_enum_maps_to_text(self):
        assert _field_to_pg_ddl(_make_field("status", "enum")) == "TEXT"

    def test_unknown_defaults_to_text(self):
        assert _field_to_pg_ddl(_make_field("x", "unknown_kind")) == "TEXT"


class TestEnsureFrameworkEntityColumns:
    def test_skips_non_framework_entities(self):
        """Only entities with domain='platform' or name in (FeedbackReport, AIJob) are synced."""
        user_entity = _make_entity("Task", "app", [_make_field("id", "uuid")])
        db = MagicMock()
        ensure_framework_entity_columns(db, [user_entity])
        db.connection.assert_not_called()

    def test_adds_missing_column(self):
        """A column present in IR but not in DB gets ALTER TABLE ADD COLUMN."""
        entity = _make_entity(
            "FeedbackReport",
            "platform",
            [
                _make_field("id", "uuid"),
                _make_field("idempotency_key", "str", max_length=36),
            ],
        )
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        db = MagicMock()
        db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        db.connection.return_value.__exit__ = MagicMock(return_value=False)

        # Simulate: table exists with only 'id' column
        with patch(
            "dazzle_back.runtime.migrations.get_table_schema",
            return_value=[
                ColumnInfo(name="id", type="UUID", not_null=True, default=None, is_pk=True)
            ],
        ):
            ensure_framework_entity_columns(db, [entity])

        # Should have executed ALTER TABLE for idempotency_key
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        alter_calls = [c for c in calls if "ADD COLUMN" in c]
        assert len(alter_calls) == 1
        assert "idempotency_key" in alter_calls[0]
        assert "VARCHAR(36)" in alter_calls[0]

    def test_skips_existing_columns(self):
        """Columns already in the DB are not ALTER'd."""
        entity = _make_entity(
            "FeedbackReport",
            "platform",
            [
                _make_field("id", "uuid"),
                _make_field("status", "enum"),
            ],
        )
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        db = MagicMock()
        db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        db.connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "dazzle_back.runtime.migrations.get_table_schema",
            return_value=[
                ColumnInfo(name="id", type="UUID", not_null=True, default=None, is_pk=True),
                ColumnInfo(name="status", type="TEXT", not_null=False, default=None, is_pk=False),
            ],
        ):
            ensure_framework_entity_columns(db, [entity])

        # No ALTER TABLE calls — all columns exist
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        alter_calls = [c for c in calls if "ADD COLUMN" in c]
        assert len(alter_calls) == 0

    def test_handles_table_not_yet_created(self):
        """If table doesn't exist yet (empty schema), skip — create_all handles it."""
        entity = _make_entity(
            "SystemHealth",
            "platform",
            [
                _make_field("id", "uuid"),
            ],
        )
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        db = MagicMock()
        db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        db.connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch("dazzle_back.runtime.migrations.get_table_schema", return_value=[]):
            ensure_framework_entity_columns(db, [entity])

        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        alter_calls = [c for c in calls if "ADD COLUMN" in c]
        assert len(alter_calls) == 0

    def test_default_now(self):
        """datetime fields with default='now' get DEFAULT now()."""
        entity = _make_entity(
            "AIJob",
            "platform",
            [
                _make_field("id", "uuid"),
                _make_field("created_at", "datetime", default="now"),
            ],
        )
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        db = MagicMock()
        db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        db.connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "dazzle_back.runtime.migrations.get_table_schema",
            return_value=[
                ColumnInfo(name="id", type="UUID", not_null=True, default=None, is_pk=True)
            ],
        ):
            ensure_framework_entity_columns(db, [entity])

        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        alter_calls = [c for c in calls if "ADD COLUMN" in c]
        assert len(alter_calls) == 1
        assert "DEFAULT now()" in alter_calls[0]
