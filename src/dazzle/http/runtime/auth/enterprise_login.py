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
"""

from __future__ import annotations

import secrets
from typing import Any

from psycopg.errors import UniqueViolation as _UniqueViolation

from dazzle.http.runtime.auth.connections import AssertedIdentity, ConnectionRecord

# Claims sources whose email is cryptographically validated by the provider and may be
# trusted directly: an OIDC ``id_token`` (authlib-verified signature/iss/aud/exp/nonce) and
# a SAML ``saml_assertion`` (python3-saml-verified XML signature against the IdP cert). The
# OIDC UserInfo-endpoint fallback (``userinfo_endpoint``) is NOT here — its claims aren't
# signed, so they additionally require an explicit ``email_verified=true``.
_VALIDATED_CLAIMS_SOURCES = frozenset({"id_token", "saml_assertion"})


class EnterpriseLoginError(RuntimeError):
    """An enterprise SSO assertion cannot be turned into a membership.

    ``reason`` is a stable machine code (``domain_not_verified`` / ``no_email`` /
    ``unverified_fallback`` / ``no_membership``) the route maps to a user-facing
    error; the message is human detail. Never carries the asserted email or any
    secret (kept out of logs / redirect query strings).
    """

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


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
    # A cryptographically-validated source (OIDC id_token / SAML assertion) is trusted;
    # the OIDC endpoint fallback is not signed, so there we require email_verified=true.
    if (
        asserted.claims_source not in _VALIDATED_CLAIMS_SOURCES
        and asserted.attributes.get("email_verified") is not True
    ):
        raise EnterpriseLoginError(
            "unverified_fallback",
            "unsigned UserInfo claims must assert email_verified=true",
        )

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
    for membership in store.get_memberships_for_identity(identity_id):
        if membership.tenant_id == connection.tenant_id:
            return user, membership.id

    if not (connection.config or {}).get("jit_provisioning", True):
        # JIT disabled: identity exists, but no membership here. The route turns this
        # into "ask an org admin to invite you" rather than silently granting access.
        raise EnterpriseLoginError(
            "no_membership",
            "no membership in this organization and JIT provisioning is disabled",
        )

    roles = map_groups_to_roles(asserted.groups, connection.group_mapping or {})
    # Uniform tenant admission gate (#1424): refuse JIT provisioning if the org
    # restricts membership to its verified domains and this email is off-domain.
    from dazzle.http.runtime.auth.domain_join import assert_domain_admissible

    assert_domain_admissible(store, connection.tenant_id, email)

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
        for membership in store.get_memberships_for_identity(identity_id):
            if membership.tenant_id == connection.tenant_id:
                return user, membership.id
        raise
    return user, membership.id
