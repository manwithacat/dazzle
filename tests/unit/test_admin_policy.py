"""Tests for the admin-capability authorization value object (#1342-adjacent)."""

from dazzle.back.runtime.auth.admin_policy import (
    CAPABILITIES,
    AdminPolicy,
    unknown_admin_personas,
)


def test_capabilities_are_the_two_framework_capabilities():
    assert CAPABILITIES == ("manage_members", "manage_connections")


def test_no_map_falls_back_to_org_admin_roles_for_every_capability():
    p = AdminPolicy.from_config(org_admin_roles=["org_admin"], admin_capabilities={})
    for cap in CAPABILITIES:
        assert p.may(cap, ["org_admin"]) is True
        assert p.may(cap, ["member"]) is False  # default-deny


def test_explicit_map_is_honored_per_capability():
    p = AdminPolicy.from_config(
        org_admin_roles=["org_admin"],
        admin_capabilities={"manage_connections": ["it_admin"]},
    )
    # mapped capability uses its own set
    assert p.may("manage_connections", ["it_admin"]) is True
    assert p.may("manage_connections", ["org_admin"]) is False
    # an UNLISTED capability falls back to org_admin_roles (not empty)
    assert p.may("manage_members", ["org_admin"]) is True
    assert p.may("manage_members", ["it_admin"]) is False


def test_fail_closed_when_nothing_configured():
    p = AdminPolicy.from_config(org_admin_roles=[], admin_capabilities={})
    assert p.may("manage_members", ["org_admin"]) is False
    assert p.may("manage_connections", ["anyone"]) is False


def test_unknown_capability_denies():
    p = AdminPolicy.from_config(org_admin_roles=["org_admin"], admin_capabilities={})
    assert p.may("manage_billing", ["org_admin"]) is False


def test_roles_for_returns_resolved_set():
    p = AdminPolicy.from_config(
        org_admin_roles=["org_admin"],
        admin_capabilities={"manage_members": ["business_admin"]},
    )
    assert p.roles_for("manage_members") == frozenset({"business_admin"})
    assert p.roles_for("manage_connections") == frozenset({"org_admin"})  # fallback
    assert p.roles_for("nope") == frozenset()


def test_empty_role_list_in_map_falls_back_not_locks_out():
    # an explicitly-empty list is treated as "unset" → fall back to org_admin_roles
    p = AdminPolicy.from_config(
        org_admin_roles=["org_admin"], admin_capabilities={"manage_members": []}
    )
    assert p.may("manage_members", ["org_admin"]) is True


def test_unknown_admin_personas_flags_typos():
    declared = {"org_admin", "it_admin", "business_admin"}
    caps = {"manage_connections": ["it_admin", "typo_admin"], "manage_members": ["business_admin"]}
    assert unknown_admin_personas(caps, declared) == {"typo_admin"}
    assert unknown_admin_personas({}, declared) == set()
