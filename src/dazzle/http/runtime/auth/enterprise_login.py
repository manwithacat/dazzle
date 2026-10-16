"""JIT identity-join for enterprise SSO logins (auth Plan 4b.ii).

After a ``ConnectionProvider`` callback asserts an identity (4b.i), this turns that
assertion into a usable ``(global Identity, org Membership)`` pair — the security-
critical step where an org's IdP assertion becomes platform access. It mirrors the
proven ``invitations.accept_invitation`` verified-email→membership path.

**Anti-hijack invariant (load-bearing):** an org's connection may only assert an
email within ITS OWN ``verified_domains``. This is what stops a malicious or
compromised org IdP from asserting ``victim@othercompany.com`` and seizing that
global identity. It complements the discovery-layer anti-hijack (verified-domain
*routing*, 4a) with an identity-layer check on the *asserted* email — a connection
with no verified domains can assert nobody.

**``require_sso`` (DD-013 decision 4).** A verified OIDC connection whose
``config["require_sso"]`` is ``True`` takes its domains off local sign-in: password
login, magic-link and password-reset requests for those addresses are refused and
sent to the IdP. :func:`sso_required_for` is the one domain lookup every refused path
calls (through :func:`sso_redirect_for`).
"""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation as _UniqueViolation

from dazzle.http.runtime.auth.connections import AssertedIdentity, ConnectionRecord
from dazzle.http.runtime.auth.invitations import InvitationError

# Claims sources whose email is cryptographically validated by the provider and may be
# trusted directly: an OIDC ``id_token`` (authlib-verified signature/iss/aud/exp/nonce). The
# OIDC UserInfo-endpoint fallback (``userinfo_endpoint``) is NOT here — its claims aren't
# signed, so they additionally require an explicit ``email_verified=true``.
_VALIDATED_CLAIMS_SOURCES = frozenset({"id_token"})

# ``app.state`` attribute ``AuthSubsystem._mount_oidc`` sets once the enterprise OIDC routes
# are mounted. ``require_sso`` refusals fire only when it is set: without those routes there
# is no IdP to send the user to, so local sign-in behaves exactly as before.
ENTERPRISE_OIDC_STATE_ATTR = "enterprise_oidc_enabled"

# The route a refused local sign-in is sent to (``enterprise_routes``).
ENTERPRISE_LOGIN_PATH = "/auth/enterprise/login"

# JSON refusal status: 403, not the 401 a bad password gets — the credentials were never
# evaluated; the org's policy forbids this sign-in method for the address.
SSO_REQUIRED_STATUS = 403


class EnterpriseLoginError(InvitationError):
    """An enterprise SSO assertion cannot be turned into a membership.

    ``reason`` is a stable machine code (``domain_not_verified`` / ``no_email`` /
    ``unverified_fallback`` / ``no_membership``) the route maps to a user-facing
    error; the message is human detail. Never carries the asserted email or any
    secret (kept out of logs / redirect query strings). Shares ``InvitationError``'s
    ``(reason, message)`` shape: both are a refused verified-email → membership join.
    """


def _email_domain(email: str) -> str:
    """Return the lowercased domain part of ``email``, or ``""`` if malformed."""
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].strip().lower()


def map_groups_to_roles(groups: list[str], group_mapping: dict[str, str]) -> list[str]:
    """Map IdP groups → app roles via the connection's ``group_mapping`` (default-deny).

    Unmapped groups contribute nothing. Returns a de-duplicated, order-preserving role
    list. An empty result means the member gets in with no app roles — the
    ``permit:``/``scope:`` layer then default-denies their actions.
    """
    roles: list[str] = []
    for group in groups:
        role = group_mapping.get(group)
        if role and role not in roles:
            roles.append(role)
    return roles


def _trusted_email(connection: ConnectionRecord, asserted: AssertedIdentity) -> str:
    """The asserted email, normalised, once steps 1–2 of the join accept it."""
    email = (asserted.email or "").strip().lower()
    if not email:
        raise EnterpriseLoginError("no_email", "the IdP asserted no email")

    # (1) Anti-hijack: the org's IdP may only assert identities in its verified domains.
    domain = _email_domain(email)
    verified = {d.strip().lower() for d in (connection.verified_domains or [])}
    if not domain or domain not in verified:
        raise EnterpriseLoginError(
            "domain_not_verified",
            "the asserted email is outside this connection's verified domains",
        )

    # (2) Differential trust on the weaker (unsigned) UserInfo-endpoint claims path.
    # A cryptographically-validated source (the OIDC id_token) is trusted; the
    # endpoint fallback is not signed, so there we require email_verified=true.
    if (
        asserted.claims_source not in _VALIDATED_CLAIMS_SOURCES
        and asserted.attributes.get("email_verified") is not True
    ):
        raise EnterpriseLoginError(
            "unverified_fallback",
            "unsigned UserInfo claims must assert email_verified=true",
        )
    return email


