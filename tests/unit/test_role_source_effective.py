"""Authorization sites source roles from active membership (auth Plan 1b).

The runtime `permit:`/`scope:` decisions must read `auth_context.effective_roles`
(the active membership's roles, membership-first per Plan 1a) rather than the
global `user.roles`. The dependency gates already switched in 1a; this pins the
route_generator + policy switchover.
"""

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord


def _ctx_with_membership(membership_roles: list[str], user_roles: list[str]) -> AuthContext:
    return AuthContext(
        user=UserRecord(email="a@b.test", password_hash="x", roles=user_roles),
        is_authenticated=True,
        roles=user_roles,
        active_membership=MembershipRecord(
            id="m-1", tenant_id="t-1", identity_id="u-1", roles=membership_roles
        ),
    )


def test_build_access_context_uses_membership_roles() -> None:
    from dazzle.http.runtime.route_generator import _build_access_context

    # Membership says admin; legacy user.roles is empty — admin must win.
    ctx = _ctx_with_membership(membership_roles=["admin"], user_roles=[])
    _user, runtime_ctx = _build_access_context(ctx)
    assert "admin" in set(runtime_ctx.roles)


def test_build_access_context_unauthenticated_has_no_roles() -> None:
    from dazzle.http.runtime.route_generator import _build_access_context

    _user, runtime_ctx = _build_access_context(AuthContext())
    assert list(runtime_ctx.roles) == []


def test_cedar_row_filters_use_membership_roles() -> None:
    """A role-gated unrestricted permit is recognised from membership roles."""
    from dazzle.http.runtime.route_generator import _extract_cedar_row_filters

    spec = SimpleNamespace(
        permissions=[
            SimpleNamespace(
                operation=SimpleNamespace(value="list"),
                effect=SimpleNamespace(value="permit"),
                condition=None,
                personas=["admin"],
            )
        ]
    )
    ctx = _ctx_with_membership(membership_roles=["admin"], user_roles=[])
    # Admin (from membership) → unrestricted permit → no row filters.
    assert _extract_cedar_row_filters(spec, user_id="u-1", auth_context=ctx) == {}


def test_should_bypass_tenant_filter_uses_membership_roles() -> None:
    from dazzle.http.runtime.route_generator import _should_bypass_tenant_filter

    ctx = _ctx_with_membership(membership_roles=["admin"], user_roles=[])
    # admin is an admin_persona → bypass applies, sourced from membership roles.
    assert _should_bypass_tenant_filter(ctx, ["admin"]) is True
    # A user whose membership lacks the admin persona does not bypass.
    ctx2 = _ctx_with_membership(membership_roles=["member"], user_roles=["admin"])
    assert _should_bypass_tenant_filter(ctx2, ["admin"]) is False


def test_policy_check_entity_op_sources_membership_roles(monkeypatch) -> None:
    """check_entity_op's permit gate reads effective_roles off the request's
    auth_context (membership-first), not the global user.roles."""
    import asyncio

    import dazzle.http.runtime.policy as policy_mod

    captured: dict[str, object] = {}

    def _fake_permit_passes(spec, op, user_roles, user_id):  # noqa: ANN001
        captured["roles"] = list(user_roles)
        return False  # deny → raises 403 after capture; avoids the scope gate

    monkeypatch.setattr(policy_mod, "_permit_passes", _fake_permit_passes, raising=True)

    ctx = _ctx_with_membership(membership_roles=["admin"], user_roles=["legacy"])
    info = SimpleNamespace(cedar_access_spec=SimpleNamespace())
    registry = SimpleNamespace(get=lambda name: info)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(policy_registry=registry)),
        state=SimpleNamespace(auth_context=ctx),
    )

    from fastapi import HTTPException

    try:
        asyncio.run(policy_mod.check_entity_op(request, "Note", "read"))
    except HTTPException:
        pass
    assert captured.get("roles") == ["admin"]


def test_list_403_detail_reports_effective_roles_not_global() -> None:
    """#1406: the LIST permit-deny 403 `detail.current_roles` must report the
    *effective* (membership) roles the decision used, not the empty global
    user.roles. A membership-scoped session has roles only on the membership."""
    import asyncio
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    from dazzle.http.runtime.handlers.list_handlers import _list_handler_body
    from dazzle.http.specs.auth import (
        AccessConditionSpec,
        AccessOperationKind,
        AccessPolicyEffect,
        EntityAccessSpec,
        PermissionRuleSpec,
    )

    # LIST is permitted for "admin" only; this actor's membership grants "viewer".
    spec = EntityAccessSpec(
        permissions=[
            PermissionRuleSpec(
                operation=AccessOperationKind.LIST,
                effect=AccessPolicyEffect.PERMIT,
                condition=AccessConditionSpec(kind="role_check", role_name="admin"),
            )
        ]
    )
    # Membership says viewer; legacy global user.roles is empty (per-org model).
    ctx = _ctx_with_membership(membership_roles=["viewer"], user_roles=[])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            _list_handler_body(
                service=MagicMock(),
                access_spec=None,
                is_authenticated=True,
                user_id="u-1",
                request=MagicMock(),
                page=1,
                page_size=20,
                sort=None,
                dir="asc",
                search=None,
                cedar_access_spec=spec,
                auth_context=ctx,
                entity_name="Secret",
            )
        )

    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    # The fix: effective membership roles, NOT the empty global user.roles.
    assert detail["current_roles"] == ["viewer"]
