"""InvitationError (auth Plan 3a). The manage-members authorization predicate moved to
``auth/admin_policy.py`` (capability ``manage_members``) — see ``tests/unit/test_admin_policy.py``."""

from dazzle.back.runtime.auth.invitations import InvitationError


def test_invitation_error_carries_reason() -> None:
    e = InvitationError("expired", "invitation expired")
    assert e.reason == "expired"
    assert "expired" in str(e)
