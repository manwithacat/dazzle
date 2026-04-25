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
