"""Tests for Cedar-style access evaluator.

Validates the three-rule Cedar evaluation semantics:
1. Any FORBID match → DENY
2. Any PERMIT match → ALLOW
3. No matching rules → DENY (default-deny)

Also tests persona scoping, superuser bypass, and backward compatibility.
"""

from __future__ import annotations

from dazzle_back.runtime.access_evaluator import (
    AccessDecision,
    AccessRuntimeContext,
    evaluate_permission,
    evaluate_permission_bool,
    evaluate_visibility,
    filter_visible_records,
)
from dazzle_back.specs.auth import (
    AccessAuthContext,
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    AccessPolicyEffect,
    EntityAccessSpec,
    PermissionRuleSpec,
    VisibilityRuleSpec,
)

# =============================================================================
# Fixtures
# =============================================================================


def _ctx(
    user_id: str | None = "user-1",
    roles: list[str] | None = None,
    is_superuser: bool = False,
) -> AccessRuntimeContext:
    return AccessRuntimeContext(
        user_id=user_id,
        roles=roles or [],
        is_superuser=is_superuser,
    )


def _permit_rule(
    op: AccessOperationKind,
    condition: AccessConditionSpec | None = None,
    personas: list[str] | None = None,
) -> PermissionRuleSpec:
    return PermissionRuleSpec(
        operation=op,
        effect=AccessPolicyEffect.PERMIT,
        condition=condition,
        personas=personas or [],
    )


def _forbid_rule(
    op: AccessOperationKind,
    condition: AccessConditionSpec | None = None,
    personas: list[str] | None = None,
) -> PermissionRuleSpec:
    return PermissionRuleSpec(
        operation=op,
        effect=AccessPolicyEffect.FORBID,
        condition=condition,
        personas=personas or [],
    )


def _role_check(role_name: str) -> AccessConditionSpec:
    return AccessConditionSpec(kind="role_check", role_name=role_name)


def _owner_check() -> AccessConditionSpec:
    return AccessConditionSpec(
        kind="comparison",
        field="owner_id",
        comparison_op=AccessComparisonKind.EQUALS,
        value="current_user",
    )


def _status_check(status: str) -> AccessConditionSpec:
    return AccessConditionSpec(
        kind="comparison",
        field="status",
        comparison_op=AccessComparisonKind.EQUALS,
        value=status,
    )


# =============================================================================
# AccessDecision
# =============================================================================


class TestAccessDecision:
    def test_bool_true(self) -> None:
        d = AccessDecision(allowed=True, matched_policy="test", effect="permit")
        assert bool(d) is True
        assert d.allowed is True

    def test_bool_false(self) -> None:
        d = AccessDecision(allowed=False, matched_policy="denied", effect="forbid")
        assert bool(d) is False
        assert d.allowed is False

    def test_repr(self) -> None:
        d = AccessDecision(allowed=True, matched_policy="superuser_bypass")
        assert "superuser_bypass" in repr(d)


# =============================================================================
# Cedar Rule 1: FORBID takes precedence
# =============================================================================


