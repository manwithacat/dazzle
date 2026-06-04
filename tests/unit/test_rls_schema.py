"""Unit tests for RLS policy + role DDL generation (RLS tenancy Phase B)."""

from __future__ import annotations

from dazzle.back.runtime.rls_schema import build_rls_policy_ddl, build_rls_role_ddl


def test_fence_is_restrictive_with_missing_ok_current_setting() -> None:
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="tenant_id"))
    assert 'ALTER TABLE "Project" ENABLE ROW LEVEL SECURITY' in ddl
    assert 'ALTER TABLE "Project" FORCE ROW LEVEL SECURITY' in ddl
    # restrictive fence, USING + WITH CHECK, missing-ok current_setting, ::uuid
    assert "AS RESTRICTIVE" in ddl
    assert "current_setting('dazzle.tenant_id', true)::uuid" in ddl
    assert ddl.count("current_setting('dazzle.tenant_id', true)::uuid") >= 2  # USING + WITH CHECK


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
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="org_id"))
    assert (
        "org_id = current_setting('dazzle.org_id', true)::uuid" in ddl
        or "\"org_id\" = current_setting('dazzle.org_id', true)::uuid" in ddl
    )


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
