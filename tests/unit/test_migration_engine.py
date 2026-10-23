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

from dazzle.db.migration_engine import (
    RevisionPlan,
    WholeSchemaRevisionRefused,
    build_plan,
    generate_baseline_plan,
    generate_revision,
    guard_whole_schema_revision,
)

pytestmark = pytest.mark.migration_engine

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

    def test_generate_revision_self_loads_rename_hints(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The real env.py path calls generate_revision(script_dir) with NO appspec.

        This proves the self-load activates rename resolution end-to-end: with a
        ``renamed_from`` annotation on a field, a column rename must resolve to a
        ``RenameColumn`` op (preserving data) rather than drop+add (data loss).

        We monkeypatch:
          * ``project_current`` → the post-rename schema (column ``name``)
          * ``load_head_snapshot`` (via the fake script_dir) → the pre-rename
            schema (column ``title``)
          * the appspec self-loader → an AppSpec whose ``task.name`` field
            declares ``renamed_from = "title"``
        and then call ``generate_revision(script_dir)`` with NO appspec arg.
        """
        prev = {"task": _table({"id": _UUID_PK, "title": _TEXT_COL})}
        curr = {"task": _table({"id": _UUID_PK, "name": _TEXT_COL})}

        monkeypatch.setattr(
            "dazzle.db.migration_engine.project_current",
            lambda: curr,
        )

        # AppSpec stub: appspec.domain.entities[*].{name, renamed_from, fields[*]}
        # with FieldSpec.{name, renamed_from} — exactly what extract_rename_hints reads.
        name_field = SimpleNamespace(name="name", renamed_from="title")
        id_field = SimpleNamespace(name="id", renamed_from=None)
        task_entity = SimpleNamespace(name="task", renamed_from=None, fields=[id_field, name_field])
        fake_appspec = SimpleNamespace(domain=SimpleNamespace(entities=[task_entity]))

        # Self-load returns the hint-bearing appspec (no explicit appspec arg passed).
        monkeypatch.setattr(
            "dazzle.db.migration_engine._load_project_appspec_for_hints",
            lambda: fake_appspec,
        )

        script_dir = self._make_script_dir(prev)
        plan = generate_revision(script_dir)  # NO appspec arg — the real env.py path

        flat = _flatten_ops(plan.upgrade_ops.ops)
        rename_ops = [o for o in flat if isinstance(o, aops.AlterColumnOp) and o.modify_name]
        # AlterColumnOp with a modify_name is how Alembic renders a column rename.
        assert any(o.column_name == "title" and o.modify_name == "name" for o in rename_ops), (
            f"expected a RenameColumn title→name, got ops: {flat}"
        )

        # And it must NOT be a drop+add (which would lose the column's data).
        drop_ops = [o for o in flat if isinstance(o, aops.DropColumnOp)]
        add_ops = [o for o in flat if isinstance(o, aops.AddColumnOp)]
        assert not drop_ops, f"unexpected DropColumnOp (data loss): {drop_ops}"
        assert not add_ops, f"unexpected AddColumnOp (data loss): {add_ops}"


# ---------------------------------------------------------------------------
# Test: generate_baseline_plan — full create from empty prev, framework excluded
# ---------------------------------------------------------------------------


class TestGenerateBaselinePlan:
    """A baseline diffs against an empty prev and (a) creates only project tables
    (framework tables excluded via table_filter), with FKs as separate ops, while
    (b) embedding the *full* snapshot so the next db revision diffs full-vs-full."""

    # A project table with a self-referential FK + a framework-owned table.
    _CURR: dict[str, Any] = {
        "Project": {
            "columns": {"id": _UUID_PK, "parent": _TEXT_COL},
            "fks": {"parent": "Project"},  # self-ref
            "uniques": [],
            "indexes": [],
        },
        "users": _table({"id": _UUID_PK}),  # framework-owned
    }

    def _patch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _project_current(table_filter: Any = None) -> dict[str, Any]:
            if table_filter is None:
                return self._CURR
            return {k: v for k, v in self._CURR.items() if table_filter(k)}

        monkeypatch.setattr("dazzle.db.migration_engine.project_current", _project_current)

    def test_creates_only_project_tables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch)
        plan = generate_baseline_plan(table_filter=lambda n: n != "users")
        created = {
            o.table_name
            for o in _flatten_ops(plan.upgrade_ops.ops)
            if isinstance(o, aops.CreateTableOp)
        }
        assert created == {"Project"}  # framework "users" excluded

    def test_self_ref_fk_emitted_as_separate_op(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch)
        plan = generate_baseline_plan(table_filter=lambda n: n != "users")
        fk_ops = [
            o for o in _flatten_ops(plan.upgrade_ops.ops) if isinstance(o, aops.CreateForeignKeyOp)
        ]
        assert len(fk_ops) == 1
        assert fk_ops[0].source_table == "Project"
        assert fk_ops[0].referent_table == "Project"

    def test_embedded_snapshot_includes_framework_tables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch(monkeypatch)
        plan = generate_baseline_plan(table_filter=lambda n: n != "users")
        recovered = ast.literal_eval(plan.snapshot_literal)
        # Full post-state — framework "users" present so the next revision cancels it.
        assert set(recovered.keys()) == {"Project", "users"}


# ---------------------------------------------------------------------------
# #1846: whole-schema guard — an empty previous snapshot against a populated DB
# ---------------------------------------------------------------------------


class TestWholeSchemaGuard:
    @pytest.mark.parametrize(
        ("prev", "existing"),
        [
            (CURR_WITH_TASK, ["task"]),  # normal: a snapshot exists
            (PREV_EMPTY, None),  # DB not inspected (offline) → guard off
            (PREV_EMPTY, []),  # genuinely fresh DB
            (PREV_EMPTY, ["users", "alembic_version"]),  # framework tables only
        ],
    )
    def test_allows(self, prev: dict[str, Any], existing: list[str] | None) -> None:
        guard_whole_schema_revision(prev, CURR_WITH_TASK, existing)

    def test_refuses_empty_prev_when_db_has_project_tables(self) -> None:
        with pytest.raises(WholeSchemaRevisionRefused, match=r"already has 1 of them \(task\)"):
            guard_whole_schema_revision(PREV_EMPTY, CURR_WITH_TASK, ["task", "users"])

    def test_generate_revision_refuses_before_rendering(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("dazzle.db.migration_engine.project_current", lambda: CURR_WITH_TASK)
        head = SimpleNamespace(module=SimpleNamespace(), down_revision=None, path=None)
        script_dir = MagicMock()
        script_dir.get_heads.return_value = ["h1"]
        script_dir.get_revision.return_value = head
        with pytest.raises(WholeSchemaRevisionRefused):
            generate_revision(script_dir, appspec=SimpleNamespace(), existing_tables=["task"])

    def test_generate_revision_carries_unsnapshotted_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hand-authored revision above the snapshot is surfaced as a note."""
        monkeypatch.setattr("dazzle.db.migration_engine.project_current", lambda: CURR_WITH_TASK)
        hand = SimpleNamespace(module=SimpleNamespace(), down_revision="snap1", path=None)
        snap = SimpleNamespace(
            module=SimpleNamespace(SCHEMA_SNAPSHOT=CURR_WITH_TASK), down_revision=None, path=None
        )
        script_dir = MagicMock()
        script_dir.get_heads.return_value = ["hand1"]
        script_dir.get_revision.side_effect = {"hand1": hand, "snap1": snap}.get
        monkeypatch.setattr(
            "dazzle.db.migration_engine._load_project_appspec_for_hints", lambda: None
        )

        plan = generate_revision(script_dir, existing_tables=["task"])
        assert plan.is_empty
        assert len(plan.notes) == 1 and "hand1" in plan.notes[0]


# ---------------------------------------------------------------------------
# #1851: framework-injected platform entities are project-lineage tables
# ---------------------------------------------------------------------------


_PLATFORM_DSL = """\
module p
app p "P":
  security_profile: standard

entity Task "Task":
  id: uuid pk
  title: str(200) required
"""


def test_platform_entities_are_in_the_project_snapshot(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Persisted platform entities (admin workspace) are projected like DSL entities.

    They are AppSpec entities, created by the project's own baseline revision
    (``db baseline``), not by the framework lineage and not in the framework
    table registry, so they belong in the project's ``SCHEMA_SNAPSHOT``; a
    revision diffed against a snapshot of the same DSL never re-creates them.
    Virtual platform entities have no table at all.
    """
    from dazzle.db.schema_snapshot import project_current
    from dazzle.db.virtual import VIRTUAL_ENTITY_NAMES
    from dazzle.http.alembic.framework_tables import is_framework_table

    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "p"\nversion = "0.1.0"\nroot = "p"\n', encoding="utf-8"
    )
    (tmp_path / "dsl").mkdir()
    (tmp_path / "dsl" / "app.dsl").write_text(_PLATFORM_DSL, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    snap = project_current()
    assert {"DeployHistory", "SessionInfo", "Task"} <= set(snap)
    assert not set(snap) & VIRTUAL_ENTITY_NAMES
    assert not any(is_framework_table(t) for t in ("DeployHistory", "SessionInfo"))

    # Adding one entity diffs to exactly one create_table: no platform table.
    grown = {**snap, "Widget": _table({"id": _UUID_PK})}
    plan = build_plan(snap, grown)
    created = [
        o.table_name
        for o in _flatten_ops(plan.upgrade_ops.ops)
        if isinstance(o, aops.CreateTableOp)
    ]
    assert created == ["Widget"]