class TestForbidTakesPrecedence:
    def test_forbid_overrides_permit(self) -> None:
        """Even when a PERMIT rule matches, a matching FORBID rule wins."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.DELETE, _role_check("admin")),
                _forbid_rule(AccessOperationKind.DELETE, _role_check("intern")),
            ]
        )
        # User is both admin AND intern — forbid should win
        ctx = _ctx(roles=["admin", "intern"])
        decision = evaluate_permission(spec, AccessOperationKind.DELETE, {}, ctx)
        assert not decision.allowed
        assert decision.effect == "forbid"

    def test_forbid_with_condition(self) -> None:
        """Forbid rule with condition: nobody can update archived records."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.UPDATE, _role_check("admin")),
                _forbid_rule(AccessOperationKind.UPDATE, _status_check("archived")),
            ]
        )
        ctx = _ctx(roles=["admin"])
        record = {"status": "archived", "owner_id": "user-1"}
        decision = evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx)
        assert not decision.allowed
        assert decision.effect == "forbid"

    def test_forbid_condition_not_met_permits(self) -> None:
        """If forbid condition doesn't match, permit rules apply."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.UPDATE, _role_check("admin")),
                _forbid_rule(AccessOperationKind.UPDATE, _status_check("archived")),
            ]
        )
        ctx = _ctx(roles=["admin"])
        record = {"status": "active"}
        decision = evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx)
        assert decision.allowed
        assert decision.effect == "permit"


# =============================================================================
# Cedar Rule 2: PERMIT allows
# =============================================================================


class TestPermitAllows:
    def test_permit_with_role_check(self) -> None:
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.CREATE, _role_check("editor")),
            ]
        )
        ctx = _ctx(roles=["editor"])
        decision = evaluate_permission(spec, AccessOperationKind.CREATE, None, ctx)
        assert decision.allowed
        assert decision.effect == "permit"

    def test_permit_with_owner_check(self) -> None:
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.UPDATE, _owner_check()),
            ]
        )
        ctx = _ctx(user_id="user-1")
        record = {"owner_id": "user-1"}
        decision = evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx)
        assert decision.allowed

    def test_permit_owner_mismatch(self) -> None:
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.UPDATE, _owner_check()),
            ]
        )
        ctx = _ctx(user_id="user-2")
        record = {"owner_id": "user-1"}
        decision = evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx)
        assert not decision.allowed
        assert decision.effect == "default"

    def test_permit_no_condition(self) -> None:
        """Permit rule with no condition matches any authenticated user."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.READ),
            ]
        )
        ctx = _ctx()
        decision = evaluate_permission(spec, AccessOperationKind.READ, {}, ctx)
        assert decision.allowed

    def test_permit_unauthenticated_denied(self) -> None:
        """Permit rule with require_auth blocks unauthenticated users."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.READ),
            ]
        )
        ctx = _ctx(user_id=None)
        decision = evaluate_permission(spec, AccessOperationKind.READ, {}, ctx)
        assert not decision.allowed


# =============================================================================
# Cedar Rule 3: Default deny
# =============================================================================


class TestDefaultDeny:
    def test_no_matching_rules_denies(self) -> None:
        """When rules exist but none match, default-deny applies."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.CREATE, _role_check("admin")),
            ]
        )
        # User is not admin, tries CREATE
        ctx = _ctx(roles=["viewer"])
        decision = evaluate_permission(spec, AccessOperationKind.CREATE, None, ctx)
        assert not decision.allowed
        assert decision.effect == "default"

    def test_wrong_operation_denies(self) -> None:
        """Rules for CREATE don't grant DELETE."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.CREATE, _role_check("admin")),
            ]
        )
        ctx = _ctx(roles=["admin"])
        decision = evaluate_permission(spec, AccessOperationKind.DELETE, {}, ctx)
        assert not decision.allowed

    def test_no_rules_authenticated_allows_write(self) -> None:
        """Backward compat: no rules + authenticated → allow writes."""
        spec = EntityAccessSpec()
        ctx = _ctx()
        decision = evaluate_permission(spec, AccessOperationKind.CREATE, None, ctx)
        assert decision.allowed
        assert decision.matched_policy == "no_rules_authenticated"

    def test_no_rules_unauthenticated_denies_write(self) -> None:
        """No rules + unauthenticated → deny writes."""
        spec = EntityAccessSpec()
        ctx = _ctx(user_id=None)
        decision = evaluate_permission(spec, AccessOperationKind.CREATE, None, ctx)
        assert not decision.allowed

    def test_no_rules_allows_read(self) -> None:
        """No rules at all → allow reads."""
        spec = EntityAccessSpec()
        ctx = _ctx(user_id=None)
        decision = evaluate_permission(spec, AccessOperationKind.READ, {}, ctx)
        assert decision.allowed


# =============================================================================
# Persona Scoping
# =============================================================================


class TestPersonaScoping:
    def test_persona_scoped_rule_matches(self) -> None:
        """Rule scoped to 'admin' persona matches when user has admin role."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.DELETE, personas=["admin"]),
            ]
        )
        ctx = _ctx(roles=["admin"])
        decision = evaluate_permission(spec, AccessOperationKind.DELETE, {}, ctx)
        assert decision.allowed

    def test_persona_scoped_rule_no_match(self) -> None:
        """Rule scoped to 'admin' doesn't match for 'editor'."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.DELETE, personas=["admin"]),
            ]
        )
        ctx = _ctx(roles=["editor"])
        decision = evaluate_permission(spec, AccessOperationKind.DELETE, {}, ctx)
        assert not decision.allowed

    def test_multiple_persona_scopes(self) -> None:
        """Rule scoped to ['admin', 'manager'] matches either."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.DELETE, personas=["admin", "manager"]),
            ]
        )
        ctx = _ctx(roles=["manager"])
        decision = evaluate_permission(spec, AccessOperationKind.DELETE, {}, ctx)
        assert decision.allowed


# =============================================================================
# Superuser Bypass
# =============================================================================


class TestSuperuserBypass:
    def test_superuser_bypasses_forbid(self) -> None:
        spec = EntityAccessSpec(
            permissions=[
                _forbid_rule(AccessOperationKind.DELETE),
            ]
        )
        ctx = _ctx(is_superuser=True)
        decision = evaluate_permission(spec, AccessOperationKind.DELETE, {}, ctx)
        assert decision.allowed
        assert decision.matched_policy == "superuser_bypass"

    def test_superuser_bypasses_default_deny(self) -> None:
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.CREATE, _role_check("admin")),
            ]
        )
        ctx = _ctx(is_superuser=True, roles=[])
        decision = evaluate_permission(spec, AccessOperationKind.DELETE, {}, ctx)
        assert decision.allowed


