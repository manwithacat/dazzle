"""Tests for the 0002_drop_dazzle_migrations Alembic migration (#1208).

Verifies the migration constants are set correctly, the upgrade/downgrade
callables exist, and that upgrade emits an idempotent `DROP TABLE IF EXISTS`
statement against `_dazzle_migrations`.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def migration_module():
    return importlib.import_module("dazzle.http.alembic.versions.0002_drop_dazzle_migrations")


def test_revision_constants(migration_module) -> None:
    assert migration_module.revision == "0002_drop_dazzle_migrations"
    assert migration_module.down_revision == "0001_framework_baseline"
    assert migration_module.branch_labels is None
    assert migration_module.depends_on is None


def test_upgrade_and_downgrade_are_callable(migration_module) -> None:
    assert callable(migration_module.upgrade)
    assert callable(migration_module.downgrade)


def test_upgrade_emits_drop_table_if_exists(migration_module) -> None:
    """upgrade() must call op.execute with an idempotent DROP TABLE IF EXISTS."""
    with patch.object(migration_module.op, "execute") as mock_execute:
        migration_module.upgrade()

    assert mock_execute.call_count == 1
    sql = mock_execute.call_args[0][0]
    assert "DROP TABLE IF EXISTS" in sql.upper()
    assert "_dazzle_migrations" in sql


def test_downgrade_is_noop(migration_module) -> None:
    """downgrade() is intentionally a no-op — the table has no writer."""
    with patch.object(migration_module.op, "execute") as mock_execute:
        result = migration_module.downgrade()

    assert result is None
    assert mock_execute.call_count == 0
