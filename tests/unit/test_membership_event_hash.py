"""Pure-Python hash-chain helpers for membership_events (auth Plan 2a)."""

from dazzle.http.runtime.auth.membership_events import (
    MembershipEventType,
    _canonical_event_payload,
    compute_event_hash,
)


def _row(**over):
    base = {
        "id": "evt-1",
        "event_type": MembershipEventType.PROVISIONED,
        "membership_id": "m-1",
        "tenant_id": "org-1",
        "identity_id": "u-1",
        "actor_id": None,
        "roles_before": None,
        "roles_after": '["admin"]',
        "status_before": None,
        "status_after": "active",
        "reason": None,
        "created_at": "2026-06-05T00:00:00+00:00",
    }
    base.update(over)
    return base


def test_canonical_payload_is_deterministic_and_excludes_hash_and_seq() -> None:
    row = _row()
    row_with_noise = {**row, "row_hash": "deadbeef", "seq": 42}
    # row_hash and seq must NOT affect the canonical payload.
    assert _canonical_event_payload(row) == _canonical_event_payload(row_with_noise)
    # Deterministic: sorted keys, compact separators.
    assert _canonical_event_payload(row).startswith("{")
    assert '"id":"evt-1"' in _canonical_event_payload(row)


def test_compute_event_hash_chains_on_prev() -> None:
    row = _row()
    h1 = compute_event_hash("", row)
    h2 = compute_event_hash(h1, row)
    assert h1 != h2  # same content, different prev → different hash
    assert len(h1) == 64  # sha256 hexdigest
    # Recomputation is stable.
    assert compute_event_hash("", row) == h1


def test_event_types_are_the_five_jml_kinds() -> None:
    assert MembershipEventType.PROVISIONED == "provisioned"
    assert MembershipEventType.ROLE_CHANGED == "role_changed"
    assert MembershipEventType.SUSPENDED == "suspended"
    assert MembershipEventType.REACTIVATED == "reactivated"
    assert MembershipEventType.REMOVED == "removed"
