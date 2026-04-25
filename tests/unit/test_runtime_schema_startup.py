"""Tests for runtime startup schema creation boundaries."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from dazzle.core import ir
from dazzle_back.runtime.migrations import MigrationError, verify_dazzle_params_table
from dazzle_back.runtime.server import DazzleBackendApp, ServerConfig


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
    def test_development_startup_keeps_create_all_convenience(self) -> None:
        builder = _make_builder()
        engine = MagicMock()

        with (
            patch.dict(os.environ, {"DAZZLE_ENV": "development"}, clear=True),
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
            patch("dazzle_back.runtime.migrations.ensure_dazzle_params_table") as ensure_params,
            patch("dazzle_back.runtime.migrations.verify_dazzle_params_table") as verify_params,
            patch("sqlalchemy.create_engine", return_value=engine) as create_engine,
        ):
            builder._setup_database()

        create_engine.assert_called_once()
        engine.dispose.assert_called_once()
        ensure_params.assert_called_once()
        verify_params.assert_not_called()

    def test_production_startup_leaves_schema_to_alembic(self) -> None:
        builder = _make_builder()

        with (
            patch.dict(os.environ, {"DAZZLE_ENV": "production"}, clear=True),
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
            patch("dazzle_back.runtime.migrations.ensure_dazzle_params_table") as ensure_params,
            patch("dazzle_back.runtime.migrations.verify_dazzle_params_table") as verify_params,
            patch("sqlalchemy.create_engine") as create_engine,
        ):
            builder._setup_database()

        create_engine.assert_not_called()
        ensure_params.assert_not_called()
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
    """The framework ships an Alembic baseline that creates `_dazzle_params`,
    so production startups (which call `verify_dazzle_params_table` instead of
    `ensure_dazzle_params_table`) succeed after `dazzle db upgrade`.

    The hint in `verify_dazzle_params_table`'s MigrationError points at this
    migration — it's load-bearing and must not be deleted/renamed without
    coordinated changes in `migrations.py`.
    """

    def test_baseline_migration_module_loads(self) -> None:
        """Migration module imports cleanly and exports the expected shape."""
        import importlib

        mod = importlib.import_module("dazzle_back.alembic.versions.0001_framework_baseline")
        assert mod.revision == "0001_framework_baseline"
        assert mod.down_revision is None  # this is the root revision
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)

    def test_baseline_migration_creates_dazzle_params(self) -> None:
        """upgrade() emits CREATE TABLE for _dazzle_params with the columns
        the runtime expects. Mirrors `ensure_dazzle_params_table()` so dev
        and production land on the same schema."""
        import importlib

        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        mod = importlib.import_module("dazzle_back.alembic.versions.0001_framework_baseline")

        # Use sqlite as a structural-validity sandbox — only verifies the
        # migration module produces well-formed Alembic ops. PostgreSQL-only
        # behaviour (JSONB, TIMESTAMPTZ default now()) is exercised by the
        # real migration in any real db env (and by ensure_dazzle_params_table
        # already, in dev).
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)

            # Patch the module-level `op` reference so upgrade() uses our
            # bound Operations instance instead of the global Alembic proxy
            # (which only resolves inside an `alembic` command run).
            with patch.object(mod, "op", op):
                # JSONB doesn't exist on sqlite; substitute with a JSON-equivalent
                # for this structural test. The real migration runs against
                # PostgreSQL and uses the genuine JSONB type.
                from sqlalchemy.dialects import postgresql

                with patch.object(postgresql, "JSONB", lambda: __import__("sqlalchemy").JSON()):
                    mod.upgrade()

            # Inspect the table
            from sqlalchemy import inspect

            inspector = inspect(engine)
            assert "_dazzle_params" in inspector.get_table_names()
            cols = {c["name"] for c in inspector.get_columns("_dazzle_params")}
            assert cols == {
                "key",
                "scope",
                "scope_id",
                "value_json",
                "updated_by",
                "updated_at",
            }
            pk = inspector.get_pk_constraint("_dazzle_params")
            assert pk["constrained_columns"] == ["key", "scope", "scope_id"]
