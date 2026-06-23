"""Tests for runtime startup schema creation boundaries."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from dazzle.core import ir
from dazzle.http.runtime.migrations import MigrationError, verify_dazzle_params_table
from dazzle.http.runtime.server import DazzleBackendApp, ServerConfig


def _make_appspec() -> ir.AppSpec:
    entity = ir.EntitySpec(
        name="Task",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
        ],
    )
    return ir.AppSpec(name="test_app", domain=ir.DomainSpec(entities=[entity]))


def _make_builder() -> DazzleBackendApp:
    builder = DazzleBackendApp(
        _make_appspec(),
        config=ServerConfig(database_url="postgresql://example/test"),
    )
    builder._create_app()
    builder._setup_models()
    return builder


class TestRuntimeSchemaStartup:
    def test_development_startup_calls_ensure_framework_schema(self) -> None:
        """Dev startup calls ensure_framework_schema (ADR-0044, Task 1 boot wiring)."""
        builder = _make_builder()
        engine = MagicMock()

        with (
            patch.dict(os.environ, {"DAZZLE_ENV": "development"}, clear=True),
            patch("dazzle.http.runtime.pg_backend.PostgresBackend"),
            patch("dazzle.http.runtime.framework_schema.ensure_framework_schema") as ensure_fw,
            patch("dazzle.http.runtime.migrations.verify_dazzle_params_table") as verify_params,
            patch("sqlalchemy.create_engine", return_value=engine) as create_engine,
        ):
            builder._setup_database()

        create_engine.assert_called_once()
        engine.dispose.assert_called_once()
        ensure_fw.assert_called_once()
        verify_params.assert_not_called()

    def test_production_startup_leaves_schema_to_alembic(self) -> None:
        builder = _make_builder()

        with (
            patch.dict(os.environ, {"DAZZLE_ENV": "production"}, clear=True),
            patch("dazzle.http.runtime.pg_backend.PostgresBackend"),
            patch("dazzle.http.runtime.framework_schema.ensure_framework_schema") as ensure_fw,
            patch("dazzle.http.runtime.migrations.verify_dazzle_params_table") as verify_params,
            patch("sqlalchemy.create_engine") as create_engine,
        ):
            builder._setup_database()

        create_engine.assert_not_called()
        ensure_fw.assert_not_called()
        verify_params.assert_called_once()


class TestDazzleParamsVerification:
    def test_verify_params_table_accepts_existing_table(self) -> None:
        db_manager = MagicMock()
        conn = db_manager.connection.return_value.__enter__.return_value
        conn.cursor.return_value.fetchone.return_value = {"exists": True}

        verify_dazzle_params_table(db_manager)

        conn.cursor.return_value.execute.assert_called_once()

    def test_verify_params_table_raises_when_missing(self) -> None:
        db_manager = MagicMock()
        conn = db_manager.connection.return_value.__enter__.return_value
        conn.cursor.return_value.fetchone.return_value = {"exists": False}

        with pytest.raises(MigrationError, match="_dazzle_params table is missing"):
            verify_dazzle_params_table(db_manager)


class TestFrameworkBaselineMigration:
    """The framework ships an Alembic squashed baseline (0019_process_runtime_tables,
    down_revision=None) that creates ALL in-scope framework tables, so production
    startups (which call ``verify_dazzle_params_table`` instead of
    ``ensure_dazzle_params_table``) succeed after ``dazzle db upgrade``.

    The baseline calls ``_ensure_framework_schema_ddl`` — the same DDL core
    as ``ensure_framework_schema`` — so baseline ≡ orchestrator by shared code.

    ADR-0044 / Task 2 of the framework-migration-baseline plan.
    """

    def test_baseline_migration_module_loads(self) -> None:
        """Migration module imports cleanly and exports the expected shape."""
        import importlib

        mod = importlib.import_module("dazzle.http.alembic.versions.0019_process_runtime_tables")
        assert mod.revision == "0019_process_runtime_tables"
        assert mod.down_revision is None  # chain root — no predecessor
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)

    def test_baseline_migration_exports_broad_framework_schema(self) -> None:
        """The baseline module documents the full in-scope framework table list
        (spot-checks key members) so a rename/split is caught early."""
        import importlib

        mod = importlib.import_module("dazzle.http.alembic.versions.0019_process_runtime_tables")
        doc = mod.__doc__ or ""
        # Core framework tables that must be declared in the baseline docstring.
        for table in (
            "_dazzle_params",
            "users",
            "sessions",
            "memberships",
            "organizations",
            "process_runs",
            "process_tasks",
            "_dazzle_audit_log",
            "_grants",
            "_dazzle_event_inbox",
            "_dazzle_event_outbox",
        ):
            assert table in doc, (
                f"Baseline docstring missing table {table!r} — update the "
                "In-scope tables list in 0019_process_runtime_tables.py"
            )
