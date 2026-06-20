"""#1228 Phase 3c slice 3c.ii — atomic-flow runtime executor.

These tests pin the in-process semantics of ``execute_atomic_flow``:

1. Each create runs against a SHARED connection (single transaction).
2. ``input.X`` resolves to ``inputs[X]``; ``above.E.id`` resolves to
   the UUID generated for the earlier create of E.
3. The framework auto-generates ``id`` for every create.
4. On any create failure, the executor raises AtomicFlowError with
   ``failed_at`` set to the offending entity name, and the connection
   context's exception handler rolls back the transaction.
5. Successful execution returns ``{EntityName: uuid}`` for each create.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core import ir
from dazzle.http.runtime.atomic_flow_executor import (
    AtomicFlowError,
    execute_atomic_flow,
)


def _make_db(*, raise_on_execute: bool = False) -> MagicMock:
    """Mock DB with a context-managed connection + cursor."""
    cursor = MagicMock()
    if raise_on_execute:
        cursor.execute = MagicMock(side_effect=RuntimeError("INSERT failed"))
    else:
        cursor.execute = MagicMock()
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    db = MagicMock()
    db.placeholder = "%s"
    db.connection = MagicMock(return_value=ctx)
    db._mock_cursor = cursor
    db._mock_conn = conn
    db._mock_ctx = ctx
    return db


def _input(name: str, kind: ir.FieldTypeKind) -> ir.FlowInput:
    return ir.FlowInput(name=name, type=ir.FieldType(kind=kind), required=True)


def _flow_two_creates() -> ir.AtomicFlowSpec:
    """Person → Employment(person=above.Person.id)."""
    return ir.AtomicFlowSpec(
        name="onboard",
        label="Onboard",
        permit_execute=["admin"],
        inputs=[_input("legal_name", ir.FieldTypeKind.STR)],
        steps=[
            ir.FlowCreate(
                entity="Person",
                assignments={
                    "legal_name": ir.FlowFieldValue(
                        kind=ir.FlowFieldValueKind.INPUT_REF,
                        input_name="legal_name",
                    ),
                },
            ),
            ir.FlowCreate(
                entity="Employment",
                assignments={
                    "person": ir.FlowFieldValue(
                        kind=ir.FlowFieldValueKind.ABOVE_REF,
                        above_entity="Person",
                        above_field="id",
                    ),
                },
            ),
        ],
    )


class TestSingleTransaction:
    def test_all_creates_share_one_connection(self) -> None:
        db = _make_db()
        execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        # One connection lease for the whole flow.
        assert db.connection.call_count == 1

    def test_one_cursor_used_for_both_creates(self) -> None:
        db = _make_db()
        execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        # Cursor.execute called once per create.
        assert db._mock_cursor.execute.call_count == 2


class TestReferenceResolution:
    def test_input_ref_resolves_to_inputs_dict(self) -> None:
        db = _make_db()
        execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        first_sql, first_params = db._mock_cursor.execute.call_args_list[0].args
        assert "Person" in first_sql
        assert "Alice" in first_params

    def test_above_ref_resolves_to_prior_uuid(self) -> None:
        db = _make_db()
        result = execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        # Second create (Employment) should have used Person's id as a
        # parameter — find it in the second call's params.
        second_sql, second_params = db._mock_cursor.execute.call_args_list[1].args
        assert "Employment" in second_sql
        assert result["Person"] in second_params

    def test_auto_generates_id_per_create(self) -> None:
        db = _make_db()
        result = execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        assert set(result.keys()) == {"Person", "Employment"}
        # Both ids are UUIDs and distinct.
        from uuid import UUID

        assert isinstance(result["Person"], UUID)
        assert isinstance(result["Employment"], UUID)
        assert result["Person"] != result["Employment"]

    def test_literal_value_passes_through(self) -> None:
        flow = ir.AtomicFlowSpec(
            name="x",
            label="X",
            permit_execute=["admin"],
            inputs=[],
            steps=[
                ir.FlowCreate(
                    entity="Person",
                    assignments={
                        "legal_name": ir.FlowFieldValue(
                            kind=ir.FlowFieldValueKind.LITERAL,
                            literal="hardcoded",
                        )
                    },
                )
            ],
        )
        db = _make_db()
        execute_atomic_flow(flow, {}, db)
        _, params = db._mock_cursor.execute.call_args.args
        assert "hardcoded" in params


class TestFailureSemantics:
    def test_raises_atomic_flow_error_on_db_failure(self) -> None:
        db = _make_db(raise_on_execute=True)
        with pytest.raises(AtomicFlowError) as exc_info:
            execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        # First create fails, so failed_at = "Person"
        assert exc_info.value.failed_at == "Person"

    def test_failure_propagates_through_connection_exit(self) -> None:
        """Connection.__exit__ sees the exception so the pool can rollback."""
        db = _make_db(raise_on_execute=True)
        with pytest.raises(AtomicFlowError):
            execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        # __exit__ was called with non-None exc_type (the pool sees the error
        # and rolls back the transaction).
        exit_call = db._mock_ctx.__exit__.call_args
        # exit_call.args = (exc_type, exc_value, traceback) — first non-None
        # means an exception bubbled up.
        assert exit_call.args[0] is not None

    def test_missing_input_raises_atomic_flow_error(self) -> None:
        db = _make_db()
        with pytest.raises(AtomicFlowError) as exc_info:
            execute_atomic_flow(_flow_two_creates(), {}, db)  # no legal_name
        assert exc_info.value.failed_at == "Person"
        assert "unresolved reference" in str(exc_info.value)


class TestReturnValue:
    def test_returns_entity_name_to_uuid_map(self) -> None:
        db = _make_db()
        result = execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        assert "Person" in result and "Employment" in result

    def test_empty_creates_returns_empty_map(self) -> None:
        flow = ir.AtomicFlowSpec(
            name="noop",
            label="Noop",
            permit_execute=["admin"],
            inputs=[],
            steps=[],
        )
        db = _make_db()
        result = execute_atomic_flow(flow, {}, db)
        assert result == {}
        # No cursor.execute calls.
        assert db._mock_cursor.execute.call_count == 0


class TestUpdateStepExecution:
    """#1313: `update` steps now execute — resolve the target row, enforce
    scope: update: (source+destination) in-transaction, then UPDATE. (Real-PG
    + scope behaviour is covered in tests/integration/test_scope_runtime_pg.py;
    these unit tests pin the SQL shape + the enforcement hand-off with mocks.)"""

    def _flow_with_update(self) -> ir.AtomicFlowSpec:
        return ir.AtomicFlowSpec(
            name="reassign",
            label="Reassign",
            permit_execute=["admin"],
            inputs=[_input("pid", ir.FieldTypeKind.UUID)],
            steps=[
                ir.FlowUpdate(
                    entity="Person",
                    target=ir.FlowFieldValue(
                        kind=ir.FlowFieldValueKind.INPUT_REF, input_name="pid"
                    ),
                    assignments={
                        "legal_name": ir.FlowFieldValue(
                            kind=ir.FlowFieldValueKind.LITERAL, literal="x"
                        )
                    },
                ),
            ],
        )

    def test_update_step_reads_then_issues_update(self) -> None:
        db = _make_db()
        # The in-txn source read returns an existing row.
        db._mock_cursor.fetchone = MagicMock(return_value={"id": "p-1", "legal_name": "old"})
        execute_atomic_flow(self._flow_with_update(), {"pid": "p-1"}, db)  # no enforcement
        calls = [c.args[0] for c in db._mock_cursor.execute.call_args_list]
        # First the source SELECT, then the UPDATE.
        assert any(s.startswith("SELECT *") and '"Person"' in s for s in calls)
        upd = [s for s in calls if s.startswith("UPDATE")]
        assert upd and '"Person"' in upd[0] and '"legal_name" = %s' in upd[0]

    def test_update_target_not_found_errors(self) -> None:
        db = _make_db()
        db._mock_cursor.fetchone = MagicMock(return_value=None)  # row absent
        with pytest.raises(AtomicFlowError, match="not found"):
            execute_atomic_flow(self._flow_with_update(), {"pid": "missing"}, db)

    def test_update_target_not_found_is_idor_404_when_enforcing(self) -> None:
        """With scope enforced, a missing target is an IDOR-shaped 404 (not a
        distinguishable 400) — indistinguishable from a scope-denied row."""
        from types import SimpleNamespace

        from fastapi import HTTPException

        db = _make_db()
        db._mock_cursor.fetchone = MagicMock(return_value=None)  # row absent
        with pytest.raises(HTTPException) as exc:
            execute_atomic_flow(
                self._flow_with_update(),
                {"pid": "missing"},
                db,
                auth_context=SimpleNamespace(user=SimpleNamespace(id="u-1"), roles=["admin"]),
                access_specs={"Person": object()},
            )
        assert exc.value.status_code == 404

    def test_update_routed_through_scope_when_enforcing(self, monkeypatch: Any) -> None:
        import dazzle.http.runtime.scope_filters as sf

        seen: list[tuple[str, bool]] = []

        def _fake_update_enforce(**kwargs: Any) -> None:
            seen.append((kwargs["entity_name"], kwargs["also_check_source"]))

        monkeypatch.setattr(sf, "_enforce_update_scope", _fake_update_enforce)
        db = _make_db()
        db._mock_cursor.fetchone = MagicMock(return_value={"id": "p-1", "legal_name": "old"})
        from types import SimpleNamespace

        execute_atomic_flow(
            self._flow_with_update(),
            {"pid": "p-1"},
            db,
            auth_context=SimpleNamespace(user=SimpleNamespace(id="u-1"), roles=["admin"]),
            access_specs={"Person": object()},
        )
        # Update routed through scope: update: with source-check enabled.
        assert seen == [("Person", True)]


class TestPerStepScopeEnforcement:
    """#1313 slice 1b: each create step is routed through scope: create:
    enforcement when auth_context + access_specs are supplied. (Real-Postgres
    behaviour is covered end-to-end in
    tests/integration/test_scope_runtime_pg.py; these unit tests pin the
    wiring + the fail-closed propagation with the CRUD enforcer mocked.)"""

    def _principal(self) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(user=SimpleNamespace(id="u-1"), roles=["admin"])

    def test_each_create_is_routed_through_scope(self, monkeypatch: Any) -> None:
        import dazzle.http.runtime.scope_filters as sf

        seen: list[str] = []

        def _fake_enforce(**kwargs: Any) -> None:
            seen.append(kwargs["entity_name"])

        monkeypatch.setattr(sf, "_enforce_create_scope", _fake_enforce)
        db = _make_db()
        execute_atomic_flow(
            _flow_two_creates(),
            {"legal_name": "Alice"},
            db,
            auth_context=self._principal(),
            access_specs={"Person": object(), "Employment": object()},
        )
        # Enforcement invoked once per create step, in declaration order.
        assert seen == ["Person", "Employment"]

    def test_scope_denial_rolls_back_before_insert(self, monkeypatch: Any) -> None:
        from fastapi import HTTPException

        import dazzle.http.runtime.scope_filters as sf

        def _deny(**kwargs: Any) -> None:
            raise HTTPException(status_code=403, detail="scope_create_denied")

        monkeypatch.setattr(sf, "_enforce_create_scope", _deny)
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            execute_atomic_flow(
                _flow_two_creates(),
                {"legal_name": "Alice"},
                db,
                auth_context=self._principal(),
                access_specs={"Person": object()},
            )
        assert exc.value.status_code == 403
        # Denial fires BEFORE the INSERT — nothing is written (fail-closed).
        assert db._mock_cursor.execute.call_count == 0

    def test_no_enforcement_without_principal_or_specs(self, monkeypatch: Any) -> None:
        """Legacy/test wiring (no auth_context or access_specs) runs unguarded."""
        import dazzle.http.runtime.scope_filters as sf

        def _boom(**kwargs: Any) -> None:
            raise AssertionError("enforcement must not run without auth_context+access_specs")

        monkeypatch.setattr(sf, "_enforce_create_scope", _boom)
        db = _make_db()
        execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)  # no kwargs
        assert db._mock_cursor.execute.call_count == 2  # both creates ran


# ---------------------------------------------------------------------------
# #1316 — scope-parent FOR SHARE lock target collection (ADR-0029 invariant 4)
# ---------------------------------------------------------------------------


class TestCollectPathCheckParentLocks:
    """`_collect_pathcheck_parent_locks` extracts the directly-referenced
    FK-path scope-parent rows to share-lock before the scope probe."""

    def _fk_graph(self) -> Any:
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.core.ir.fk_graph import FKGraph

        appspec = load_project_appspec(Path("fixtures/scope_runtime"))
        return FKGraph.from_entities(appspec.domain.entities)

    def _create_rule(self, op: str = "create") -> Any:
        from types import SimpleNamespace

        from dazzle.core.ir.predicates import CompOp, PathCheck, ValueRef

        # Enrolment's depth-2 FK-path create-scope: teaching_group.department.
        pred = PathCheck(
            path=["teaching_group", "department"],
            op=CompOp.EQ,
            value=ValueRef(user_attr="department"),
        )
        return SimpleNamespace(operation=SimpleNamespace(value=op), personas=["*"], predicate=pred)

    def test_depth2_create_collects_root_target(self) -> None:
        from types import SimpleNamespace

        from dazzle.http.runtime.atomic_flow_executor import _collect_pathcheck_parent_locks

        spec = SimpleNamespace(scopes=[self._create_rule("create")])
        group_id = "11111111-1111-1111-1111-111111111111"
        locks = _collect_pathcheck_parent_locks(
            entity="Enrolment",
            payload={"teaching_group": group_id},
            access_specs={"Enrolment": spec},
            fk_graph=self._fk_graph(),
            operations=("create",),
        )
        assert len(locks) == 1
        (table, pks) = next(iter(locks.items()))
        assert "TeachingGroup" in table  # root FK target table (schema-qualified+quoted)
        assert pks == {group_id}

    def test_operation_filter_excludes_other_ops(self) -> None:
        from types import SimpleNamespace

        from dazzle.http.runtime.atomic_flow_executor import _collect_pathcheck_parent_locks

        spec = SimpleNamespace(scopes=[self._create_rule("create")])
        # Asking for update locks must not pick up the create rule.
        locks = _collect_pathcheck_parent_locks(
            entity="Enrolment",
            payload={"teaching_group": "11111111-1111-1111-1111-111111111111"},
            access_specs={"Enrolment": spec},
            fk_graph=self._fk_graph(),
            operations=("update",),
        )
        assert locks == {}

    def test_update_locks_unchanged_fk_from_merged_payload(self) -> None:
        # #1316 review finding: an update that does NOT change the scope FK still
        # authorizes against the existing parent (the probe binds the merged
        # would-be-final row), so the lock must be collected from the merged
        # payload — keyed off the existing DB column value — not just new_values.
        from types import SimpleNamespace

        from dazzle.http.runtime.atomic_flow_executor import _collect_pathcheck_parent_locks

        spec = SimpleNamespace(scopes=[self._create_rule("update")])
        existing_fk = "22222222-2222-2222-2222-222222222222"
        # merged = {**existing (DB column key), **new_values} with FK unchanged.
        merged = {"teaching_group_id": existing_fk, "label": "renamed"}
        locks = _collect_pathcheck_parent_locks(
            entity="Enrolment",
            payload=merged,
            access_specs={"Enrolment": spec},
            fk_graph=self._fk_graph(),
            operations=("update",),
        )
        assert len(locks) == 1
        (table, pks) = next(iter(locks.items()))
        assert "TeachingGroup" in table
        assert pks == {existing_fk}

    def test_missing_payload_fk_collects_nothing(self) -> None:
        from types import SimpleNamespace

        from dazzle.http.runtime.atomic_flow_executor import _collect_pathcheck_parent_locks

        spec = SimpleNamespace(scopes=[self._create_rule("create")])
        # Payload omits the FK → nothing to lock (the probe fail-closes anyway).
        locks = _collect_pathcheck_parent_locks(
            entity="Enrolment",
            payload={"label": "x"},
            access_specs={"Enrolment": spec},
            fk_graph=self._fk_graph(),
            operations=("create",),
        )
        assert locks == {}

    def test_no_access_spec_returns_empty(self) -> None:
        from dazzle.http.runtime.atomic_flow_executor import _collect_pathcheck_parent_locks

        assert (
            _collect_pathcheck_parent_locks(
                entity="Enrolment",
                payload={"teaching_group": "x"},
                access_specs=None,
                fk_graph=None,
                operations=("create",),
            )
            == {}
        )


# ---------------------------------------------------------------------------
# #1317 — strict in-transaction audit writer
# ---------------------------------------------------------------------------


class TestStrictAtomicAuditWrite:
    """`_write_strict_atomic_audit` pins the row shape, incl. the null-principal
    path (an unauthenticated strict flow still records, with null user fields —
    the #1317 review fix so opting into strict never silently drops ALL audit)."""

    def test_write_with_null_principal_uses_null_user_fields(self) -> None:
        from unittest.mock import MagicMock

        from dazzle.http.runtime.atomic_flow_executor import _write_strict_atomic_audit

        cur = MagicMock()
        _write_strict_atomic_audit(
            cur,
            "enrol_student_strict",
            None,  # no auth_context (unauthenticated/legacy wiring)
            [{"entity": "Enrolment", "operation": "create", "entity_id": "row-1"}],
        )
        assert cur.execute.call_count == 1
        params = cur.execute.call_args[0][1]
        # (id, timestamp, flow_name, user_id, user_email, user_roles, operation,
        #  entity_name, entity_id, decision, matched_policy)
        assert params[2] == "enrol_student_strict"
        assert params[3] is None  # user_id
        assert params[4] is None  # user_email
        assert params[5] == "[]"  # user_roles (json) — no roles, not dropped
        assert params[6] == "create"
        assert params[7] == "Enrolment"
        assert params[8] == "row-1"
        assert params[9] == "allow"
        assert params[10] == "atomic:enrol_student_strict"

    def test_write_one_row_per_committed_step(self) -> None:
        from unittest.mock import MagicMock

        from dazzle.http.runtime.atomic_flow_executor import _write_strict_atomic_audit

        cur = MagicMock()
        _write_strict_atomic_audit(
            cur,
            "f",
            None,
            [
                {"entity": "A", "operation": "create", "entity_id": "1"},
                {"entity": "B", "operation": "update", "entity_id": "2"},
            ],
        )
        assert cur.execute.call_count == 2


class TestExecuteOnConn:
    """#1319 / ADR-0032 Slice A — `execute_atomic_flow_on_conn` runs on a
    caller-provided connection (so a transition can share its transaction)."""

    def test_runs_on_provided_conn_without_opening_one(self) -> None:
        from dazzle.http.runtime.atomic_flow_executor import execute_atomic_flow_on_conn

        cursor = MagicMock()
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)

        result = execute_atomic_flow_on_conn(
            _flow_two_creates(), {"legal_name": "Alice"}, conn, "%s"
        )
        # One INSERT per create, on the PROVIDED cursor.
        assert cursor.execute.call_count == 2
        assert set(result.keys()) == {"Person", "Employment"}

    def test_wrapper_delegates_to_on_conn(self) -> None:
        # execute_atomic_flow opens a connection then delegates; the steps run
        # on that connection's cursor.
        db = _make_db()
        execute_atomic_flow(_flow_two_creates(), {"legal_name": "Alice"}, db)
        assert db.connection.call_count == 1
        assert db._mock_cursor.execute.call_count == 2
