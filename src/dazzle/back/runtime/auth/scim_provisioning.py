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

import logging
import re as _re
import secrets as _secrets
from dataclasses import dataclass
from typing import Any

from dazzle.back.runtime.auth.enterprise_login import map_groups_to_roles

_logger = logging.getLogger(__name__)

_MEMBER_VALUE_FILTER = _re.compile(r'members\[\s*value\s+eq\s+"([^"]+)"\s*\]', _re.IGNORECASE)


def parse_group_patch(body: dict[str, Any]) -> list[tuple[str, Any]]:
    """Parse a SCIM PATCH body into concrete ``(op, arg)`` tuples (#1342).

    Supports the forms Okta/Entra send (not a general SCIM path-filter engine):
    ``add_members`` (list), ``remove_member`` (one id via ``members[value eq "id"]``),
    ``replace_members`` (list; ``path:members`` remove-all → empty list), ``rename``
    (str; ``displayName`` path or the no-path ``value`` dict form). Unknown ops are
    skipped — the route returns the resource unchanged (SCIM-lenient).
    """
    ops: list[tuple[str, Any]] = []
    for op in body.get("Operations", []) or []:
        kind = str(op.get("op", "")).lower()
        path = op.get("path")
        value = op.get("value")
        if kind == "add" and path == "members":
            ops.append(("add_members", [m["value"] for m in (value or []) if "value" in m]))
        elif kind == "remove" and isinstance(path, str):
            m = _MEMBER_VALUE_FILTER.fullmatch(path.strip())
            if m:
                ops.append(("remove_member", m.group(1)))
            elif path == "members":
                ops.append(("replace_members", []))  # remove all
        elif kind == "replace" and path == "members":
            ops.append(("replace_members", [m["value"] for m in (value or []) if "value" in m]))
        elif kind in ("add", "replace") and path == "displayName":
            ops.append(("rename", str(value)))
        elif kind in ("add", "replace") and path is None and isinstance(value, dict):
            if "displayName" in value:
                ops.append(("rename", str(value["displayName"])))
            if "members" in value:
                ops.append(
                    (
                        "replace_members",
                        [m["value"] for m in (value["members"] or []) if "value" in m],
                    )
                )
        # else: unknown op — skip
    return ops


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


class SCIMGroupError(Exception):
    """A SCIM Group op error → mapped to a SCIM HTTP status by the route.

    ``status`` is the HTTP code (400 invalid, 404 not-found, 409 uniqueness).
    """

    def __init__(self, reason: str, message: str = "", status: int = 400) -> None:
        self.reason = reason
        self.status = status
        super().__init__(message or reason)


def _require_member_in_org(store: Any, connection: Any, membership_id: str) -> Any:
    """A membership by id, but only if it's in this connection's org (else raise)."""
    m = store.get_membership(membership_id)
    if m is None or m.tenant_id != connection.tenant_id:
        raise SCIMGroupError("invalid_member", f"member {membership_id!r} not in this org", 400)
    return m


def create_group(store: Any, connection: Any, display_name: str, member_ids: list[str]) -> Any:
    if not display_name:
        raise SCIMGroupError("invalid_value", "displayName is required", 400)
    for mid in member_ids:
        _require_member_in_org(store, connection, mid)
    if store.list_scim_groups(connection.id, display_name=display_name):
        raise SCIMGroupError("uniqueness", f"group {display_name!r} already exists", 409)
    group = store.create_scim_group(connection.id, display_name)
    for mid in member_ids:
        store.add_group_member(group.id, mid)
        recompute_membership_roles(store, connection, mid)
    return group


def get_group(store: Any, connection: Any, group_id: str) -> Any:
    group = store.get_scim_group(group_id, connection.id)
    if group is None:
        raise SCIMGroupError("not_found", f"no group {group_id!r}", 404)
    return group


def list_groups(store: Any, connection: Any, display_name: str | None = None) -> Any:
    return store.list_scim_groups(connection.id, display_name=display_name)


def rename_group(store: Any, connection: Any, group_id: str, display_name: str) -> Any:
    group = get_group(store, connection, group_id)
    if display_name and display_name != group.display_name:
        if store.list_scim_groups(connection.id, display_name=display_name):
            raise SCIMGroupError("uniqueness", f"group {display_name!r} already exists", 409)
        store.rename_scim_group(group_id, connection.id, display_name)
        for mid in store.get_group_member_ids(group_id):
            recompute_membership_roles(store, connection, mid)
    return store.get_scim_group(group_id, connection.id)


def delete_group(store: Any, connection: Any, group_id: str) -> None:
    get_group(store, connection, group_id)  # 404 if absent / wrong org
    member_ids = store.get_group_member_ids(group_id)
    store.delete_scim_group(group_id, connection.id)  # cascades scim_group_members
    for mid in member_ids:
        recompute_membership_roles(store, connection, mid)


def set_group_members(store: Any, connection: Any, group_id: str, member_ids: list[str]) -> None:
    get_group(store, connection, group_id)
    for mid in member_ids:
        _require_member_in_org(store, connection, mid)
    affected = set(store.get_group_member_ids(group_id)) | set(member_ids)
    store.replace_group_members(group_id, member_ids)
    for mid in affected:
        recompute_membership_roles(store, connection, mid)


def add_group_members(store: Any, connection: Any, group_id: str, member_ids: list[str]) -> None:
    get_group(store, connection, group_id)
    for mid in member_ids:
        _require_member_in_org(store, connection, mid)
        store.add_group_member(group_id, mid)
        recompute_membership_roles(store, connection, mid)


def remove_group_member(store: Any, connection: Any, group_id: str, member_id: str) -> None:
    get_group(store, connection, group_id)
    store.remove_group_member(group_id, member_id)
    recompute_membership_roles(store, connection, member_id)


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
    # #1342: group→role is owned by the /Groups endpoint (RFC 7643 treats
    # User.groups as server-managed/read-only). The `groups` arg is accepted for
    # compatibility but no longer drives roles — group-derived roles come solely
    # from persisted SCIM group memberships (recompute_membership_roles).
    if groups:
        _logger.debug(
            "SCIM User `groups` attribute is informational (use /Groups for roles): %s",
            groups,
        )
    membership = _membership_in_org(store, identity_id, connection.tenant_id)

    if membership is None:
        membership = store.create_membership(
            tenant_id=connection.tenant_id,
            identity_id=identity_id,
            roles=[],  # /Groups assigns group-derived roles
            reason="SCIM provision",
        )
        if not active:
            store.suspend_membership(membership.id, reason="SCIM provisioned inactive")
        return ScimResult(identity_id, membership.id, active)

    # Existing membership — sync only active state. Roles are owned by the /Groups
    # endpoint; do NOT overwrite them from the (informational) `groups` attribute.
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
