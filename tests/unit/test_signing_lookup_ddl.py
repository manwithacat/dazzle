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


def test_empty_when_domain_has_no_entities_attr() -> None:
    """``or []`` — ``and []`` would iterate ``None`` (#1659 nightly L743)."""
    appspec = SimpleNamespace(domain=SimpleNamespace(), tenancy=None)
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
    assert 'SELECT "tenant_id"' in joined
    assert 'FROM "Contract"' in joined
    assert "zzz" not in joined
    owner = next(s for s in stmts if "OWNER TO dazzle_bypass" in s)
    grant = next(s for s in stmts if "GRANT EXECUTE" in s)
    assert "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'dazzle_bypass')" in owner
    assert "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'dazzle_app')" in grant
    assert not owner.strip().startswith("ALTER FUNCTION")
    assert not grant.strip().startswith("GRANT EXECUTE")


def test_unsigned_without_attr_is_not_in_case() -> None:
    """Default ``signable`` is False — True interpolates leftover names (#1659 L744)."""
    signed = SimpleNamespace(
        name="Contract",
        signable=True,
        fields=[SimpleNamespace(name="id"), SimpleNamespace(name="tenant_id")],
    )
    leftover = SimpleNamespace(
        name="Trust",
        fields=[SimpleNamespace(name="id")],
    )
    appspec = SimpleNamespace(
        domain=SimpleNamespace(entities=[signed, leftover]),
        tenancy=SimpleNamespace(isolation=SimpleNamespace(partition_key="tenant_id")),
    )
    joined = "\n".join(build_signing_lookup_ddl(appspec))
    assert "WHEN 'Contract'" in joined
    assert "WHEN 'Trust'" not in joined


def test_custom_partition_key_column_when_present() -> None:
    """Live partition_key wins — ``and "tenant_id"`` would replace ``org_id`` (#1659 L748)."""
    entity = SimpleNamespace(
        name="Contract",
        signable=True,
        fields=[SimpleNamespace(name="id"), SimpleNamespace(name="org_id")],
    )
    appspec = SimpleNamespace(
        domain=SimpleNamespace(entities=[entity]),
        tenancy=SimpleNamespace(isolation=SimpleNamespace(partition_key="org_id")),
    )
    joined = "\n".join(build_signing_lookup_ddl(appspec))
    assert 'SELECT "org_id"' in joined
    assert 'SELECT "tenant_id"' not in joined


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
