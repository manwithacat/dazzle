"""#1217 Phase 3e.iii — Alembic revision 0003 registers assert_subtype_kind.

Pure module-import + behaviour-shape test. Does not run Alembic against a
live DB — that's the responsibility of the dazzle db upgrade path.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch


def test_revision_0003_module_loads() -> None:
    mod = importlib.import_module("dazzle.http.alembic.versions.0003_subtype_kind_function")
    assert mod.revision == "0003_subtype_kind_function"
    assert mod.down_revision == "0002_drop_dazzle_migrations"
    assert mod.branch_labels is None
    assert mod.depends_on is None


def test_upgrade_calls_op_execute_with_function_sql() -> None:
    from dazzle.http.runtime.triggers import build_assert_subtype_kind_function

    mod = importlib.import_module("dazzle.http.alembic.versions.0003_subtype_kind_function")
    with patch.object(mod.op, "execute") as mock_execute:
        mod.upgrade()
        mock_execute.assert_called_once_with(build_assert_subtype_kind_function())


def test_downgrade_drops_function_with_cascade() -> None:
    mod = importlib.import_module("dazzle.http.alembic.versions.0003_subtype_kind_function")
    with patch.object(mod.op, "execute") as mock_execute:
        mod.downgrade()
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0][0]
        assert "DROP FUNCTION" in call_args
        assert "assert_subtype_kind" in call_args
        assert "CASCADE" in call_args
