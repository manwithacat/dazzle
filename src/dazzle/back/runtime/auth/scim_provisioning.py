"""SCIM 2.0 provisioning kernel (auth Plan 4c.i).

Turns an IdP's SCIM provisioning intents — create/update a user, deactivate
(``active:false``), deprovision (DELETE) — into identity + membership state changes
against the existing membership lifecycle. The SCIM REST/JSON endpoints that parse
the wire format and call these live in 4c.ii; this module is the security substance.

The same **anti-hijack** invariant as enterprise OIDC (4b.ii) applies: a SCIM
connection may only provision emails within ITS OWN ``verified_domains`` — a SCIM
bearer can't be used to provision identities in a domain the connection doesn't
control. Every operation is scoped to ``connection.tenant_id``, so one org's SCIM
integration can never touch another org's memberships. Deactivation suspends the org
membership AND revokes its sessions, so access is lost immediately.
"""

from __future__ import annotations

import secrets as _secrets
from dataclasses import dataclass
from typing import Any

from dazzle.back.runtime.auth.enterprise_login import map_groups_to_roles


class ScimError(RuntimeError):
    """A SCIM provisioning intent can't be applied. ``reason`` is a stable code
    (``no_email`` / ``domain_not_verified`` / ``not_found``); the message is human
    detail. Never carries a secret (the bearer is authenticated upstream)."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def recompute_membership_roles(store: Any, connection: Any, membership_id: str) -> None:
    """Set a membership's roles to ``map_groups_to_roles`` over the union of ALL
    its (this-connection) SCIM groups — the single source of truth for
    group-derived roles (#1342). Idempotent; correct for multi-group de-escalation
    (a role granted by another group survives removal from one)."""
    names = store.get_member_group_names(membership_id, connection.id)
    roles = map_groups_to_roles(names, connection.group_mapping or {})
    membership = store.get_membership(membership_id)
    if membership is None:
        return
    if set(roles) != set(membership.roles or []):
        store.update_membership_roles(membership_id, roles, reason="SCIM group sync")


@dataclass(frozen=True)
class ScimResult:
    """Outcome of a provision/update — the resolved identity + membership + state."""

    identity_id: str
    membership_id: str
    active: bool


def _email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""


def _require_verified_domain(connection: Any, email: str) -> None:
    """Anti-hijack: the email's domain must be one the connection has verified."""
    domain = _email_domain(email)
    verified = {d.strip().lower() for d in (connection.verified_domains or [])}
    if not domain or domain not in verified:
        raise ScimError(
            "domain_not_verified",
            "the user's email is outside this connection's verified domains",
        )


def _membership_in_org(store: Any, identity_id: str, tenant_id: str) -> Any:
    """The identity's membership in ``tenant_id`` (any status), or ``None``."""
    for membership in store.get_memberships_for_identity(identity_id):
        if membership.tenant_id == tenant_id:
            return membership
    return None


def provision_scim_user(
    store: Any,
    connection: Any,
    *,
    email: str,
    active: bool = True,
    groups: list[str] | None = None,
) -> ScimResult:
    """Create-or-update a user pushed by the IdP (SCIM POST/PUT/PATCH).

    Resolves/creates the global identity by verified email, then ensures a membership
    in the connection's org reflecting ``active`` + the group→role mapping. Idempotent:
    a re-push syncs roles and the active flag without duplicating.
    """
    email = (email or "").strip().lower()
    if not email:
        raise ScimError("no_email", "the SCIM payload carried no email/userName")
    _require_verified_domain(connection, email)

    user = store.get_user_by_email(email)
    if user is None:
        user = store.create_user(email=email, password=_secrets.token_urlsafe(48), username=None)
    if not getattr(user, "email_verified", False):
        # The org's IdP vouched for this mailbox within a verified domain.
        store.mark_email_verified(str(user.id))

    identity_id = str(user.id)
    roles = map_groups_to_roles(groups or [], connection.group_mapping or {})
    membership = _membership_in_org(store, identity_id, connection.tenant_id)

    if membership is None:
        membership = store.create_membership(
            tenant_id=connection.tenant_id,
            identity_id=identity_id,
            roles=roles,
            reason="SCIM provision",
        )
        if not active:
            store.suspend_membership(membership.id, reason="SCIM provisioned inactive")
        return ScimResult(identity_id, membership.id, active)

    # Existing membership — sync roles + active state. The IdP is authoritative, so an
    # empty target set (the user was removed from all mapped groups) MUST revoke the
    # last roles — do NOT guard on `roles` being truthy, or de-escalation-to-zero would
    # silently leave the old (possibly admin) roles in place.
    if set(roles) != set(membership.roles or []):
        store.update_membership_roles(membership.id, roles, reason="SCIM role sync")
    if active and membership.status == "suspended":
        store.reactivate_membership(membership.id, reason="SCIM reactivate")
    elif not active and membership.status == "active":
        store.suspend_membership(membership.id, reason="SCIM deactivate")
        store.delete_sessions_for_membership(membership.id)
    return ScimResult(identity_id, membership.id, active)


def set_scim_user_active(store: Any, connection: Any, *, identity_id: str, active: bool) -> str:
    """Apply a SCIM ``active`` toggle (the common PATCH). Returns the membership id.

    ``active=False`` suspends the org membership and revokes its sessions (access lost
    now); ``active=True`` reactivates a suspended membership. Idempotent — a no-op when
    the membership is already in the target state. Raises ``ScimError('not_found')`` if
    the identity has no membership in this org.
    """
    membership = _membership_in_org(store, identity_id, connection.tenant_id)
    if membership is None:
        raise ScimError("not_found", "no membership for this identity in this organization")
    if active:
        if membership.status == "suspended":
            store.reactivate_membership(membership.id, reason="SCIM activate")
    elif membership.status == "active":
        store.suspend_membership(membership.id, reason="SCIM deactivate")
        store.delete_sessions_for_membership(membership.id)
    return str(membership.id)


def deprovision_scim_user(store: Any, connection: Any, *, identity_id: str) -> bool:
    """Apply a SCIM DELETE — remove the org membership and revoke its sessions.

    Returns ``True`` if a membership was removed, ``False`` if there was none (idempotent
    DELETE). The global identity is left intact (it may belong to other orgs); only this
    org's membership + its sessions are torn down. The REMOVED lifecycle event persists.
    """
    membership = _membership_in_org(store, identity_id, connection.tenant_id)
    if membership is None:
        return False
    # Revoke sessions first so access is cut even if the membership delete is retried.
    store.delete_sessions_for_membership(membership.id)
    return bool(store.remove_membership(membership.id, reason="SCIM deprovision"))
