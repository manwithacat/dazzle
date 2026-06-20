"""MembershipRecord model + AuthContext.active_membership (auth Plan 1a)."""

import pytest
from pydantic import ValidationError

from dazzle.http.runtime.auth.models import (
    AuthContext,
    MembershipRecord,
    OrganizationRecord,
    UserRecord,
)


class TestMembershipRecord:
    def test_minimal_construction_defaults(self) -> None:
        m = MembershipRecord(id="m-1", tenant_id="t-1", identity_id="u-1")
        assert m.id == "m-1"
        assert m.tenant_id == "t-1"
        assert m.identity_id == "u-1"
        assert m.roles == []
        assert m.status == "active"
        assert m.invited_by is None

    def test_roles_and_status_round_trip(self) -> None:
        m = MembershipRecord(
            id="m-2",
            tenant_id="t-1",
            identity_id="u-1",
            roles=["admin", "member"],
            status="invited",
            invited_by="u-9",
        )
        assert m.roles == ["admin", "member"]
        assert m.status == "invited"
        assert m.invited_by == "u-9"

    def test_is_frozen(self) -> None:
        m = MembershipRecord(id="m-3", tenant_id="t-1", identity_id="u-1")
        with pytest.raises(ValidationError):
            m.status = "suspended"  # type: ignore[misc]


class TestAuthContextActiveMembership:
    def _user(self) -> UserRecord:
        return UserRecord(email="a@b.test", password_hash="x", roles=["legacy_role"])

    def test_active_membership_defaults_none(self) -> None:
        ctx = AuthContext(user=self._user(), is_authenticated=True, roles=["legacy_role"])
        assert ctx.active_membership is None
        assert ctx.effective_roles == ["legacy_role"]

    def test_effective_roles_prefer_membership(self) -> None:
        m = MembershipRecord(id="m-1", tenant_id="t-1", identity_id="u-1", roles=["admin"])
        ctx = AuthContext(
            user=self._user(),
            is_authenticated=True,
            roles=["legacy_role"],
            active_membership=m,
        )
        assert ctx.effective_roles == ["admin"]

    def test_effective_roles_unauthenticated_empty(self) -> None:
        assert AuthContext().effective_roles == []


class TestOrganizationRecord:
    def test_minimal_construction_defaults(self) -> None:
        o = OrganizationRecord(id="o-1", slug="default", name="Default")
        assert o.id == "o-1"
        assert o.slug == "default"
        assert o.name == "Default"
        assert o.status == "active"
        assert o.is_test is False

    def test_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        o = OrganizationRecord(id="o-2", slug="acme", name="Acme")
        with pytest.raises(ValidationError):
            o.status = "suspended"  # type: ignore[misc]
