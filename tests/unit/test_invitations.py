"""org_admin_roles authorization predicate + InvitationError (auth Plan 3a)."""

from dazzle.back.runtime.auth.invitations import InvitationError, may_manage_members


def test_may_manage_members_requires_active_membership_role_in_admin_set() -> None:
    # No admin roles configured → nobody may invite (fail-closed).
    assert may_manage_members(["owner"], org_admin_roles=[]) is False
    # Role intersects the configured admin set → allowed.
    assert may_manage_members(["owner", "member"], org_admin_roles=["owner", "admin"]) is True
    # No intersection → denied.
    assert may_manage_members(["member"], org_admin_roles=["owner", "admin"]) is False
    # Empty roles → denied.
    assert may_manage_members([], org_admin_roles=["owner"]) is False


def test_invitation_error_carries_reason() -> None:
    e = InvitationError("expired", "invitation expired")
    assert e.reason == "expired"
    assert "expired" in str(e)
