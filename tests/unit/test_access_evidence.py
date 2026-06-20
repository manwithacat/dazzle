"""Pure point-in-time replay + JML classification + control map (auth Plan 2b)."""

from datetime import datetime

from dazzle.http.runtime.auth.membership_events import MembershipEvent, MembershipEventType
from dazzle.rbac.access_evidence import (
    ACCESS_EVIDENCE_CONTROLS,
    classify_jml,
    replay_roster,
)


def _evt(
    seq, etype, mid, *, roles_after=None, status_after=None, identity="u-1", when="2026-01-01"
):
    return MembershipEvent(
        id=f"e{seq}",
        event_type=etype,
        membership_id=mid,
        tenant_id="org-1",
        identity_id=identity,
        actor_id=None,
        roles_before=None,
        roles_after=roles_after,
        status_before=None,
        status_after=status_after,
        reason=None,
        created_at=datetime.fromisoformat(f"{when}T00:00:00+00:00"),
        seq=seq,
    )


def test_replay_builds_roster_from_provision_and_role_change() -> None:
    events = [
        _evt(
            1, MembershipEventType.PROVISIONED, "m1", roles_after=["member"], status_after="active"
        ),
        _evt(2, MembershipEventType.ROLE_CHANGED, "m1", roles_after=["member", "approver"]),
    ]
    roster = replay_roster(events)
    assert len(roster) == 1
    assert roster["m1"].roles == ["member", "approver"]
    assert roster["m1"].status == "active"


def test_replay_drops_removed_membership() -> None:
    events = [
        _evt(
            1, MembershipEventType.PROVISIONED, "m1", roles_after=["member"], status_after="active"
        ),
        _evt(2, MembershipEventType.REMOVED, "m1", status_after="removed"),
    ]
    assert replay_roster(events) == {}  # leaver gone from the roster


def test_replay_keeps_suspended_member_with_status() -> None:
    events = [
        _evt(
            1, MembershipEventType.PROVISIONED, "m1", roles_after=["member"], status_after="active"
        ),
        _evt(2, MembershipEventType.SUSPENDED, "m1", status_after="suspended"),
    ]
    roster = replay_roster(events)
    assert roster["m1"].status == "suspended"  # still has a grant, but paused


def test_replay_reprovisioned_identity_is_a_distinct_membership() -> None:
    events = [
        _evt(
            1, MembershipEventType.PROVISIONED, "m1", roles_after=["member"], status_after="active"
        ),
        _evt(2, MembershipEventType.REMOVED, "m1", status_after="removed"),
        _evt(
            3, MembershipEventType.PROVISIONED, "m2", roles_after=["admin"], status_after="active"
        ),
    ]
    roster = replay_roster(events)
    assert set(roster) == {"m2"}  # m1 removed; m2 is the new grant
    assert roster["m2"].roles == ["admin"]


def test_classify_jml_buckets_event_kinds() -> None:
    assert classify_jml(MembershipEventType.PROVISIONED) == "joiner"
    assert classify_jml(MembershipEventType.ROLE_CHANGED) == "mover"
    assert classify_jml(MembershipEventType.REACTIVATED) == "mover"
    assert classify_jml(MembershipEventType.SUSPENDED) == "leaver"
    assert classify_jml(MembershipEventType.REMOVED) == "leaver"


def test_control_map_covers_every_event_kind_and_the_roster() -> None:
    for kind in (
        MembershipEventType.PROVISIONED,
        MembershipEventType.ROLE_CHANGED,
        MembershipEventType.SUSPENDED,
        MembershipEventType.REACTIVATED,
        MembershipEventType.REMOVED,
    ):
        assert ACCESS_EVIDENCE_CONTROLS[kind]  # non-empty control list
    assert ACCESS_EVIDENCE_CONTROLS["roster"]  # the as-of access matrix maps too


def test_render_access_review_markdown_has_sections() -> None:
    from dazzle.rbac.access_evidence import (
        AccessReview,
        ChainAttestation,
        JmlEntry,
        MemberSnapshot,
        OrgAccessSnapshot,
    )
    from dazzle.rbac.report import render_access_review_markdown

    review = AccessReview(
        tenant_id="org-1",
        generated_at="2026-06-05T00:00:00+00:00",
        snapshot=OrgAccessSnapshot(
            "org-1",
            None,
            "current",
            [MemberSnapshot("m1", "u-1", ["admin"], "active", "2026-01-01T00:00:00+00:00")],
        ),
        jml=[
            JmlEntry(
                "joiner",
                "provisioned",
                "m1",
                "u-1",
                None,
                ["admin"],
                None,
                "active",
                "admin-1",
                None,
                "2026-01-01T00:00:00+00:00",
                ["CC6.2", "A.5.16"],
            ),
        ],
        period_since=None,
        period_until=None,
        chain=ChainAttestation(ok=True, total_rows=1, mismatched_count=0, first_mismatch_id=None),
    )
    md = render_access_review_markdown(review)
    assert "# Access Review" in md
    assert "org-1" in md
    assert "## Membership Roster" in md
    assert "## Access Changes (Joiner / Mover / Leaver)" in md
    assert "## Control Coverage" in md
    assert "CC6.2" in md
    assert "Integrity" in md and "INTACT" in md  # chain ok → INTACT (honestly scoped)
    # C1: the attestation must not over-claim — the tail-truncation caveat is present.
    assert "tail truncation" in md.lower()


def test_normalize_instant_rejects_naive_and_garbage_and_normalizes_offset() -> None:
    import pytest

    from dazzle.rbac.access_evidence import _normalize_instant

    assert _normalize_instant(None) is None
    # A non-UTC offset is normalized to UTC so the lexical TEXT compare is sound.
    assert _normalize_instant("2026-03-01T12:00:00+05:00") == "2026-03-01T07:00:00+00:00"
    # Date-only (naive) is rejected — would silently mis-compare lexically.
    with pytest.raises(ValueError, match="no timezone"):
        _normalize_instant("2026-03-01")
    # Garbage is rejected, not lexically mis-filtered.
    with pytest.raises(ValueError, match="invalid datetime"):
        _normalize_instant("not-a-date")


def test_render_flags_reconciliation_divergence() -> None:
    from dazzle.rbac.access_evidence import (
        AccessReview,
        ChainAttestation,
        OrgAccessSnapshot,
        RosterReconciliation,
    )
    from dazzle.rbac.report import render_access_review_markdown

    review = AccessReview(
        tenant_id="org-1",
        generated_at="2026-06-05T00:00:00+00:00",
        snapshot=OrgAccessSnapshot("org-1", None, "current", []),
        jml=[],
        period_since=None,
        period_until=None,
        chain=ChainAttestation(ok=True, total_rows=0, mismatched_count=0, first_mismatch_id=None),
        reconciliation=RosterReconciliation(
            consistent=False, only_in_table=["m9"], only_in_replay=[], role_mismatches=[]
        ),
    )
    md = render_access_review_markdown(review)
    assert "Roster Reconciliation" in md
    assert "INCONSISTENT" in md and "m9" in md


def test_md_cell_escapes_pipe_and_newline() -> None:
    from dazzle.rbac.report import _md_cell

    assert _md_cell("a|b") == "a\\|b"
    assert _md_cell("line1\nline2") == "line1 line2"
