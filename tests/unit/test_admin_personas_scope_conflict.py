"""Regression guard for #1184.

A persona listed in `tenancy.admin_personas` bypasses the tenant filter at
runtime. If the same persona is also bound to a `scope: ... as:` rule, that
rule is dead for the persona — the apparent row-filtering is a silent
cross-tenant leak. `validate_admin_personas_scope_conflict` must reject it.
"""

from dazzle.core import ir
from dazzle.core.validator import validate_admin_personas_scope_conflict


def _appspec(admin_personas: list[str], scope_personas: list[str]) -> ir.AppSpec:
    entity = ir.EntitySpec(
        name="Invoice",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            )
        ],
        access=ir.AccessSpec(
            scopes=[ir.ScopeRule(operation=ir.PermissionKind.READ, personas=scope_personas)]
        ),
    )
    return ir.AppSpec(
        name="Test",
        domain=ir.DomainSpec(entities=[entity]),
        tenancy=ir.TenancySpec(admin_personas=admin_personas),
    )


def test_conflict_is_rejected() -> None:
    errors, _ = validate_admin_personas_scope_conflict(
        _appspec(admin_personas=["tenant_admin"], scope_personas=["tenant_admin"])
    )
    assert errors, "a persona in both admin_personas and a scope rule must error"
    assert "tenant_admin" in errors[0]


def test_no_overlap_is_clean() -> None:
    errors, _ = validate_admin_personas_scope_conflict(
        _appspec(admin_personas=["super_admin"], scope_personas=["staff"])
    )
    assert errors == []


def test_no_admin_personas_is_clean() -> None:
    errors, _ = validate_admin_personas_scope_conflict(
        _appspec(admin_personas=[], scope_personas=["staff"])
    )
    assert errors == []
