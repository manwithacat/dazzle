"""Tests for ``build_all_rls_ddl`` — the shared RLS-DDL builder (Phase D, Task 1).

``build_all_rls_ddl(appspec, entities)`` is the single, DB-free partitioner that
both the dev ``create_all`` apply (``server._apply_rls_policies``) and Phase D's
prod-apply / inspect / drift paths consume. It mirrors the partitioning that
used to live inline in ``_apply_rls_policies``:

  * ``[]`` when there is no ``tenancy`` / the mode is not ``shared_schema`` /
    there are no tenant-scoped entities.
  * for a SHARED_SCHEMA appspec with a scoped entity (``access.scopes``) →
    its per-verb ``scope_*`` policies, with the permissive ``tenant_baseline``
    dropped (never recreated).
  * for a tenant-flat scoped entity (no scope rules) → fence + permissive
    ``tenant_baseline``.
  * raises ``ValueError`` when a scoped-with-rules entity has no ``fk_graph``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.core.ir.predicates import ColumnCheck, CompOp, ValueRef

pytest.importorskip("fastapi")

from dazzle.core.access import AccessOperationKind, EntityAccessSpec, ScopeRuleSpec
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.governance import TenancyMode
from dazzle.http.runtime.rls_schema import build_all_rls_ddl
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

# ---------------------------------------------------------------------------
# Synthetic appspec + back-spec entities (mirror test_rls_scope_policies.py)
# ---------------------------------------------------------------------------


def _scalar(st: ScalarType) -> FieldType:
    return FieldType(kind="scalar", scalar_type=st)


def _fk_graph() -> FKGraph:
    graph = FKGraph()
    graph._edges = {"Project": []}
    graph._fields = {"Project": {"id", "tenant_id", "owner_id", "status"}}
    return graph


def _project_fields() -> list[FieldSpec]:
    return [
        FieldSpec(name="id", type=_scalar(ScalarType.UUID)),
        FieldSpec(name="tenant_id", type=_scalar(ScalarType.UUID)),
        FieldSpec(name="owner_id", type=FieldType(kind="ref", ref_entity="User")),
        FieldSpec(name="status", type=_scalar(ScalarType.STR)),
    ]


def _account_fields() -> list[FieldSpec]:
    return [
        FieldSpec(name="id", type=_scalar(ScalarType.UUID)),
        FieldSpec(name="tenant_id", type=_scalar(ScalarType.UUID)),
        FieldSpec(name="name", type=_scalar(ScalarType.STR)),
    ]


def _untenanted_fields() -> list[FieldSpec]:
    # No partition_key column → not tenant-scoped.
    return [
        FieldSpec(name="id", type=_scalar(ScalarType.UUID)),
        FieldSpec(name="label", type=_scalar(ScalarType.STR)),
    ]


def _owner_rule(op: AccessOperationKind) -> ScopeRuleSpec:
    pred = ColumnCheck(field="owner_id", op=CompOp.EQ, value=ValueRef(current_user=True))
    return ScopeRuleSpec(operation=op, personas=["*"], predicate=pred)


def _scoped_project(scopes: list[ScopeRuleSpec]) -> EntitySpec:
    return EntitySpec(
        name="Project",
        fields=_project_fields(),
        access=EntityAccessSpec(scopes=scopes),
    )


def _flat_account() -> EntitySpec:
    return EntitySpec(name="Account", fields=_account_fields(), access=EntityAccessSpec(scopes=[]))


def _untenanted() -> EntitySpec:
    return EntitySpec(name="Catalog", fields=_untenanted_fields())


def _appspec(
    entities: list[EntitySpec],
    *,
    mode: TenancyMode | None = TenancyMode.SHARED_SCHEMA,
    partition_key: str = "tenant_id",
    fk_graph: object | None = "default",
) -> SimpleNamespace:
    """A minimal duck-typed appspec carrying just what the builder reads.

    ``appspec.tenancy``, ``appspec.domain.entities`` (for scoped_entity_names),
    and ``appspec.fk_graph``. ``mode=None`` means no tenancy block at all.
    """
    if mode is None:
        tenancy = None
    else:
        tenancy = SimpleNamespace(isolation=SimpleNamespace(mode=mode, partition_key=partition_key))
    graph = _fk_graph() if fk_graph == "default" else fk_graph
    return SimpleNamespace(
        tenancy=tenancy,
        domain=SimpleNamespace(entities=entities),
        fk_graph=graph,
    )


def _joined(stmts: list[str]) -> str:
    return "\n".join(stmts)


# ---------------------------------------------------------------------------
# Empty-result cases
# ---------------------------------------------------------------------------


def test_empty_when_no_tenancy() -> None:
    entities = [_scoped_project([_owner_rule(AccessOperationKind.READ)])]
    appspec = _appspec(entities, mode=None)
    assert build_all_rls_ddl(appspec, entities) == []


def test_empty_when_not_shared_schema() -> None:
    entities = [_scoped_project([_owner_rule(AccessOperationKind.READ)])]
    appspec = _appspec(entities, mode=TenancyMode.SCHEMA_PER_TENANT)
    assert build_all_rls_ddl(appspec, entities) == []


def test_empty_when_no_scoped_entities() -> None:
    # SHARED_SCHEMA but no entity carries the partition_key column.
    entities = [_untenanted()]
    appspec = _appspec(entities)
    assert build_all_rls_ddl(appspec, entities) == []


# ---------------------------------------------------------------------------
# Scoped entity → scope_* policies + dropped baseline
# ---------------------------------------------------------------------------


def test_scoped_entity_emits_scope_policies_and_drops_baseline() -> None:
    entities = [_scoped_project([_owner_rule(AccessOperationKind.READ)])]
    appspec = _appspec(entities)
    ddl = _joined(build_all_rls_ddl(appspec, entities))

    assert 'ALTER TABLE "Project" ENABLE ROW LEVEL SECURITY' in ddl
    assert 'ALTER TABLE "Project" FORCE ROW LEVEL SECURITY' in ddl
    assert 'CREATE POLICY tenant_fence ON "Project"' in ddl
    assert 'CREATE POLICY scope_select ON "Project"' in ddl
    # Baseline is dropped, never recreated, for a scoped entity.
    assert 'DROP POLICY IF EXISTS tenant_baseline ON "Project"' in ddl
    assert "CREATE POLICY tenant_baseline" not in ddl


# ---------------------------------------------------------------------------
# Tenant-flat entity → fence + permissive baseline
# ---------------------------------------------------------------------------


def test_tenant_flat_entity_emits_fence_and_baseline() -> None:
    entities = [_flat_account()]
    appspec = _appspec(entities)
    ddl = _joined(build_all_rls_ddl(appspec, entities))

    assert 'ALTER TABLE "Account" ENABLE ROW LEVEL SECURITY' in ddl
    assert 'CREATE POLICY tenant_fence ON "Account"' in ddl
    assert 'CREATE POLICY tenant_baseline ON "Account"' in ddl
    assert "USING (true)" in ddl
    # No scope policies for a tenant-flat entity.
    assert "scope_select" not in ddl


def test_mixed_scoped_and_flat() -> None:
    project = _scoped_project([_owner_rule(AccessOperationKind.READ)])
    account = _flat_account()
    catalog = _untenanted()  # not scoped → no policies
    entities = [project, account, catalog]
    appspec = _appspec(entities)
    ddl = _joined(build_all_rls_ddl(appspec, entities))

    assert 'CREATE POLICY scope_select ON "Project"' in ddl
    assert 'CREATE POLICY tenant_baseline ON "Account"' in ddl
    # The untenanted entity gets nothing.
    assert '"Catalog"' not in ddl


# ---------------------------------------------------------------------------
# Fail loud: scoped-with-rules entity but no fk_graph
# ---------------------------------------------------------------------------


def test_fail_loud_when_scoped_rules_and_no_fk_graph() -> None:
    entities = [_scoped_project([_owner_rule(AccessOperationKind.READ)])]
    appspec = _appspec(entities, fk_graph=None)
    with pytest.raises(ValueError, match="FK graph"):
        build_all_rls_ddl(appspec, entities)


def test_no_fk_graph_ok_when_only_flat_entities() -> None:
    # A tenant-flat entity needs no fk_graph (no predicate compilation).
    entities = [_flat_account()]
    appspec = _appspec(entities, fk_graph=None)
    ddl = _joined(build_all_rls_ddl(appspec, entities))
    assert 'CREATE POLICY tenant_baseline ON "Account"' in ddl


# ---------------------------------------------------------------------------
# #1531: physical column-type overrides for the GUC casts
# ---------------------------------------------------------------------------


def _scope_select_stmt(stmts: list[str]) -> str:
    return next(s for s in stmts if s.startswith("CREATE POLICY scope_select"))


def test_physical_cast_overrides_normalises_udt_names() -> None:
    from dazzle.http.runtime.rls_schema import physical_cast_overrides

    rows = [
        ("Project", "owner_id", "varchar"),
        ("Project", "tenant_id", "uuid"),
        ("Project", "flag", "bool"),
        ("Project", "weird", "hstore"),  # unknown udt → no override (fail-safe)
        # Dict rows — the `dazzle db` CLI's psycopg connection uses a dict row
        # factory, so the mapping shape must resolve identically (#1531).
        {"table_name": "Task", "column_name": "owner", "udt_name": "varchar"},
    ]
    overrides = physical_cast_overrides(rows)
    assert overrides[("Project", "owner_id")] == "text"
    assert overrides[("Project", "tenant_id")] == "uuid"
    assert overrides[("Project", "flag")] == "boolean"
    assert ("Project", "weird") not in overrides
    assert overrides[("Task", "owner")] == "text"


def test_physical_text_column_suppresses_uuid_cast() -> None:
    # The #1531 regression shape: owner_id is logically a ref (→ uuid cast) but
    # the live column is TEXT (created before its type migration was generated).
    # The scope policy must cast the GUC to the PHYSICAL type or CREATE POLICY
    # fails with `operator does not exist: text = uuid`.
    entities = [_scoped_project([_owner_rule(AccessOperationKind.READ)])]
    appspec = _appspec(entities)
    stmts = build_all_rls_ddl(appspec, entities, physical_types={("Project", "owner_id"): "text"})
    scope_select = _scope_select_stmt(stmts)
    assert "::text" in scope_select
    assert "::uuid" not in scope_select


def test_physical_override_falls_back_to_logical_for_missing_columns() -> None:
    # A physical map that doesn't mention the scope column leaves the logical
    # (ref → uuid) resolution in charge.
    entities = [_scoped_project([_owner_rule(AccessOperationKind.READ)])]
    appspec = _appspec(entities)
    stmts = build_all_rls_ddl(appspec, entities, physical_types={("Project", "status"): "text"})
    assert "::uuid" in _scope_select_stmt(stmts)


def test_physical_matching_logical_emits_same_ddl_as_db_free_build() -> None:
    # When live and logical types agree, the physical-aware build is
    # byte-identical to the DB-free one.
    entities = [_scoped_project([_owner_rule(AccessOperationKind.READ)])]
    appspec = _appspec(entities)
    db_free = build_all_rls_ddl(appspec, entities)
    physical = build_all_rls_ddl(
        appspec, entities, physical_types={("Project", "owner_id"): "uuid"}
    )
    assert physical == db_free


def test_physical_logical_drift_logs_warning(caplog) -> None:
    import logging

    entities = [_scoped_project([_owner_rule(AccessOperationKind.READ)])]
    appspec = _appspec(entities)
    with caplog.at_level(logging.WARNING, logger="dazzle.http.runtime.rls_schema"):
        build_all_rls_ddl(appspec, entities, physical_types={("Project", "owner_id"): "text"})
    assert any("dazzle db revision" in r.message for r in caplog.records)
