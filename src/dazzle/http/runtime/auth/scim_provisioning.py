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

from dazzle.http.runtime.auth.enterprise_login import map_groups_to_roles

_logger = logging.getLogger(__name__)

_MEMBER_VALUE_FILTER = _re.compile(r'members\[\s*value\s+eq\s+"([^"]+)"\s*\]', _re.IGNORECASE)


def _member_ids(value: Any) -> list[Any]:
    """Member ids from a SCIM ``members`` value — lenient: a non-list, or non-dict /
    value-less members, are skipped rather than crashing (hostile/malformed PATCH)."""
    if not isinstance(value, list):
        return []
    return [m["value"] for m in value if isinstance(m, dict) and "value" in m]


def parse_group_patch(body: dict[str, Any]) -> list[tuple[str, Any]]:
    """Parse a SCIM PATCH body into concrete ``(op, arg)`` tuples (#1342).

    Supports the forms Okta/Entra send (not a general SCIM path-filter engine):
    ``add_members`` (list), ``remove_member`` (one id via ``members[value eq "id"]``),
    ``replace_members`` (list; ``path:members`` remove-all → empty list), ``rename``
    (str; ``displayName`` path or the no-path ``value`` dict form). Unknown ops are
    skipped — the route returns the resource unchanged (SCIM-lenient).
    """
    ops: list[tuple[str, Any]] = []
    operations = body.get("Operations")
    if not isinstance(operations, list):
        return ops  # SCIM-lenient: a malformed/absent Operations is a no-op, not a crash
    for op in operations:
        if not isinstance(op, dict):
            continue  # skip a non-object operation rather than crashing on op.get(...)
        kind = str(op.get("op", "")).lower()
        path = op.get("path")
        value = op.get("value")
        if kind == "add" and path == "members":
            ops.append(("add_members", _member_ids(value)))
        elif kind == "remove" and isinstance(path, str):
            m = _MEMBER_VALUE_FILTER.fullmatch(path.strip())
            if m:
                ops.append(("remove_member", m.group(1)))
            elif path == "members":
                ops.append(("replace_members", []))  # remove all
        elif kind == "replace" and path == "members":
            ops.append(("replace_members", _member_ids(value)))
        elif kind in ("add", "replace") and path == "displayName":
            ops.append(("rename", str(value)))
        elif kind in ("add", "replace") and path is None and isinstance(value, dict):
            if "displayName" in value:
                ops.append(("rename", str(value["displayName"])))
            if "members" in value:
                ops.append(("replace_members", _member_ids(value["members"])))
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
    membership = store.get_membership(membership_id)
    # Org-containment chokepoint: NEVER touch a membership outside this
    # connection's org. This is the single defense for every caller — a PATCH
    # `remove`/`replace` op can carry an attacker-chosen membership id, and
    # without this guard recompute would zero a cross-org member's roles
    # (get_member_group_names returns [] for a foreign membership → roles []).
    if membership is None or membership.tenant_id != connection.tenant_id:
        return
    # #1342 schools-gap 2: match group_mapping on EITHER the group's display_name OR its
    # external_id (Entra group GUID) — so one GUID-keyed mapping works for SAML (claim=GUIDs)
    # and SCIM alike; name-keyed configs keep matching (display_name is always a key).
    keys = store.get_member_group_keys(membership_id, connection.id)
    roles = map_groups_to_roles(keys, connection.group_mapping or {})
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


def _raise_if_duplicate(exc: Exception, display_name: str) -> None:
    """Translate a DB unique-constraint hit into a 409 SCIMGroupError.

    The list_scim_groups pre-check is not atomic with the INSERT/UPDATE, so two
    concurrent IdP pushes (Okta/Entra parallelise group sync) can both pass the
    check and the loser then trips the ``UNIQUE (connection_id, display_name)``
    constraint. Map that to a SCIM 409 instead of letting psycopg's
    UniqueViolation propagate as an unhandled 500.
    """
    import psycopg

    if isinstance(exc, psycopg.errors.UniqueViolation):
        raise SCIMGroupError("uniqueness", f"group {display_name!r} already exists", 409) from exc


