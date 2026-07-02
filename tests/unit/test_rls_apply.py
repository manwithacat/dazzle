"""Unit tests for ``dazzle.db.rls_apply.apply_rls_policies`` (#1531).

The real-PG proof lives in ``tests/integration/test_rls_apply_and_drift_pg.py``;
these pin the connection-level contract with a fake psycopg conn:

* the live column types are introspected and fed into the DDL build as cast
  overrides (the #1531 fix — casts follow the PHYSICAL column, not the logical
  schema);
* the whole policy set applies inside ONE transaction (DROP-then-CREATE on an
  autocommit conn would otherwise leave a table's scope policy dropped when a
  later statement fails);
* the no-op cases (non-tenant / non-shared_schema appspec) return 0 without
  touching the connection at all.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from dazzle.core.ir.predicates import ColumnCheck, CompOp, ValueRef

pytest.importorskip("fastapi")

from dazzle.core.access import AccessOperationKind, EntityAccessSpec, ScopeRuleSpec
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.governance import TenancyMode
from dazzle.db.rls_apply import apply_rls_policies
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType


class _FakeCursor:
    """Returns DICT rows — ``dazzle.db.connection.get_connection`` configures a
    dict row factory, and the #1531 PG test proved tuple-shaped fakes hide a
    real unpacking bug (dict rows iterate their keys)."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    async def fetchall(self) -> list[dict[str, str]]:
        return self._rows


class _FakeTransaction:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeTransaction:
        self._conn.transactions_entered += 1
        self._conn.in_transaction = True
        return self

    async def __aexit__(self, *exc: object) -> bool:
        self._conn.in_transaction = False
        return False


class _FakeConn:
    """The slice of the psycopg3 AsyncConnection surface the apply path uses."""

    def __init__(self, info_rows: list[dict[str, str]]) -> None:
        self.info_rows = info_rows
        self.executed: list[str] = []
        self.executed_in_tx: list[str] = []
        self.transactions_entered = 0
        self.in_transaction = False

    async def execute(self, sql: str) -> _FakeCursor:
        self.executed.append(sql)
        if self.in_transaction:
            self.executed_in_tx.append(sql)
        return _FakeCursor(self.info_rows)

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)


def _scoped_entity() -> EntitySpec:
    pred = ColumnCheck(field="owner_id", op=CompOp.EQ, value=ValueRef(current_user=True))
    return EntitySpec(
        name="Project",
        fields=[
            FieldSpec(name="id", type=FieldType(kind="scalar", scalar_type=ScalarType.UUID)),
            FieldSpec(name="tenant_id", type=FieldType(kind="scalar", scalar_type=ScalarType.UUID)),
            FieldSpec(name="owner_id", type=FieldType(kind="ref", ref_entity="User")),
        ],
        access=EntityAccessSpec(
            scopes=[
                ScopeRuleSpec(operation=AccessOperationKind.READ, personas=["*"], predicate=pred)
            ]
        ),
    )


def _appspec(entities: list[EntitySpec], *, mode: TenancyMode | None) -> SimpleNamespace:
    tenancy = (
        None
        if mode is None
        else SimpleNamespace(isolation=SimpleNamespace(mode=mode, partition_key="tenant_id"))
    )
    graph = FKGraph()
    graph._edges = {"Project": []}
    graph._fields = {"Project": {"id", "tenant_id", "owner_id"}}
    return SimpleNamespace(
        tenancy=tenancy, domain=SimpleNamespace(entities=entities), fk_graph=graph
    )


def test_noop_appspec_never_touches_the_connection() -> None:
    entities = [_scoped_entity()]
    conn = _FakeConn(info_rows=[])
    applied = asyncio.run(apply_rls_policies(conn, _appspec(entities, mode=None), entities))
    assert applied == 0
    assert conn.executed == []
    assert conn.transactions_entered == 0


def test_apply_introspects_and_runs_all_ddl_in_one_transaction() -> None:
    entities = [_scoped_entity()]
    appspec = _appspec(entities, mode=TenancyMode.SHARED_SCHEMA)
    # Live column type for the scope column is TEXT (the #1531 drift shape),
    # delivered as a dict row (the production psycopg row factory).
    conn = _FakeConn(
        info_rows=[{"table_name": "Project", "column_name": "owner_id", "udt_name": "text"}]
    )

    applied = asyncio.run(apply_rls_policies(conn, appspec, entities))

    assert applied > 0
    # First statement on the wire is the information_schema introspection…
    assert "information_schema.columns" in conn.executed[0]
    # …and every DDL statement ran inside the single transaction.
    assert conn.transactions_entered == 1
    assert len(conn.executed_in_tx) == applied
    # The physical TEXT type drove the cast (no ::uuid against the text column).
    scope_select = next(
        s for s in conn.executed_in_tx if s.startswith("CREATE POLICY scope_select")
    )
    assert "::text" in scope_select
    assert "::uuid" not in scope_select
