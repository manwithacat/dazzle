"""#1404 Phase B — apex tenant discovery decision mapper (pure)."""

from __future__ import annotations

from dazzle.back.runtime.auth.apex_discovery import (
    NO_ORGS_PATH,
    PICKER_PATH,
    resolve_apex_redirect,
)
from dazzle.back.runtime.auth.models import MembershipRecord


def _m(mid: str, tid: str, status: str = "active") -> MembershipRecord:
    return MembershipRecord(id=mid, tenant_id=tid, identity_id="u-1", status=status)


def _slug_map(mapping: dict[str, str]):
    return lambda tid: mapping.get(tid)


class TestResolveApexRedirect:
    def test_single_membership_redirects_to_org_host(self) -> None:
        url = resolve_apex_redirect(
            [_m("m-1", "t-1")],
            domain="example.com",
            slug_for_tenant=_slug_map({"t-1": "acme"}),
            memberships_required=True,
        )
        assert url == "https://acme.example.com/"

    def test_multiple_memberships_go_to_picker(self) -> None:
        url = resolve_apex_redirect(
            [_m("m-1", "t-1"), _m("m-2", "t-2")],
            domain="example.com",
            slug_for_tenant=_slug_map({"t-1": "acme", "t-2": "globex"}),
            memberships_required=True,
        )
        assert url == PICKER_PATH

    def test_no_memberships_goes_to_no_orgs_when_gated(self) -> None:
        url = resolve_apex_redirect(
            [],
            domain="example.com",
            slug_for_tenant=_slug_map({}),
            memberships_required=True,
        )
        assert url == NO_ORGS_PATH

    def test_no_memberships_passes_through_when_ungated(self) -> None:
        # #1418 interaction: an ungated app's apex is its own landing — no redirect.
        url = resolve_apex_redirect(
            [],
            domain="example.com",
            slug_for_tenant=_slug_map({}),
            memberships_required=False,
        )
        assert url is None

    def test_suspended_membership_is_not_active(self) -> None:
        # One suspended membership → no active orgs → no-orgs (gated).
        url = resolve_apex_redirect(
            [_m("m-1", "t-1", status="suspended")],
            domain="example.com",
            slug_for_tenant=_slug_map({"t-1": "acme"}),
            memberships_required=True,
        )
        assert url == NO_ORGS_PATH

    def test_unresolvable_slug_fails_safe_to_none(self) -> None:
        # Single membership but the tenant_id maps to no slug → don't redirect.
        url = resolve_apex_redirect(
            [_m("m-1", "t-1")],
            domain="example.com",
            slug_for_tenant=_slug_map({}),  # t-1 not present
            memberships_required=True,
        )
        assert url is None

    def test_invalid_slug_is_rejected(self) -> None:
        # A slug that fails validation must never be interpolated into a redirect.
        url = resolve_apex_redirect(
            [_m("m-1", "t-1")],
            domain="example.com",
            slug_for_tenant=_slug_map({"t-1": "ev/il.attacker.com"}),
            memberships_required=True,
        )
        assert url is None
