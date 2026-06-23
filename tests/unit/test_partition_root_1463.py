"""#1463: partition-root resolution for memberships (two-level tenancy RLS).

Unit coverage for the three pure-ish pieces of the fix:
  * ``build_partition_hierarchy`` — derive the parent graph from AppSpec entities.
  * ``resolve_partition_root`` — the sync probe-then-ascend walk (driven by a fake
    cursor that interprets the exact SQL the resolver emits).
  * ``_resolve_user_attribute("tenant_id")`` — binds partition_root_id, falling
    back to tenant_id.

The real-Postgres proof (RLS fence + host-confinement) lives in
``tests/integration/test_partition_root_hierarchy_rls_pg.py``.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from dazzle.http.runtime.auth.partition_root import (
    PartitionHierarchy,
    build_partition_hierarchy,
    reconcile_membership_partition_roots,
    resolve_partition_root,
)

# ── fake AppSpec entities ─────────────────────────────────────────────────────


def _ref_field(name: str, target: str) -> Any:
    return SimpleNamespace(name=name, type=SimpleNamespace(ref_entity=target))


def _tenant_entity(name: str, *, parent_field: str | None, fields: list[Any]) -> Any:
    return SimpleNamespace(
        name=name, fields=fields, tenant_host=SimpleNamespace(parent=parent_field)
    )


def _hierarchy_entities() -> list[Any]:
    # Region (root) ◂ Trust(region) ◂ School(trust)
    region = SimpleNamespace(name="Region", fields=[], tenant_host=SimpleNamespace(parent=None))
    trust = _tenant_entity("Trust", parent_field="region", fields=[_ref_field("region", "Region")])
    school = _tenant_entity("School", parent_field="trust", fields=[_ref_field("trust", "Trust")])
    # a non-tenant data entity is ignored
    report = SimpleNamespace(
        name="Report", fields=[_ref_field("school", "School")], tenant_host=None
    )
    return [region, trust, school, report]


# ── build_partition_hierarchy ─────────────────────────────────────────────────


def test_build_hierarchy_extracts_parent_edges() -> None:
    h = build_partition_hierarchy(_hierarchy_entities())
    assert h is not None
    assert h.parent_edges == {"Trust": ("region", "Region"), "School": ("trust", "Trust")}
    assert set(h.probe_kinds) == {"Trust", "School"}  # root (Region) is not probed


def test_build_hierarchy_flat_returns_none() -> None:
    # All tenant kinds are roots (no parent edge) → flat → None.
    flat = [
        SimpleNamespace(name="Workspace", fields=[], tenant_host=SimpleNamespace(parent=None)),
        SimpleNamespace(name="Item", fields=[], tenant_host=None),
    ]
    assert build_partition_hierarchy(flat) is None
    assert build_partition_hierarchy([]) is None
    assert build_partition_hierarchy(None) is None


def test_build_hierarchy_skips_malformed_edge() -> None:
    # `parent: trust` names a field that isn't a ref (no ref_entity) → edge skipped.
    bad = _tenant_entity(
        "School", parent_field="trust", fields=[SimpleNamespace(name="trust", type=None)]
    )
    assert build_partition_hierarchy([bad]) is None


# ── resolve_partition_root (fake cursor over the emitted SQL) ──────────────────


class _FakeCursor:
    """Interprets the two SQL shapes resolve_partition_root emits, over an
    in-memory ``{table: {id: {col: value}}}`` store."""

    _PROBE = re.compile(r'SELECT 1 AS hit FROM "(?P<t>\w+)" WHERE id::text = %s')
    _ASCEND = re.compile(r'SELECT "(?P<c>\w+)"::text AS pid FROM "(?P<t>\w+)" WHERE id::text = %s')

    def __init__(self, store: dict[str, dict[str, dict[str, Any]]]) -> None:
        self._store = store
        self._result: dict[str, Any] | None = None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        sql = " ".join(sql.split())  # collapse whitespace/newlines
        (rid,) = params
        if m := self._PROBE.search(sql):
            rows = self._store.get(m["t"], {})
            self._result = {"hit": 1} if str(rid) in rows else None
            return
        if m := self._ASCEND.search(sql):
            row = self._store.get(m["t"], {}).get(str(rid))
            val = row.get(m["c"]) if row else None
            self._result = {"pid": str(val)} if val is not None else {"pid": None}
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self) -> dict[str, Any] | None:
        return self._result


_H = PartitionHierarchy(parent_edges={"Trust": ("region", "Region"), "School": ("trust", "Trust")})


def _store() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "Region": {"reg-1": {}},
        "Trust": {"trust-1": {"region": "reg-1"}, "trust-2": {"region": "reg-1"}},
        "School": {"school-1": {"trust": "trust-1"}, "school-2": {"trust": "trust-2"}},
    }


def test_resolve_leaf_walks_to_root() -> None:
    cur = _FakeCursor(_store())
    # School → Trust → Region(root)
    assert resolve_partition_root(cur, "school-1", _H) == "reg-1"


def test_resolve_mid_walks_to_root() -> None:
    cur = _FakeCursor(_store())
    assert resolve_partition_root(cur, "trust-2", _H) == "reg-1"


def test_resolve_root_id_returns_itself() -> None:
    # Region is not a probe kind → unmatched probe → returns input unchanged.
    cur = _FakeCursor(_store())
    assert resolve_partition_root(cur, "reg-1", _H) == "reg-1"


def test_resolve_unknown_id_returns_itself() -> None:
    cur = _FakeCursor(_store())
    assert resolve_partition_root(cur, "ghost", _H) == "ghost"


def test_resolve_flat_hierarchy_is_noop() -> None:
    cur = _FakeCursor(_store())
    assert resolve_partition_root(cur, "anything", None) == "anything"


def test_resolve_null_parent_fk_stops_narrow() -> None:
    # School with a NULL trust FK → stops at the school (fail-closed/narrow), never
    # broadens to a root it can't prove.
    store = _store()
    store["School"]["orphan"] = {"trust": None}
    cur = _FakeCursor(store)
    assert resolve_partition_root(cur, "orphan", _H) == "orphan"


def test_resolve_cycle_guard_truncates() -> None:
    # A pathological cycle School→Trust→School must not loop forever.
    store = {
        "Trust": {"t": {"region": "s"}},
        "School": {"s": {"trust": "t"}},
    }
    h = PartitionHierarchy(
        parent_edges={"Trust": ("region", "School"), "School": ("trust", "Trust")}
    )
    cur = _FakeCursor(store)
    # Walk: s(School)→t(Trust)→s(seen) → truncate at t.
    assert resolve_partition_root(cur, "s", h) == "t"


# ── _resolve_user_attribute("tenant_id") binds partition_root_id ──────────────


def test_resolve_user_attribute_prefers_partition_root() -> None:
    from dazzle.http.runtime.scope_filters import _resolve_user_attribute

    membership = SimpleNamespace(tenant_id="school-1", partition_root_id="reg-1")
    ctx = SimpleNamespace(active_membership=membership, user=None, preferences={})
    assert _resolve_user_attribute("tenant_id", ctx) == "reg-1"


def test_resolve_user_attribute_falls_back_to_tenant_id() -> None:
    from dazzle.http.runtime.scope_filters import _resolve_user_attribute

    # Un-backfilled row: partition_root_id is None → fall back to tenant_id.
    membership = SimpleNamespace(tenant_id="school-1", partition_root_id=None)
    ctx = SimpleNamespace(active_membership=membership, user=None, preferences={})
    assert _resolve_user_attribute("tenant_id", ctx) == "school-1"


def test_resolve_user_attribute_no_membership_denies() -> None:
    from dazzle.http.runtime.scope_filters import _resolve_user_attribute

    ctx = SimpleNamespace(active_membership=None, user=None, preferences={})
    assert _resolve_user_attribute("tenant_id", ctx) == "__RBAC_DENY__"


# ── reconcile_membership_partition_roots (boot backfill / refresh) ────────────


class _ReconcileCursor(_FakeCursor):
    """Adds the memberships SELECT/UPDATE shapes on top of the probe/ascend cursor."""

    def __init__(
        self,
        tenant_store: dict[str, dict[str, dict[str, Any]]],
        memberships: dict[str, dict[str, Any]],
    ) -> None:
        super().__init__(tenant_store)
        self._memberships = memberships
        self._fetchall_result: list[dict[str, Any]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        s = " ".join(sql.split())
        if s.startswith("SELECT id, tenant_id, partition_root_id FROM memberships"):
            self._fetchall_result = [
                {
                    "id": mid,
                    "tenant_id": m["tenant_id"],
                    "partition_root_id": m["partition_root_id"],
                }
                for mid, m in self._memberships.items()
            ]
            return
        if s.startswith("UPDATE memberships SET partition_root_id"):
            root, _updated_at, mid = params
            self._memberships[mid]["partition_root_id"] = root
            return
        super().execute(sql, params)

    def fetchall(self) -> list[dict[str, Any]]:
        return self._fetchall_result


class _FakeStore:
    def __init__(self, cur: _ReconcileCursor) -> None:
        self._cur = cur

    @contextmanager
    def _transaction(self) -> Any:
        yield self._cur


def test_reconcile_backfills_null_and_refreshes_stale() -> None:
    memberships = {
        "m-leaf-null": {"tenant_id": "school-1", "partition_root_id": None},  # backfill → reg-1
        "m-leaf-ok": {"tenant_id": "school-2", "partition_root_id": "reg-1"},  # already correct
        "m-stale": {"tenant_id": "school-1", "partition_root_id": "wrong"},  # refresh → reg-1
        "m-root": {"tenant_id": "reg-1", "partition_root_id": "reg-1"},  # root, no change
    }
    cur = _ReconcileCursor(_store(), memberships)
    updated = reconcile_membership_partition_roots(_FakeStore(cur), _H)
    assert updated == 2  # the NULL and the stale rows
    assert memberships["m-leaf-null"]["partition_root_id"] == "reg-1"
    assert memberships["m-stale"]["partition_root_id"] == "reg-1"
    assert memberships["m-leaf-ok"]["partition_root_id"] == "reg-1"
    assert memberships["m-root"]["partition_root_id"] == "reg-1"


def test_reconcile_idempotent_second_pass_updates_nothing() -> None:
    memberships = {"m": {"tenant_id": "school-1", "partition_root_id": None}}
    cur = _ReconcileCursor(_store(), memberships)
    assert reconcile_membership_partition_roots(_FakeStore(cur), _H) == 1
    cur2 = _ReconcileCursor(_store(), memberships)
    assert reconcile_membership_partition_roots(_FakeStore(cur2), _H) == 0


def test_reconcile_flat_hierarchy_is_noop() -> None:
    memberships = {"m": {"tenant_id": "x", "partition_root_id": None}}
    cur = _ReconcileCursor(_store(), memberships)
    assert reconcile_membership_partition_roots(_FakeStore(cur), None) == 0
