"""Unit tests for RLS policy + role DDL generation (RLS tenancy Phase B)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.core.ir import TenancyMode
from dazzle.http.runtime.rls_schema import (
    build_all_rls_ddl,
    build_rls_policy_ddl,
    build_rls_role_ddl,
    build_rls_scope_policy_ddl,
    describe_rls_policies,
)


def test_fence_is_restrictive_with_missing_ok_current_setting() -> None:
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="tenant_id"))
    assert 'ALTER TABLE "Project" ENABLE ROW LEVEL SECURITY' in ddl
    assert 'ALTER TABLE "Project" FORCE ROW LEVEL SECURITY' in ddl
    # restrictive fence, USING + WITH CHECK, missing-ok current_setting, ::uuid.
    # NULLIF(.., '') collapses the pooled empty-string GUC state to NULL → deny
    # instead of a raising ''::uuid (#1400).
    assert "AS RESTRICTIVE" in ddl
    assert "NULLIF(current_setting('dazzle.tenant_id', true), '')::uuid" in ddl
    assert (
        ddl.count("NULLIF(current_setting('dazzle.tenant_id', true), '')::uuid") >= 2
    )  # USING + WITH CHECK


def test_permissive_baseline_present() -> None:
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="tenant_id"))
    assert "AS PERMISSIVE" in ddl
    assert "USING (true)" in ddl  # baseline so a fenced table is not deny-all (companion §1.4)


def test_idempotent_drop_before_create() -> None:
    # CREATE POLICY has no IF NOT EXISTS; generator drops first so re-apply is safe.
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="tenant_id"))
    assert 'DROP POLICY IF EXISTS tenant_fence ON "Project"' in ddl
    assert 'DROP POLICY IF EXISTS tenant_baseline ON "Project"' in ddl
    fence_drop = ddl.index("DROP POLICY IF EXISTS tenant_fence")
    fence_create = ddl.index("CREATE POLICY tenant_fence")
    assert fence_drop < fence_create


def test_custom_partition_key() -> None:
    # C-2: a custom partition_key drives only the fenced COLUMN; the GUC the
    # fence reads is the FIXED framework constant dazzle.tenant_id (the same one
    # the runtime sets). It must NOT become dazzle.org_id, which the runtime
    # never sets → silent total-deny.
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="org_id"))
    assert "\"org_id\" = NULLIF(current_setting('dazzle.tenant_id', true), '')::uuid" in ddl
    # the partition-key-derived GUC name must never appear
    assert "dazzle.org_id" not in ddl


def test_empty_when_no_entities() -> None:
    assert build_rls_policy_ddl([], partition_key="tenant_id") == []


def test_multi_entity_emits_per_table_in_order() -> None:
    stmts = build_rls_policy_ddl(["Project", "Task"], partition_key="tenant_id")
    # 6 statements per entity: ENABLE, FORCE, DROP+CREATE fence, DROP+CREATE baseline.
    assert len(stmts) == 12
    ddl = "\n".join(stmts)
    assert ddl.index('ON "Project"') < ddl.index('ON "Task"')
    assert ddl.count("CREATE POLICY tenant_fence") == 2
    assert ddl.count("CREATE POLICY tenant_baseline") == 2


def test_app_role_statement_never_grants_bypassrls() -> None:
    # The whole dazzle_app DO block (not just one line) must never grant BYPASSRLS.
    stmts = build_rls_role_ddl(app_password="pw", bypass_password="pw")
    app_stmt = next(s for s in stmts if "CREATE ROLE dazzle_app" in s)
    assert "BYPASSRLS" not in app_stmt
    bypass_stmt = next(s for s in stmts if "CREATE ROLE dazzle_bypass" in s)
    assert "BYPASSRLS" in bypass_stmt
    # Optional password is escaped and embedded only when supplied.
    assert "PASSWORD 'pw'" in app_stmt
    # Default call embeds no password.
    assert "PASSWORD" not in next(s for s in build_rls_role_ddl() if "CREATE ROLE dazzle_app" in s)


def test_role_ddl_three_roles_idempotent_no_bypass_on_app() -> None:
    ddl = "\n".join(build_rls_role_ddl())
    assert "dazzle_owner" in ddl and "dazzle_app" in ddl and "dazzle_bypass" in ddl
    assert "BYPASSRLS" in ddl  # on dazzle_bypass
    # dazzle_app must NOT be granted BYPASSRLS
    app_line = next(
        line
        for line in ddl.splitlines()
        if "dazzle_app" in line and ("ROLE" in line or "LOGIN" in line)
    )
    assert "BYPASSRLS" not in app_line
    # idempotent (guarded create — DO block / IF NOT EXISTS pattern)
    assert "pg_roles" in ddl or "IF NOT EXISTS" in ddl
    # PG15+ (CVE-2022-2625): schema USAGE must be granted or the LOGIN roles
    # cannot resolve any object in public and the table grants are inert.
    assert "GRANT USAGE ON SCHEMA public" in ddl


# ---------------------------------------------------------------------------
# Orchestrator branch coverage (mutation-audit residuals, 2026-06-08).
# build_all_rls_ddl / describe_rls_policies were exercised only end-to-end by
# the PG suite; these pin the tenancy-gate and scoped-vs-flat branches directly
# with lightweight stubs (scoped_entity_names only checks for a `tenant_id`
# field; the type resolver is lazy, so no real schema is needed).
# ---------------------------------------------------------------------------


def _field(name: str):
    return SimpleNamespace(name=name, type=None)


def _stub_appspec(entities: list, *, mode: TenancyMode = TenancyMode.SHARED_SCHEMA):
    domain = SimpleNamespace(
        entities=[SimpleNamespace(name=e.name, fields=e.fields) for e in entities]
    )
    return SimpleNamespace(
        tenancy=SimpleNamespace(isolation=SimpleNamespace(mode=mode, partition_key="tenant_id")),
        domain=domain,
        fk_graph=None,
    )


def _flat_scoped_entity(name: str = "Flat", *, access):
    # Tenant-scoped (has a tenant_id field) entity with the given `access` object.
    return SimpleNamespace(name=name, fields=[_field("tenant_id"), _field("id")], access=access)


def test_no_tenancy_emits_nothing_without_crashing() -> None:
    # tenancy is None → empty, and the guard must short-circuit BEFORE touching
    # `tenancy.isolation` (an `or`→`and` mutation would dereference None and crash).
    none_app = SimpleNamespace(tenancy=None)
    assert build_all_rls_ddl(none_app, []) == []
    assert describe_rls_policies(none_app, []) == []


def test_shared_schema_with_scoped_entity_emits_policies() -> None:
    # A shared_schema app with a tenant-scoped entity MUST emit RLS — inverting the
    # `mode != SHARED_SCHEMA` guard (`!=`→`==`) would silently emit nothing (no tenant
    # isolation at all), the worst possible RLS regression.
    flat = _flat_scoped_entity(access=None)
    app = _stub_appspec([flat])
    assert build_all_rls_ddl(app, [flat]) != []
    assert describe_rls_policies(app, [flat]) != []


def test_non_shared_schema_emits_nothing() -> None:
    flat = _flat_scoped_entity(access=None)
    app = _stub_appspec([flat], mode=TenancyMode.SCHEMA_PER_TENANT)
    assert build_all_rls_ddl(app, [flat]) == []
    assert describe_rls_policies(app, [flat]) == []


def test_access_without_scope_rules_is_tenant_flat() -> None:
    # An entity with an `access` block but NO scope rules is tenant-FLAT → it gets the
    # permissive baseline, not a per-verb scope policy. `has_scopes` is
    # `access is not None AND bool(scopes)`; an `and`→`or` mutation would mis-route it to
    # the scope path (build_all_rls_ddl would then raise ValueError; describe would drop
    # the baseline). access present + empty scopes is the only input that distinguishes them.
    flat = _flat_scoped_entity(access=SimpleNamespace(scopes=[]))
    app = _stub_appspec([flat])

    ddl = build_all_rls_ddl(app, [flat])  # must NOT raise
    assert ddl
    descs = describe_rls_policies(app, [flat])
    assert any(d.entity == "Flat" and d.name == "tenant_baseline" and d.permissive for d in descs)


def test_scope_policy_ddl_requires_scope_rules() -> None:
    # build_rls_scope_policy_ddl is for scoped entities only; on a no-scopes entity it must
    # raise ValueError (not proceed). `access is None OR not access.scopes` → an `or`→`and`
    # mutation would dereference None / skip the guard.
    no_access = SimpleNamespace(name="X", access=None)
    with pytest.raises(ValueError):
        build_rls_scope_policy_ddl(no_access, None, None, partition_key="tenant_id")

    empty_scopes = SimpleNamespace(name="X", access=SimpleNamespace(scopes=[]))
    with pytest.raises(ValueError):
        build_rls_scope_policy_ddl(empty_scopes, None, None, partition_key="tenant_id")


def _degrading_entity(personas: list[str]) -> SimpleNamespace:
    """A scoped entity whose single read-rule will hit the #1447 degradation path
    (compile_predicate_policy is monkeypatched to raise in the test)."""
    rule = SimpleNamespace(
        operation=SimpleNamespace(value="read"),
        predicate=SimpleNamespace(kind="exists_check"),  # content irrelevant — compile is patched
        personas=personas,
    )
    return SimpleNamespace(name="Doc", access=SimpleNamespace(scopes=[rule]))


def test_degraded_verb_names_personas_in_warning(monkeypatch, caplog) -> None:
    """#1447 graceful degradation: when a scope rule is not RLS-policy-expressible,
    the warning must name the rule's personas. The persona string is otherwise
    unobserved by DDL assertions (degraded_verbs is membership-only), so without
    this the `personas = ... or [] ... or "*"` fallback (rls_schema.py L542) is a
    coverage gap — its two mutants (`or []`→`and []`, `or "*"`→`and "*"`) both
    collapse the personas to "*" and would survive."""
    import logging

    from dazzle.http.runtime import predicate_compiler

    def _raise(*_a, **_k):
        raise ValueError("not RLS-policy-expressible (test)")

    monkeypatch.setattr(predicate_compiler, "compile_predicate_policy", _raise)

    entity = _degrading_entity(["auditor", "manager"])
    with caplog.at_level(logging.WARNING):
        ddl = build_rls_scope_policy_ddl(entity, None, None, partition_key="tenant_id")

    # Degradation does NOT abort — the verb still gets a permissive (fence-only) policy.
    assert any("CREATE POLICY" in s for s in ddl)
    # The warning names the personas verbatim — kills both L542 fallback mutants.
    assert "as auditor, manager" in caplog.text


def test_degraded_verb_no_personas_defaults_to_star(monkeypatch, caplog) -> None:
    """A degraded rule with no personas falls back to ``*`` in the warning — the
    true-branch of the ``or "*"`` default."""
    import logging

    from dazzle.http.runtime import predicate_compiler

    monkeypatch.setattr(
        predicate_compiler,
        "compile_predicate_policy",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("nope")),
    )

    entity = _degrading_entity([])
    with caplog.at_level(logging.WARNING):
        build_rls_scope_policy_ddl(entity, None, None, partition_key="tenant_id")

    assert "as *" in caplog.text