def _converge_on_external_id(
    store: Any, connection: Any, external_id: str | None, exc: Exception
) -> Any:
    """Recover from a ``(tenant_id, external_id)`` unique-index collision by re-resolving the
    membership the externalId now names (the concurrent winner / existing holder).

    The lookup→write in ``provision_scim_user`` is not atomic, so two parallel IdP pushes for
    the same externalId can both miss the lookup and the loser trips ``uq_memberships_tenant_external``.
    Re-reads converge on the winning row so SCIM stays idempotent instead of 500-ing. Re-raises
    the original error if it wasn't a uniqueness hit, or if the row genuinely can't be found
    (so a real failure isn't swallowed)."""
    import psycopg

    if external_id is not None and isinstance(exc, psycopg.errors.UniqueViolation):
        winner = store.get_membership_by_external_id(connection.tenant_id, external_id)
        if winner is not None:
            return winner
    raise exc


def _require_member_in_org(store: Any, connection: Any, membership_id: str) -> Any:
    """A membership by id, but only if it's in this connection's org (else raise)."""
    m = store.get_membership(membership_id)
    if m is None or m.tenant_id != connection.tenant_id:
        raise SCIMGroupError("invalid_member", f"member {membership_id!r} not in this org", 400)
    return m


def create_group(
    store: Any,
    connection: Any,
    display_name: str,
    member_ids: list[str],
    *,
    external_id: str | None = None,
) -> Any:
    if not display_name:
        raise SCIMGroupError("invalid_value", "displayName is required", 400)
    for mid in member_ids:
        _require_member_in_org(store, connection, mid)
    if store.list_scim_groups(connection.id, display_name=display_name):
        raise SCIMGroupError("uniqueness", f"group {display_name!r} already exists", 409)
    try:
        group = store.create_scim_group(connection.id, display_name, external_id)
    except Exception as exc:
        _raise_if_duplicate(exc, display_name)
        raise
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
        mapping = connection.group_mapping or {}
        # A rename re-derives every member's roles from the NEW name. If the new name isn't in
        # the mapping but the old one was, the rename strips the mapped role — correct (stale
        # mapping) but worth a loud warning. EXCEPT when the mapping is keyed by this group's
        # external_id (Entra GUID, #1342 gap 2): the GUID is unchanged by a rename, so the role
        # survives — don't warn (the display_name key was never load-bearing).
        guid_mapped = bool(getattr(group, "external_id", None) and group.external_id in mapping)
        if group.display_name in mapping and display_name not in mapping and not guid_mapped:
            _logger.warning(
                "SCIM group rename %r -> %r drops mapped role %r for all members "
                "(update connection.group_mapping to the new name to retain it)",
                group.display_name,
                display_name,
                mapping[group.display_name],
            )
        try:
            store.rename_scim_group(group_id, connection.id, display_name)
        except Exception as exc:
            _raise_if_duplicate(exc, display_name)
            raise
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


def _identity_email(store: Any, identity_id: str) -> str:
    """The global identity's current email, or ``""`` if it can't be resolved. Used only
    to detect (and loud-log) an externalId-matched re-push under a changed email."""
    from uuid import UUID

    try:
        user = store.get_user_by_id(UUID(str(identity_id)))
    except (ValueError, TypeError):
        return ""
    return getattr(user, "email", "") if user is not None else ""


def _sync_membership_active(store: Any, membership: Any, active: bool) -> None:
    """Apply the SCIM ``active`` flag to an existing membership. Roles are owned by the
    /Groups endpoint, so this touches status only. Deactivation revokes live sessions."""
    if active and membership.status == "suspended":
        store.reactivate_membership(membership.id, reason="SCIM reactivate")
    elif not active and membership.status == "active":
        store.suspend_membership(membership.id, reason="SCIM deactivate")
        store.delete_sessions_for_membership(membership.id)


