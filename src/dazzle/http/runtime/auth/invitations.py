"""Organization invitations (auth Plan 3a).

An org admin invites a person by *email* + roles; the membership is created when
the invitee *accepts* — never at invite time — so an unregistered or unverified
invitee never holds a dangling grant. The accept binds the grant to a logged-in
identity whose **verified** email matches the invitation (the verified-email
identity-join key, spec §8): a stolen link cannot grant access to a different
account, and JIT provisioning stays safe (no confused-deputy).

Token table mirrors ``magic_link`` (opaque token, TTL, single-use via
``accepted_at``). Accept reuses Plan 2a ``create_membership`` (→ ``provisioned``
event, ``invited_by`` attributed).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.errors import UniqueViolation as _UniqueViolation

INVITATIONS_DDL = """
CREATE TABLE IF NOT EXISTS invitations (
    token TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    email TEXT NOT NULL,
    roles TEXT NOT NULL DEFAULT '[]',
    invited_by TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    created_at TEXT NOT NULL
)
"""

INVITATIONS_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_invitations_org ON invitations(org_id)",
    "CREATE INDEX IF NOT EXISTS ix_invitations_email ON invitations(email)",
)


class InvitationError(RuntimeError):
    """An invitation could not be created or accepted.

    ``reason`` is a stable code (``not_found`` / ``used`` / ``expired`` /
    ``email_mismatch`` / ``unverified`` / ``already_member``) the routes map to a
    status + message.
    """

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


@dataclass(frozen=True)
class InvitationRecord:
    token: str
    org_id: str
    email: str
    roles: list[str]
    invited_by: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


def _row_to_invitation(row: dict[str, Any]) -> InvitationRecord:
    return InvitationRecord(
        token=row["token"],
        org_id=row["org_id"],
        email=row["email"],
        roles=json.loads(row["roles"]) if row.get("roles") else [],
        invited_by=row["invited_by"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
        accepted_at=datetime.fromisoformat(row["accepted_at"]) if row.get("accepted_at") else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def create_invitation(
    store: Any,
    *,
    org_id: str,
    email: str,
    roles: list[str],
    invited_by: str,
    ttl_hours: int = 72,
) -> str:
    """Create a pending invitation; returns the opaque token (for the accept URL).

    Authorization (who may invite) is enforced at the route layer, not here.
    Email is normalised to lowercase so the accept-time match is case-insensitive.
    """
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
    store._execute_modify(
        """
        INSERT INTO invitations (token, org_id, email, roles, invited_by, expires_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            token,
            org_id,
            email.strip().lower(),
            json.dumps(roles),
            invited_by,
            expires_at,
            now.isoformat(),
        ),
    )
    return token


def get_invitation(store: Any, token: str) -> InvitationRecord | None:
    rows = store._execute("SELECT * FROM invitations WHERE token = %s", (token,))
    return _row_to_invitation(rows[0]) if rows else None


def list_pending_invitations(store: Any, org_id: str) -> list[InvitationRecord]:
    """Open (not-yet-accepted, not-expired) invitations for an org (for 3b admin UI)."""
    now = datetime.now(UTC).isoformat()
    rows = store._execute(
        "SELECT * FROM invitations WHERE org_id = %s AND accepted_at IS NULL "
        "AND expires_at > %s ORDER BY created_at",
        (org_id, now),
    )
    return [_row_to_invitation(r) for r in rows]


def accept_invitation(
    store: Any,
    token: str,
    *,
    identity_id: str,
    accepting_email: str,
    email_verified: bool,
) -> Any:  # -> MembershipRecord
    """Redeem an invitation → create an active membership for the accepting identity.

    Enforces (in order): token exists, not already accepted, not expired, and the
    **verified-email join** — the accepting identity's email MUST equal the
    invitation email AND be verified (spec §8; prevents a stolen link granting a
    different account). Idempotency: a pre-existing membership for (org, identity)
    raises ``already_member`` rather than duplicating.

    Atomicity note: the membership is created first (the durable grant), then the
    token is marked accepted. If the process dies between, a re-accept hits the
    ``already_member`` guard — so a partial state never yields a *duplicate*
    membership; the worst case is an un-marked token that self-heals on re-accept.
    """
    inv = get_invitation(store, token)
    if inv is None:
        raise InvitationError("not_found", "invitation not found")
    if inv.accepted_at is not None:
        raise InvitationError("used", "invitation already accepted")
    if datetime.now(UTC) > inv.expires_at:
        raise InvitationError("expired", "invitation expired")
    if accepting_email.strip().lower() != inv.email:
        # The grant binds only to the verified identity for the invited email.
        raise InvitationError("email_mismatch", "this invitation is for a different email address")
    if not email_verified:
        raise InvitationError("unverified", "verify your email address before accepting")
    # Already a member of this org? Don't duplicate (uq_memberships_tenant_identity).
    # NOTE: this matches a membership of ANY status — a *suspended* prior member is
    # told ``already_member`` (reactivate them rather than re-invite). A *removed*
    # member has no row, so re-invite works.
    for m in store.get_memberships_for_identity(identity_id):
        if m.tenant_id == inv.org_id:
            raise InvitationError("already_member", "already a member of this organization")

    # Uniform tenant admission gate (#1424): if the org restricts membership to its
    # verified domains, the accepting email's domain must be among them. No-op otherwise.
    from dazzle.http.runtime.auth.domain_join import assert_domain_admissible

    assert_domain_admissible(store, inv.org_id, accepting_email)

    try:
        membership = store.create_membership(
            tenant_id=inv.org_id,
            identity_id=identity_id,
            roles=inv.roles,
            invited_by=inv.invited_by,
            actor_id=inv.invited_by,
            reason="invitation accepted",
        )
    except _UniqueViolation as exc:
        # A concurrent accept won the (org, identity) unique constraint between our
        # guard read and this insert — surface a clean already_member, not a 500.
        raise InvitationError("already_member", "already a member of this organization") from exc
    store._execute_modify(
        "UPDATE invitations SET accepted_at = %s WHERE token = %s",
        (datetime.now(UTC).isoformat(), token),
    )
    return membership
