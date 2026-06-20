"""Per-verb intra-tenant RLS scope policy DDL tests (RLS tenancy Phase C, Task 2).

A *scoped* entity (one with ≥1 ``access.scopes`` rule) drops Phase B's permissive
``tenant_baseline`` and instead carries one permissive policy per **permitted
verb**, compiled from the scope algebra:

  * ``scope_select``  — ``FOR SELECT``  ``USING (<OR of read + list predicates>)``
  * ``scope_insert``  — ``FOR INSERT``  ``WITH CHECK (<create predicate>)``
  * ``scope_update``  — ``FOR UPDATE``  ``USING (<update>) WITH CHECK (<update>)``
  * ``scope_delete``  — ``FOR DELETE``  ``USING (<delete predicate>)``

A verb with no scope rule emits NO policy → that verb is denied (companion §1.4).
Multiple rules for one verb (multiple personas) OR their predicate bodies. The
restrictive ``tenant_fence`` (Phase B) is unchanged and ANDs over everything.

A *tenant-flat* entity (no scope rules) keeps Phase B's ``tenant_baseline``.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.predicates import ColumnCheck, CompOp, ValueRef

pytest.importorskip("fastapi")

from dazzle.core.access import AccessOperationKind, EntityAccessSpec, ScopeRuleSpec
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.http.runtime.predicate_compiler import build_entity_type_resolver
from dazzle.http.runtime.rls_schema import (
    build_rls_policy_ddl,
    build_rls_scope_policy_ddl,
)

# The runtime apply path passes the *converted* back-spec entities
# (``self._entities``), so the test builds the same shape: a back-spec
# ``EntitySpec`` whose ``access.scopes`` are ``ScopeRuleSpec`` carrying the
# compiled ScopePredicate, keyed by ``AccessOperationKind``.
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

# ---------------------------------------------------------------------------
# Fixtures: a synthetic scoped entity + its FK graph + type resolver
# ---------------------------------------------------------------------------


def _scalar(st: ScalarType) -> FieldType:
    return FieldType(kind="scalar", scalar_type=st)


def _fk_graph() -> FKGraph:
    graph = FKGraph()
    graph._edges = {"Project": []}
    graph._fields = {"Project": {"id", "tenant_id", "owner_id", "status", "department"}}
    return graph


def _project_fields() -> list[FieldSpec]:
    return [
        FieldSpec(name="id", type=_scalar(ScalarType.UUID)),
        FieldSpec(name="tenant_id", type=_scalar(ScalarType.UUID)),
        FieldSpec(name="owner_id", type=FieldType(kind="ref", ref_entity="User")),
        FieldSpec(name="status", type=_scalar(ScalarType.STR)),
        FieldSpec(name="department", type=_scalar(ScalarType.STR)),
    ]


def _owner_rule(op: AccessOperationKind) -> ScopeRuleSpec:
    """``owner_id = current_user`` scope rule for *op* (predicate pre-compiled)."""
    pred = ColumnCheck(field="owner_id", op=CompOp.EQ, value=ValueRef(current_user=True))
    return ScopeRuleSpec(operation=op, personas=["*"], predicate=pred)


def _status_rule(op: AccessOperationKind, value: str) -> ScopeRuleSpec:
    """``status = <value>`` scope rule for *op* (predicate pre-compiled)."""
    pred = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal=value))
    return ScopeRuleSpec(operation=op, personas=["*"], predicate=pred)


def _scoped_entity(scopes: list[ScopeRuleSpec]) -> EntitySpec:
    return EntitySpec(
        name="Project",
        fields=_project_fields(),
        access=EntityAccessSpec(scopes=scopes),
    )


def _resolver() -> object:
    return build_entity_type_resolver([_scoped_entity([])])


def _ddl(entity: EntitySpec) -> str:
    stmts = build_rls_scope_policy_ddl(
        entity,
        _fk_graph(),
        _resolver(),
        partition_key="tenant_id",
    )
    return "\n".join(stmts)


# ---------------------------------------------------------------------------
# Fence + ENABLE/FORCE are still present (composed from Phase B)
# ---------------------------------------------------------------------------


def test_enable_force_and_fence_still_present() -> None:
    ddl = _ddl(_scoped_entity([_owner_rule(AccessOperationKind.READ)]))
    assert 'ALTER TABLE "Project" ENABLE ROW LEVEL SECURITY' in ddl
    assert 'ALTER TABLE "Project" FORCE ROW LEVEL SECURITY' in ddl
    assert 'CREATE POLICY tenant_fence ON "Project"' in ddl
    assert "AS RESTRICTIVE" in ddl
    assert "NULLIF(current_setting('dazzle.tenant_id', true), '')::uuid" in ddl  # #1400


# ---------------------------------------------------------------------------
# Baseline is dropped for a scoped entity (no permissive FOR ALL baseline)
# ---------------------------------------------------------------------------


def test_baseline_dropped_for_scoped_entity() -> None:
    ddl = _ddl(_scoped_entity([_owner_rule(AccessOperationKind.READ)]))
    assert 'DROP POLICY IF EXISTS tenant_baseline ON "Project"' in ddl
    # No baseline is CREATED for a scoped entity.
    assert "CREATE POLICY tenant_baseline" not in ddl


# ---------------------------------------------------------------------------
# Per-verb policies: SELECT / INSERT / UPDATE / DELETE
# ---------------------------------------------------------------------------


def test_scope_select_for_read() -> None:
    ddl = _ddl(_scoped_entity([_owner_rule(AccessOperationKind.READ)]))
    assert 'DROP POLICY IF EXISTS scope_select ON "Project"' in ddl
    assert 'CREATE POLICY scope_select ON "Project"' in ddl
    assert "AS PERMISSIVE" in ddl
    assert "FOR SELECT" in ddl
    assert 'USING ("Project"."owner_id" = current_setting(\'dazzle.user_id\', true)::uuid)' in ddl


def test_scope_insert_with_check_only() -> None:
    ddl = _ddl(_scoped_entity([_owner_rule(AccessOperationKind.CREATE)]))
    assert 'CREATE POLICY scope_insert ON "Project"' in ddl
    assert "FOR INSERT" in ddl
    assert (
        'WITH CHECK ("Project"."owner_id" = current_setting(\'dazzle.user_id\', true)::uuid)' in ddl
    )
    # INSERT policies have no USING clause.
    insert_block = ddl[ddl.index("CREATE POLICY scope_insert") :]
    insert_block = insert_block.split("CREATE POLICY", 2)[1]  # the scope_insert block only
    assert "USING" not in insert_block


def test_scope_update_using_and_with_check() -> None:
    ddl = _ddl(_scoped_entity([_owner_rule(AccessOperationKind.UPDATE)]))
    assert 'CREATE POLICY scope_update ON "Project"' in ddl
    assert "FOR UPDATE" in ddl
    body = '"Project"."owner_id" = current_setting(\'dazzle.user_id\', true)::uuid'
    assert f"USING      ({body})" in ddl
    assert f"WITH CHECK ({body})" in ddl


def test_scope_delete_using_only() -> None:
    ddl = _ddl(_scoped_entity([_owner_rule(AccessOperationKind.DELETE)]))
    assert 'CREATE POLICY scope_delete ON "Project"' in ddl
    assert "FOR DELETE" in ddl
    body = '"Project"."owner_id" = current_setting(\'dazzle.user_id\', true)::uuid'
    assert f"USING ({body})" in ddl
    delete_block = ddl[ddl.index("CREATE POLICY scope_delete") :]
    assert "WITH CHECK" not in delete_block


# ---------------------------------------------------------------------------
# A verb with no scope rule → no policy → denied (companion §1.4)
# ---------------------------------------------------------------------------


def test_missing_verb_emits_no_policy() -> None:
    # Only a READ rule → SELECT covered; insert/update/delete have no policy.
    ddl = _ddl(_scoped_entity([_owner_rule(AccessOperationKind.READ)]))
    assert "scope_select" in ddl
    assert "CREATE POLICY scope_insert" not in ddl
    assert "CREATE POLICY scope_update" not in ddl
    assert "CREATE POLICY scope_delete" not in ddl
    # The drops are still emitted (idempotent re-apply), but nothing is created.
    assert 'DROP POLICY IF EXISTS scope_insert ON "Project"' in ddl


# ---------------------------------------------------------------------------
# read + list → ONE scope_select with the OR union of both predicates (§2.1)
# ---------------------------------------------------------------------------


def test_read_and_list_union_in_scope_select() -> None:
    ddl = _ddl(
        _scoped_entity(
            [
                _owner_rule(AccessOperationKind.READ),  # owner_id = current_user
                _status_rule(AccessOperationKind.LIST, "active"),  # status = 'active'
            ]
        )
    )
    # Exactly one scope_select, USING the OR of read + list bodies.
    assert ddl.count("CREATE POLICY scope_select") == 1
    assert "FOR SELECT" in ddl
    owner = '"Project"."owner_id" = current_setting(\'dazzle.user_id\', true)::uuid'
    status = '"Project"."status" = \'active\''
    assert f"USING (({owner}) OR ({status}))" in ddl


def test_list_only_maps_to_select() -> None:
    ddl = _ddl(_scoped_entity([_status_rule(AccessOperationKind.LIST, "active")]))
    assert "CREATE POLICY scope_select" in ddl
    assert "FOR SELECT" in ddl
    assert 'USING ("Project"."status" = \'active\')' in ddl


# ---------------------------------------------------------------------------
# Multiple personas/rules for the SAME verb → OR the bodies
# ---------------------------------------------------------------------------


def test_multiple_rules_same_verb_or_together() -> None:
    ddl = _ddl(
        _scoped_entity(
            [
                _owner_rule(AccessOperationKind.UPDATE),  # owner_id = current_user
                _status_rule(AccessOperationKind.UPDATE, "draft"),  # status = 'draft'
            ]
        )
    )
    assert ddl.count("CREATE POLICY scope_update") == 1
    owner = '"Project"."owner_id" = current_setting(\'dazzle.user_id\', true)::uuid'
    status = '"Project"."status" = \'draft\''
    assert f"USING      (({owner}) OR ({status}))" in ddl
    assert f"WITH CHECK (({owner}) OR ({status}))" in ddl


# ---------------------------------------------------------------------------
# Idempotence: each scope policy is DROP-before-CREATE
# ---------------------------------------------------------------------------


def test_scope_policies_drop_before_create() -> None:
    ddl = _ddl(
        _scoped_entity(
            [
                _owner_rule(AccessOperationKind.READ),
                _owner_rule(AccessOperationKind.CREATE),
                _owner_rule(AccessOperationKind.UPDATE),
                _owner_rule(AccessOperationKind.DELETE),
            ]
        )
    )
    for pol in ("scope_select", "scope_insert", "scope_update", "scope_delete"):
        assert f'DROP POLICY IF EXISTS {pol} ON "Project"' in ddl
        assert ddl.index(f"DROP POLICY IF EXISTS {pol}") < ddl.index(f"CREATE POLICY {pol}")


def test_no_bind_params_in_policy_bodies() -> None:
    ddl = _ddl(
        _scoped_entity(
            [
                _owner_rule(AccessOperationKind.READ),
                _status_rule(AccessOperationKind.LIST, "active"),
            ]
        )
    )
    assert "%s" not in ddl


# ---------------------------------------------------------------------------
# Tenant-flat entity keeps Phase B's tenant_baseline (unchanged)
# ---------------------------------------------------------------------------


def test_tenant_flat_entity_keeps_baseline() -> None:
    # An entity with no scope rules → use Phase B's build_rls_policy_ddl,
    # which CREATEs the permissive baseline.
    ddl = "\n".join(build_rls_policy_ddl(["Account"], partition_key="tenant_id"))
    assert "CREATE POLICY tenant_baseline" in ddl
    assert "USING (true)" in ddl
    # No per-verb scope policies for a tenant-flat entity.
    assert "scope_select" not in ddl