def provision_scim_user(
    store: Any,
    connection: Any,
    *,
    email: str,
    active: bool = True,
    groups: list[str] | None = None,
    external_id: str | None = None,
) -> ScimResult:
    """Create-or-update a user pushed by the IdP (SCIM POST/PUT/PATCH).

    Resolution order (#1342 gap 1): if the IdP supplied a stable ``external_id`` (Entra
    user objectId GUID) and this org already has a membership for it, that membership IS
    this user — even if the pushed email differs (the IdP renamed the mailbox); we keep it
    and loud-log the mismatch rather than forking a duplicate identity. Otherwise resolve
    (or create) the global identity by verified email. Idempotent: a re-push syncs the
    active flag, backfills a newly-seen externalId, and never duplicates.
    """
    email = (email or "").strip().lower()
    external_id = (external_id or "").strip() or None
    if not email:
        raise ScimError("no_email", "the SCIM payload carried no email/userName")
    _require_verified_domain(connection, email)

    # Dedup-first: a stable externalId match wins over email. A re-push under a changed
    # email updates the existing membership instead of forking. On an email mismatch we
    # do NOT rewrite the global identity's email — it may be shared across orgs, and one
    # org's IdP push is not authoritative over the global mailbox (loud-log for operator).
    if external_id is not None:
        existing = store.get_membership_by_external_id(connection.tenant_id, external_id)
        if existing is not None:
            current_email = (_identity_email(store, existing.identity_id) or "").lower()
            if current_email and current_email != email:
                _logger.warning(  # nosemgrep
                    "SCIM connection %s: externalId %s pushed with email %r but the linked "
                    "identity's email is %r — keeping the existing membership; NOT rewriting "
                    "the global identity email (it may be shared across orgs). Operator "
                    "reconciliation may be needed.",
                    connection.id,
                    external_id,
                    email,
                    current_email,
                )
            _sync_membership_active(store, existing, active)
            return ScimResult(existing.identity_id, existing.id, active)

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
        # Uniform tenant admission gate (#1424): refuse provisioning if the org
        # restricts membership to its verified domains and this email is off-domain.
        from dazzle.http.runtime.auth.domain_join import assert_domain_admissible

        assert_domain_admissible(store, connection.tenant_id, email)

        try:
            membership = store.create_membership(
                tenant_id=connection.tenant_id,
                identity_id=identity_id,
                roles=[],  # /Groups assigns group-derived roles
                external_id=external_id,
                reason="SCIM provision",
            )
        except Exception as exc:
            # A concurrent provision won the (tenant_id, external_id) race (IdPs parallelise
            # user sync). The unique index blocked the duplicate row; converge on the winner
            # idempotently rather than surfacing a 500 (SCIM POST is idempotent on externalId).
            converged = _converge_on_external_id(store, connection, external_id, exc)
            _sync_membership_active(store, converged, active)
            return ScimResult(converged.identity_id, converged.id, active)
        if not active:
            store.suspend_membership(membership.id, reason="SCIM provisioned inactive")
        return ScimResult(identity_id, membership.id, active)

    # Existing membership found by email. Backfill the externalId on first sight so future
    # re-pushes (under a possibly-changed email) resolve via the stable id above.
    if external_id is not None and getattr(membership, "external_id", None) != external_id:
        try:
            store.update_membership_external_id(membership.id, external_id)
        except Exception as exc:
            # Another membership in this org already holds this externalId (concurrent race
            # or a pre-existing split identity). The stable id wins — converge on it, loud-log.
            winner = _converge_on_external_id(store, connection, external_id, exc)
            if winner.id != membership.id:
                _logger.warning(  # nosemgrep
                    "SCIM connection %s: externalId %s collided on backfill — email %r "
                    "resolved to membership %s but the externalId already names membership "
                    "%s; converging on the externalId's membership. Operator reconciliation "
                    "may be needed.",
                    connection.id,
                    external_id,
                    email,
                    membership.id,
                    winner.id,
                )
            _sync_membership_active(store, winner, active)
            return ScimResult(winner.identity_id, winner.id, active)
    _sync_membership_active(store, membership, active)
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