def _org_membership_id(store: Any, identity_id: str, tenant_id: str) -> str | None:
    """The id of ``identity_id``'s membership (any status) in ``tenant_id``, or ``None``."""
    for membership in store.get_memberships_for_identity(identity_id):
        if membership.tenant_id == tenant_id:
            return str(membership.id)
    return None


def provision_enterprise_login(
    store: Any,
    connection: ConnectionRecord,
    asserted: AssertedIdentity,
) -> tuple[Any, str]:
    """Turn a provider's ``AssertedIdentity`` into ``(UserRecord, membership_id)``.

    Each step is fail-closed:

    1. **Anti-hijack** — the asserted email's domain MUST be in
       ``connection.verified_domains`` (an org IdP can only assert identities within
       the domains it has proven it controls).
    2. **Differential trust** — a non-``id_token`` ``claims_source`` (the unsigned
       UserInfo-endpoint fallback) MUST carry ``email_verified=true``; the provider
       tolerates a *missing* ``email_verified`` only on the validated id_token path.
    3. Resolve/create the global Identity by verified email (passwordless).
    4. Reuse an existing membership for (identity, org), else JIT-create one (gated by
       ``connection.config['jit_provisioning']``, default ``True``) with roles mapped
       from the asserted groups (default-deny).

    Raises ``EnterpriseLoginError`` (with a stable ``reason``) on any refusal.
    """
    email = _trusted_email(connection, asserted)

    # (3) Resolve/create the global Identity (passwordless — the IdP proof is the auth).
    user = store.get_user_by_email(email)
    if user is None:
        user = store.create_user(email=email, password=secrets.token_urlsafe(48), username=None)

    # Reaching here means the org IdP vouched for this email within a domain it has
    # proven it controls (id_token-validated, or email_verified=true on the unsigned
    # fallback) — strong proof the mailbox is controlled. Mark the global identity
    # verified so downstream paths (e.g. invitation acceptance's email_verified gate)
    # don't treat an SSO-proven identity as unverified. Idempotent; only write when
    # not already verified to avoid a DB write on every login.
    if not getattr(user, "email_verified", False):
        store.mark_email_verified(str(user.id))

    # (4) Reuse an existing membership (any status) for this org — never duplicate.
    identity_id = str(user.id)
    existing = _org_membership_id(store, identity_id, connection.tenant_id)
    if existing is not None:
        return user, existing

    if not (connection.config or {}).get("jit_provisioning", True):
        # JIT disabled: identity exists, but no membership here. The route turns this
        # into "ask an org admin to invite you" rather than silently granting access.
        raise EnterpriseLoginError(
            "no_membership",
            "no membership in this organization and JIT provisioning is disabled",
        )

    roles = map_groups_to_roles(asserted.groups, connection.group_mapping or {})
    try:
        membership = store.create_membership(
            tenant_id=connection.tenant_id,
            identity_id=identity_id,
            roles=roles,
            reason=f"enterprise SSO JIT ({connection.type}/{connection.provider})",
        )
    except _UniqueViolation:
        # A concurrent login won the (org, identity) unique constraint between our
        # reuse-scan and this insert — re-resolve to that membership, don't 500.
        winner = _org_membership_id(store, identity_id, connection.tenant_id)
        if winner is None:
            raise
        return user, winner
    return user, membership.id


def sso_required_for(email: str, store: Any) -> ConnectionRecord | None:
    """The OIDC connection that requires SSO for ``email``, or ``None`` (DD-013).

    Resolves through ``get_connection_by_verified_domain`` — VERIFIED domains of
    active OIDC connections only — so an org can only take local sign-in away from a
    domain it has proven it owns (org-fenced through the connection's tenant). An
    unverified claim, or a connection without ``config["require_sso"] is True``,
    leaves local sign-in untouched. Superusers are not exempt: the check is on the
    address, before any credential is evaluated.
    """
    domain = _email_domain((email or "").strip())
    if not domain:
        return None
    conn = store.get_connection_by_verified_domain(domain, types=("oidc",))
    if conn is None or (conn.config or {}).get("require_sso") is not True:
        return None
    result: ConnectionRecord = conn
    return result


def sso_redirect_for(request: Any, store: Any, email: str, *, next_path: str = "") -> str | None:
    """The enterprise login URL when ``require_sso`` refuses ``email``'s local sign-in.

    ``None`` means carry on: OIDC is not mounted on this app, or
    :func:`sso_required_for` finds no connection requiring SSO for the address.
    ``next_path`` must already be validated by the caller.
    """
    if not getattr(request.app.state, ENTERPRISE_OIDC_STATE_ATTR, False):
        return None
    if sso_required_for(email, store) is None:
        return None
    params = {"email": email.strip().lower()}
    if next_path:
        params["next"] = next_path
    return f"{ENTERPRISE_LOGIN_PATH}?{urlencode(params)}"


def sso_required_json(login_url: str) -> JSONResponse:
    """The JSON refusal for API callers: ``{"status": "sso_required", "login_url": ...}``."""
    return JSONResponse(
        status_code=SSO_REQUIRED_STATUS,
        content={"status": "sso_required", "login_url": login_url},
    )
