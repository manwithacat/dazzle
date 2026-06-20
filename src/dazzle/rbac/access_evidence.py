"""Access-evidence / access-review export (auth Plan 2b).

Turns the Plan 2a membership lifecycle substrate into auditor-ready evidence:
a per-org membership snapshot (current or point-in-time "as of date D",
reconstructed by replaying ``membership_events``), the Joiner/Mover/Leaver event
stream over a period, both mapped to SOC 2 / ISO 27001 controls (spec §6), and a
tamper-evidence attestation (the 2a hash-chain verification).

The membership table IS the per-org access matrix; the event stream IS every
access change. "Everyone with access to org X as of date D" and "every access
change in period P" are answered completely **when every mutation goes through the
AuthStore membership methods** (which emit the lifecycle event atomically). A
raw-SQL bypass would not emit an event; the current-state snapshot therefore
ships a `reconciliation` cross-check (current table vs replay-to-now) so such a
divergence is surfaced, not silently trusted.

Integrity caveat: the 2a hash-chain detects *edited* and *removed interior*
events, but a self-contained chain cannot detect truncation of the most recent
*trailing* events (no successor hash to break). The attestation wording is scoped
accordingly; a tamper-proof guarantee against tail truncation needs an external
signed head anchor (a future substrate slice).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from dazzle.http.runtime.auth.membership_events import MembershipEvent, MembershipEventType


def _normalize_instant(value: str | None) -> str | None:
    """Normalize an ISO-8601 string to a UTC instant for the lexical TEXT filter.

    ``membership_events.created_at`` is always written as a UTC ``isoformat()``
    (``+00:00``), and the point-in-time / period filters are lexical TEXT
    comparisons — so a caller-supplied cutoff MUST be a full UTC ISO-8601 instant
    or the comparison is silently wrong (H2/H3). Parse, require a timezone (reject
    date-only / naive), convert to UTC, re-emit. Raises ``ValueError`` otherwise.
    """
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"invalid datetime {value!r}: expected a full ISO-8601 instant, "
            "e.g. 2026-03-01T00:00:00+00:00"
        ) from exc
    if dt.tzinfo is None:
        raise ValueError(
            f"datetime {value!r} has no timezone offset — pass an explicit offset "
            "(e.g. ...+00:00) so the point-in-time filter is unambiguous"
        )
    return dt.astimezone(UTC).isoformat()


# spec §6 — membership lifecycle event (and the roster itself) → control ids.
# SOC 2 CC6.x (logical access) + ISO 27001 A.5.15–18 (access control / identity /
# auth / access rights). The "roster" key maps the point-in-time access matrix.
ACCESS_EVIDENCE_CONTROLS: dict[str, list[str]] = {
    MembershipEventType.PROVISIONED: ["CC6.2", "A.5.16", "A.5.18"],  # joiner / grant
    MembershipEventType.ROLE_CHANGED: ["CC6.3", "A.5.18"],  # mover / access rights
    MembershipEventType.SUSPENDED: ["CC6.2", "CC6.3", "A.5.18"],  # leaver-ish
    MembershipEventType.REACTIVATED: ["CC6.3", "A.5.18"],  # mover
    MembershipEventType.REMOVED: ["CC6.2", "CC6.3", "A.5.18"],  # leaver / revoke
    "roster": ["CC6.1", "CC6.3", "A.5.15"],  # the as-of access matrix + review
}

_JML: dict[str, str] = {
    MembershipEventType.PROVISIONED: "joiner",
    MembershipEventType.ROLE_CHANGED: "mover",
    MembershipEventType.REACTIVATED: "mover",
    MembershipEventType.SUSPENDED: "leaver",
    MembershipEventType.REMOVED: "leaver",
}


def classify_jml(event_type: str) -> str:
    """Bucket a membership event kind into joiner / mover / leaver (or 'other')."""
    return _JML.get(event_type, "other")


@dataclass(frozen=True)
class MemberSnapshot:
    """One membership in a roster, as of the snapshot moment."""

    membership_id: str
    identity_id: str
    roles: list[str]
    status: str
    joined_at: str | None  # ISO-8601 (the provisioned event time, when replayed)


def replay_roster(events: list[MembershipEvent]) -> dict[str, MemberSnapshot]:
    """Reconstruct the roster (membership_id → MemberSnapshot) by replaying events.

    Pure: takes an already-time-filtered, seq-ordered event list and folds it.
    provisioned→add, role_changed→update roles, suspended/reactivated→status,
    removed→drop. Keyed by membership_id so a removed-then-reprovisioned identity
    is correctly two distinct grants.
    """
    roster: dict[str, MemberSnapshot] = {}
    for e in sorted(events, key=lambda x: x.seq if x.seq is not None else 0):
        mid = e.membership_id
        if e.event_type == MembershipEventType.PROVISIONED:
            roster[mid] = MemberSnapshot(
                membership_id=mid,
                identity_id=e.identity_id,
                roles=list(e.roles_after or []),
                status=e.status_after or "active",
                joined_at=e.created_at.isoformat() if e.created_at else None,
            )
        elif e.event_type == MembershipEventType.REMOVED:
            roster.pop(mid, None)
        elif mid in roster:
            cur = roster[mid]
            if e.event_type == MembershipEventType.ROLE_CHANGED:
                roster[mid] = MemberSnapshot(
                    mid, cur.identity_id, list(e.roles_after or []), cur.status, cur.joined_at
                )
            elif e.event_type in (
                MembershipEventType.SUSPENDED,
                MembershipEventType.REACTIVATED,
            ):
                roster[mid] = MemberSnapshot(
                    mid, cur.identity_id, cur.roles, e.status_after or cur.status, cur.joined_at
                )
    return roster


@dataclass(frozen=True)
class OrgAccessSnapshot:
    """Per-org membership roster at a moment (current or as-of)."""

    tenant_id: str
    as_of: str | None  # ISO-8601 cut-off; None = current state
    source: str  # "current" (memberships table) | "replay" (event stream)
    members: list[MemberSnapshot]


@dataclass(frozen=True)
class JmlEntry:
    """One access-change event, JML-classified, with its control mappings."""

    jml: str  # joiner | mover | leaver | other
    event_type: str
    membership_id: str
    identity_id: str
    roles_before: list[str] | None
    roles_after: list[str] | None
    status_before: str | None
    status_after: str | None
    actor_id: str | None
    reason: str | None
    at: str  # ISO-8601
    controls: list[str]


@dataclass(frozen=True)
class ChainAttestation:
    """Tamper-evidence attestation for the evidence (Plan 2a chain verify).

    ``ok`` means: no edited or removed *interior* event was detected across the
    recomputed chain. It does NOT certify against *tail* truncation (deletion of
    the most recent trailing events) — a self-contained chain has no successor
    hash to break there. ``tail_truncation_detectable`` records that scope
    honestly so the renderer never over-claims "tamper-proof".
    """

    ok: bool
    total_rows: int
    mismatched_count: int
    first_mismatch_id: str | None
    tail_truncation_detectable: bool = False


@dataclass(frozen=True)
class RosterReconciliation:
    """Cross-check: the current memberships table vs replay-to-now of the event log.

    They agree when every mutation went through the AuthStore methods (which emit
    events atomically). A divergence means a row was changed without emitting an
    event (e.g. a raw-SQL bypass) — surfaced here rather than silently trusting
    the table as authoritative.
    """

    consistent: bool
    only_in_table: list[str]  # membership_ids in the table, absent from replay
    only_in_replay: list[str]  # active in replay, absent from the table
    role_mismatches: list[str]  # membership_ids whose table roles != replay roles


@dataclass(frozen=True)
class AccessReview:
    """The full access-review evidence pack for one org."""

    tenant_id: str
    generated_at: str
    snapshot: OrgAccessSnapshot
    jml: list[JmlEntry]
    period_since: str | None
    period_until: str | None
    chain: ChainAttestation
    control_index: dict[str, list[str]] = field(default_factory=dict)
    reconciliation: RosterReconciliation | None = None  # only for current-state snapshots

    def to_dict(self) -> dict[str, Any]:
        """JSON-able dict (owner-attestable evidence artifact)."""
        return asdict(self)


def reconcile_current_vs_replay(store: Any, tenant_id: str) -> RosterReconciliation:
    """Compare the current memberships table to a replay-to-now of the event log."""
    table = {m.id: list(m.roles) for m in store.get_memberships_for_tenant(tenant_id)}
    replay = {
        mid: snap.roles
        for mid, snap in replay_roster(store.get_membership_events(tenant_id=tenant_id)).items()
    }
    only_table = sorted(set(table) - set(replay))
    only_replay = sorted(set(replay) - set(table))
    role_mismatch = sorted(mid for mid in set(table) & set(replay) if table[mid] != replay[mid])
    return RosterReconciliation(
        consistent=not (only_table or only_replay or role_mismatch),
        only_in_table=only_table,
        only_in_replay=only_replay,
        role_mismatches=role_mismatch,
    )


def build_org_snapshot(
    store: Any, tenant_id: str, *, as_of: str | None = None
) -> OrgAccessSnapshot:
    """Build the roster: current memberships (as_of None) or a point-in-time replay.

    ``as_of`` is an ISO-8601 string; events with ``created_at <= as_of`` are
    replayed (the membership_events ``created_at`` is TEXT ISO-8601, lexically
    ordered). Current state reads the authoritative ``memberships`` table.
    """
    as_of = _normalize_instant(as_of)
    if as_of is None:
        members = [
            MemberSnapshot(
                membership_id=m.id,
                identity_id=m.identity_id,
                roles=list(m.roles),
                status=m.status,
                joined_at=m.joined_at.isoformat() if m.joined_at else None,
            )
            for m in store.get_memberships_for_tenant(tenant_id)
        ]
        return OrgAccessSnapshot(tenant_id, None, "current", members)

    events = store.get_membership_events(tenant_id=tenant_id, until=as_of)
    roster = replay_roster(events)
    return OrgAccessSnapshot(tenant_id, as_of, "replay", list(roster.values()))


def build_jml_stream(
    store: Any, tenant_id: str, *, since: str | None = None, until: str | None = None
) -> list[JmlEntry]:
    """The JML access-change stream for an org over a period (from 2a events)."""
    since = _normalize_instant(since)
    until = _normalize_instant(until)
    out: list[JmlEntry] = []
    for e in store.get_membership_events(tenant_id=tenant_id, since=since, until=until):
        out.append(
            JmlEntry(
                jml=classify_jml(e.event_type),
                event_type=e.event_type,
                membership_id=e.membership_id,
                identity_id=e.identity_id,
                roles_before=e.roles_before,
                roles_after=e.roles_after,
                status_before=e.status_before,
                status_after=e.status_after,
                actor_id=e.actor_id,
                reason=e.reason,
                at=e.created_at.isoformat() if e.created_at else "",
                controls=ACCESS_EVIDENCE_CONTROLS.get(e.event_type, []),
            )
        )
    return out


def build_access_review(
    store: Any,
    tenant_id: str,
    *,
    as_of: str | None = None,
    since: str | None = None,
    until: str | None = None,
    generated_at: str,
) -> AccessReview:
    """Assemble the full evidence pack: snapshot + JML stream + chain attestation.

    ``generated_at`` is passed in (callers stamp the wall-clock time) so this
    builder stays deterministic/testable.
    """
    snapshot = build_org_snapshot(store, tenant_id, as_of=as_of)
    jml = build_jml_stream(store, tenant_id, since=since, until=until)
    chain_result = store.verify_membership_event_chain()
    chain = ChainAttestation(
        ok=chain_result.ok,
        total_rows=chain_result.total_rows,
        mismatched_count=chain_result.mismatched_count,
        first_mismatch_id=chain_result.first_mismatch_id,
        tail_truncation_detectable=False,  # honest scope — see ChainAttestation docstring
    )
    # Cross-check the authoritative current table against the immutable log (only
    # meaningful for a current-state snapshot; an as-of replay IS the log).
    reconciliation = (
        reconcile_current_vs_replay(store, tenant_id) if snapshot.source == "current" else None
    )
    return AccessReview(
        tenant_id=tenant_id,
        generated_at=generated_at,
        snapshot=snapshot,
        jml=jml,
        period_since=since,
        period_until=until,
        chain=chain,
        control_index=dict(ACCESS_EVIDENCE_CONTROLS),
        reconciliation=reconciliation,
    )