# =============================================================================
# Logical Conditions
# =============================================================================


class TestLogicalConditions:
    def test_or_condition(self) -> None:
        """owner_id = current_user OR role(admin)"""
        or_cond = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.OR,
            logical_left=_owner_check(),
            logical_right=_role_check("admin"),
        )
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.UPDATE, or_cond),
            ]
        )
        # Owner matches
        ctx = _ctx(user_id="user-1")
        record = {"owner_id": "user-1"}
        assert evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx).allowed

        # Admin matches
        ctx = _ctx(user_id="user-2", roles=["admin"])
        assert evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx).allowed

        # Neither
        ctx = _ctx(user_id="user-2", roles=["viewer"])
        assert not evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx).allowed

    def test_and_condition(self) -> None:
        """owner_id = current_user AND role(editor)"""
        and_cond = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.AND,
            logical_left=_owner_check(),
            logical_right=_role_check("editor"),
        )
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.UPDATE, and_cond),
            ]
        )
        # Owner + editor → allow
        ctx = _ctx(user_id="user-1", roles=["editor"])
        record = {"owner_id": "user-1"}
        assert evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx).allowed

        # Owner without editor → deny
        ctx = _ctx(user_id="user-1", roles=["viewer"])
        assert not evaluate_permission(spec, AccessOperationKind.UPDATE, record, ctx).allowed


# =============================================================================
# Backward Compatibility
# =============================================================================


class TestBackwardCompat:
    def test_evaluate_permission_bool(self) -> None:
        """evaluate_permission_bool returns plain bool."""
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.CREATE, _role_check("admin")),
            ]
        )
        ctx = _ctx(roles=["admin"])
        assert evaluate_permission_bool(spec, AccessOperationKind.CREATE, None, ctx) is True

    def test_visibility_rules_still_work(self) -> None:
        """Visibility rules remain functional."""
        spec = EntityAccessSpec(
            visibility=[
                VisibilityRuleSpec(
                    context=AccessAuthContext.AUTHENTICATED,
                    condition=_owner_check(),
                ),
            ]
        )
        ctx = _ctx(user_id="user-1")
        record = {"owner_id": "user-1"}
        assert evaluate_visibility(spec, record, ctx) is True

        ctx = _ctx(user_id="user-2")
        assert evaluate_visibility(spec, record, ctx) is False

    def test_filter_visible_records(self) -> None:
        spec = EntityAccessSpec(
            visibility=[
                VisibilityRuleSpec(
                    context=AccessAuthContext.AUTHENTICATED,
                    condition=_owner_check(),
                ),
            ]
        )
        ctx = _ctx(user_id="user-1")
        records = [
            {"id": "1", "owner_id": "user-1"},
            {"id": "2", "owner_id": "user-2"},
            {"id": "3", "owner_id": "user-1"},
        ]
        visible = filter_visible_records(spec, records, ctx)
        assert len(visible) == 2
        assert all(r["owner_id"] == "user-1" for r in visible)


# =============================================================================
# Mixed Permit + Forbid Rules
# =============================================================================


class TestMixedRules:
    def test_complex_rbac_scenario(self) -> None:
        """
        Real-world scenario:
        - Editors and admins can update
        - Interns cannot update
        - Nobody can update archived records
        """
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.UPDATE, _role_check("editor")),
                _permit_rule(AccessOperationKind.UPDATE, _role_check("admin")),
                _forbid_rule(AccessOperationKind.UPDATE, _role_check("intern")),
                _forbid_rule(AccessOperationKind.UPDATE, _status_check("archived")),
            ]
        )

        # Editor, active record → allow
        ctx = _ctx(roles=["editor"])
        assert evaluate_permission(
            spec, AccessOperationKind.UPDATE, {"status": "active"}, ctx
        ).allowed

        # Admin, active record → allow
        ctx = _ctx(roles=["admin"])
        assert evaluate_permission(
            spec, AccessOperationKind.UPDATE, {"status": "active"}, ctx
        ).allowed

        # Intern (even if also editor) → deny
        ctx = _ctx(roles=["editor", "intern"])
        assert not evaluate_permission(
            spec, AccessOperationKind.UPDATE, {"status": "active"}, ctx
        ).allowed

        # Any role, archived record → deny
        ctx = _ctx(roles=["admin"])
        assert not evaluate_permission(
            spec, AccessOperationKind.UPDATE, {"status": "archived"}, ctx
        ).allowed

        # Viewer (no permit rule) → deny
        ctx = _ctx(roles=["viewer"])
        assert not evaluate_permission(
            spec, AccessOperationKind.UPDATE, {"status": "active"}, ctx
        ).allowed
