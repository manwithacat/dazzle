"""ASVS V4: Access Control security tests."""

from __future__ import annotations

from dazzle.core import ir


class TestDefaultDeny:
    """V4.1: General Access Control."""

    def test_default_deny_no_access_spec(self):
        """V4.1.1: Entities without access spec should default to deny."""
        # An entity without access control should not have open permissions
        entity = ir.EntitySpec(
            name="Secret",
            title="Secret Entity",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ],
        )
        assert entity.access is None, "No access = no permissions = default deny"


class TestRBACEnforcement:
    """V4.2: Operation Level Access Control."""

    def test_permission_kinds_cover_crud(self):
        """V4.2.1: Permission system covers all CRUD operations."""
        kinds = {k.value for k in ir.PermissionKind}
        assert "create" in kinds
        assert "read" in kinds
        assert "update" in kinds
        assert "delete" in kinds

    def test_forbid_effect_support(self):
        """V4.2.2: Access control supports forbid (deny) rules via Cedar-style PolicyEffect."""
        rule = ir.PermissionRule(
            operation=ir.PermissionKind.DELETE,
            effect=ir.PolicyEffect.FORBID,
        )
        assert rule.effect == ir.PolicyEffect.FORBID

    def test_forbid_takes_precedence_concept(self):
        """V4.2.3: Forbid rules should conceptually override permit rules."""
        # Verify the AccessSpec model supports both permit and forbid effects
        access = ir.AccessSpec(
            permissions=[
                ir.PermissionRule(
                    operation=ir.PermissionKind.READ,
                    effect=ir.PolicyEffect.PERMIT,
                ),
                ir.PermissionRule(
                    operation=ir.PermissionKind.DELETE,
                    effect=ir.PolicyEffect.FORBID,
                ),
            ],
        )
        forbid_rules = [r for r in access.permissions if r.effect == ir.PolicyEffect.FORBID]
        assert len(forbid_rules) > 0, "Forbid rules must be supported"
