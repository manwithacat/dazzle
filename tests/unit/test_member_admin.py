"""Last-admin orphan guard + admin-count helpers (auth Plan 3b)."""

from dazzle.back.runtime.auth.member_admin import active_admins, would_orphan_org

# roster rows: (membership_id, roles, status)
_ADMIN_ROLES = ["owner", "admin"]


def test_active_admins_counts_only_active_members_with_an_admin_role() -> None:
    roster = [
        ("m1", ["owner"], "active"),
        ("m2", ["member"], "active"),
        ("m3", ["admin"], "suspended"),  # suspended → not an active admin
    ]
    assert active_admins(roster, _ADMIN_ROLES) == ["m1"]


def test_removing_the_last_admin_would_orphan() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["member"], "active")]
    assert would_orphan_org(roster, "m1", new_roles=None, admin_roles=_ADMIN_ROLES) is True


def test_removing_a_non_last_admin_is_fine() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["admin"], "active")]
    assert would_orphan_org(roster, "m1", new_roles=None, admin_roles=_ADMIN_ROLES) is False


def test_removing_a_non_admin_never_orphans() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["member"], "active")]
    assert would_orphan_org(roster, "m2", new_roles=None, admin_roles=_ADMIN_ROLES) is False


def test_demoting_the_last_admin_would_orphan() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["member"], "active")]
    assert would_orphan_org(roster, "m1", new_roles=["member"], admin_roles=_ADMIN_ROLES) is True


def test_demotion_that_keeps_another_admin_is_fine() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["admin"], "active")]
    assert would_orphan_org(roster, "m1", new_roles=["member"], admin_roles=_ADMIN_ROLES) is False


def test_no_guard_when_org_already_has_no_admins() -> None:
    roster = [("m1", ["member"], "active")]
    assert would_orphan_org(roster, "m1", new_roles=None, admin_roles=_ADMIN_ROLES) is False


def test_guards_accept_a_frozenset_admin_set() -> None:
    roster = [("m1", ["it_admin"], "active"), ("m2", ["member"], "active")]
    assert active_admins(roster, frozenset({"it_admin"})) == ["m1"]
    assert (
        would_orphan_org(roster, "m1", new_roles=None, admin_roles=frozenset({"it_admin"})) is True
    )
