"""TDD tests for dazzle.db.migration_engine.

Covers the pure ``build_plan(prev, curr) -> RevisionPlan`` core plus
the thin ``generate_revision(script_dir)`` wrapper (via a stub script_dir).

Snapshot shape follows schema_snapshot.py conventions:
  ColSnap  = {type, nullable, default, pk}
  TableSnap = {columns, fks, uniques, indexes}
  Snapshot  = dict[str, TableSnap]
"""

from __future__ import annotations

import ast
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from alembic.operations import ops as aops

from dazzle.db.migration_engine import RevisionPlan, build_plan, generate_revision

# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

_UUID_PK: dict[str, Any] = {"type": "uuid", "nullable": False, "default": None, "pk": True}
_TEXT_COL: dict[str, Any] = {"type": "text", "nullable": True, "default": None, "pk": False}
_BOOL_COL: dict[str, Any] = {
    "type": "boolean",
    "nullable": True,
    "default": "false",
    "pk": False,
}


def _table(columns: dict[str, Any]) -> dict[str, Any]:
    """Return a minimal TableSnap."""
    return {"columns": columns, "fks": {}, "uniques": [], "indexes": []}


# ---------------------------------------------------------------------------
# Snapshots for the core scenario: prev has no tables, curr adds "task"
# ---------------------------------------------------------------------------

PREV_EMPTY: dict[str, Any] = {}

CURR_WITH_TASK: dict[str, Any] = {
    "task": _table(
        {
            "id": _UUID_PK,
            "title": _TEXT_COL,
            "completed": _BOOL_COL,
        }
    )
}


# ---------------------------------------------------------------------------
# Helper: flatten ModifyTableOps sub-ops
# ---------------------------------------------------------------------------


def _flatten_ops(ops_list: list) -> list:
    result = []
    for o in ops_list:
        if isinstance(o, aops.ModifyTableOps):
            result.extend(o.ops)
        else:
            result.append(o)
    return result


# ---------------------------------------------------------------------------
# Test: build_plan returns a non-empty plan when curr adds a table
# ---------------------------------------------------------------------------


class TestBuildPlan:
    def test_non_empty_plan_when_table_added(self) -> None:
        plan = build_plan(PREV_EMPTY, CURR_WITH_TASK)

        assert isinstance(plan, RevisionPlan)
        assert not plan.is_empty

    def test_upgrade_ops_contains_create_table(self) -> None:
        plan = build_plan(PREV_EMPTY, CURR_WITH_TASK)

        flat = _flatten_ops(plan.upgrade_ops.ops)
        create_ops = [o for o in flat if isinstance(o, aops.CreateTableOp)]
        assert len(create_ops) == 1
        assert create_ops[0].table_name == "task"

    def test_downgrade_ops_contains_drop_table(self) -> None:
        plan = build_plan(PREV_EMPTY, CURR_WITH_TASK)

        flat = _flatten_ops(plan.downgrade_ops.ops)
        drop_ops = [o for o in flat if isinstance(o, aops.DropTableOp)]
        assert len(drop_ops) == 1
        assert drop_ops[0].table_name == "task"

    def test_snapshot_literal_round_trips_to_curr(self) -> None:
        plan = build_plan(PREV_EMPTY, CURR_WITH_TASK)

        # snapshot_literal is a pprint.pformat output — safe to parse as a literal.
        recovered = ast.literal_eval(plan.snapshot_literal)
        assert recovered == CURR_WITH_TASK

    def test_empty_plan_when_snapshots_identical(self) -> None:
        plan = build_plan(CURR_WITH_TASK, CURR_WITH_TASK)

        assert plan.is_empty
        assert plan.upgrade_ops.ops == []
        assert plan.downgrade_ops.ops == []

    def test_snapshot_literal_empty_when_no_tables(self) -> None:
        """Snapshot of the current state is always embedded (even if empty)."""
        plan = build_plan(PREV_EMPTY, PREV_EMPTY)

        assert ast.literal_eval(plan.snapshot_literal) == {}

    def test_upgrade_contains_all_columns(self) -> None:
        """CreateTableOp should carry the three columns."""
        plan = build_plan(PREV_EMPTY, CURR_WITH_TASK)

        flat = _flatten_ops(plan.upgrade_ops.ops)
        create_op = next(o for o in flat if isinstance(o, aops.CreateTableOp))
        col_names = {c.name for c in create_op.columns}
        assert col_names == {"id", "title", "completed"}


# ---------------------------------------------------------------------------
# Test: generate_revision wires build_plan via load_head_snapshot
# ---------------------------------------------------------------------------


class TestGenerateRevision:
    """generate_revision(script_dir) calls load_head_snapshot + project_current
    internally.  We test it by supplying a fake script_dir whose head module
    exposes PREV_EMPTY, and patching project_current to return CURR_WITH_TASK.
    """

    def _make_script_dir(self, snapshot: dict[str, Any]) -> MagicMock:
        """Return a mock ScriptDirectory whose head module has SCHEMA_SNAPSHOT."""
        head_module = SimpleNamespace(SCHEMA_SNAPSHOT=snapshot)
        head_script = MagicMock()
        head_script.module = head_module

        script_dir = MagicMock()
        script_dir.get_heads.return_value = ["abc123"]
        script_dir.get_revision.return_value = head_script
        return script_dir

    def test_generate_revision_non_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "dazzle.db.migration_engine.project_current",
            lambda: CURR_WITH_TASK,
        )
        script_dir = self._make_script_dir(PREV_EMPTY)
        plan = generate_revision(script_dir)

        assert isinstance(plan, RevisionPlan)
        assert not plan.is_empty

    def test_generate_revision_empty_when_no_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "dazzle.db.migration_engine.project_current",
            lambda: CURR_WITH_TASK,
        )
        script_dir = self._make_script_dir(CURR_WITH_TASK)
        plan = generate_revision(script_dir)

        assert plan.is_empty

    def test_generate_revision_upgrade_contains_create_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "dazzle.db.migration_engine.project_current",
            lambda: CURR_WITH_TASK,
        )
        script_dir = self._make_script_dir(PREV_EMPTY)
        plan = generate_revision(script_dir)

        flat = _flatten_ops(plan.upgrade_ops.ops)
        create_ops = [o for o in flat if isinstance(o, aops.CreateTableOp)]
        assert len(create_ops) == 1
        assert create_ops[0].table_name == "task"

    def test_generate_revision_snapshot_literal_round_trips(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "dazzle.db.migration_engine.project_current",
            lambda: CURR_WITH_TASK,
        )
        script_dir = self._make_script_dir(PREV_EMPTY)
        plan = generate_revision(script_dir)

        recovered = ast.literal_eval(plan.snapshot_literal)
        assert recovered == CURR_WITH_TASK
