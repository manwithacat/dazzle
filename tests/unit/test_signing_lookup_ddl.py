"""ADR-0055 D5: signing DEFINER DDL is closed over IR signable names."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.rls_schema import build_signing_lookup_ddl


def test_empty_when_no_signable() -> None:
    appspec = SimpleNamespace(
        domain=SimpleNamespace(entities=[SimpleNamespace(name="Trust", signable=False, fields=[])]),
        tenancy=SimpleNamespace(isolation=SimpleNamespace(partition_key="tenant_id")),
    )
    assert build_signing_lookup_ddl(appspec) == []


def test_owner_is_dazzle_bypass_and_grant_is_app() -> None:
    entity = SimpleNamespace(
        name="Contract",
        signable=True,
        fields=[SimpleNamespace(name="id"), SimpleNamespace(name="tenant_id")],
    )
    appspec = SimpleNamespace(
        domain=SimpleNamespace(entities=[entity]),
        tenancy=SimpleNamespace(isolation=SimpleNamespace(partition_key="tenant_id")),
    )
    stmts = build_signing_lookup_ddl(appspec)
    joined = "\n".join(stmts)
    assert "SECURITY DEFINER" in joined
    assert "OWNER TO dazzle_bypass" in joined
    assert "GRANT EXECUTE" in joined and "dazzle_app" in joined
    assert "REVOKE ALL" in joined
    assert "WHEN 'Contract'" in joined
    assert "zzz" not in joined


def test_tenant_root_selects_id_not_tenant_id() -> None:
    entity = SimpleNamespace(
        name="Trust",
        signable=True,
        fields=[SimpleNamespace(name="id"), SimpleNamespace(name="slug")],
    )
    appspec = SimpleNamespace(
        domain=SimpleNamespace(entities=[entity]),
        tenancy=SimpleNamespace(isolation=SimpleNamespace(partition_key="tenant_id")),
    )
    joined = "\n".join(build_signing_lookup_ddl(appspec))
    assert 'SELECT "id"' in joined
    assert 'FROM "Trust"' in joined
