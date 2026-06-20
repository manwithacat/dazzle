"""Verified-domain join orchestration (#1424 phase 3).

``apply_domain_join`` is the single entry-point that composes:

  * ``resolve_domain_tenant`` — find the tenant for the email's domain;
  * ``OrgSettings`` — read the tenant's join policy;
  * ``decide_domain_join`` — pure outcome mapper (Off / AutoJoin /
    NeedsApproval / Noop);
  * ``assert_domain_admissible`` — fail-closed admission gate (even for
    AutoJoin — a tenant can restrict membership to its verified domains);
  * ``store.create_membership`` / ``store.create_join_request`` — the write
    side-effects.

Callers are responsible for only invoking this for a verified identity; the
``email_verified`` param is forwarded into ``decide_domain_join`` so an
unverified email is always a ``Noop`` (fail-closed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from dazzle.http.runtime.auth.domain_join import (
    AutoJoin,
    NeedsApproval,
    assert_domain_admissible,
    decide_domain_join,
    resolve_domain_tenant,
)
from dazzle.http.runtime.auth.org_settings import OrgSettings


@dataclass
class ApplyResult:
    """Outcome of ``apply_domain_join``.

    ``kind`` is one of:
      * ``"joined"``  — membership created; ``membership_id`` carries its id;
      * ``"pending"`` — join request created, awaiting admin approval;
      * ``"none"``    — no action taken (policy off, no tenant, unverified
                        email, or pre-existing membership).
    """

    kind: Literal["joined", "pending", "none"]
    membership_id: str | None = field(default=None)


def apply_domain_join(
    store: Any,
    *,
    identity_id: str,
    email: str,
    email_verified: bool,
) -> ApplyResult:
    """Orchestrate a verified-domain self-service join attempt.

    Steps:
    1. Resolve which tenant (if any) owns this email's verified domain.
    2. If none → return ``ApplyResult("none")``.
    3. Compute whether the identity already holds a membership in that tenant.
    4. Read the tenant's ``OrgSettings`` to get the join policy.
    5. Call ``decide_domain_join`` to get the outcome.
    6. Execute the outcome:
       - ``AutoJoin``     → ``assert_domain_admissible`` (may raise
                             ``DomainNotAdmissibleError``), then
                             ``store.create_membership``.
       - ``NeedsApproval`` → ``store.create_join_request``.
       - ``Off`` / ``Noop`` → no-op.

    Args:
        store: Auth store instance (real or fake) exposing the methods
            described in ``dazzle.http.runtime.auth.store``.
        identity_id: The global identity id of the authenticating user.
        email: The user's email address (used to resolve the domain tenant
            and passed to ``create_join_request``).
        email_verified: Whether the email has been verified. An unverified
            email always results in ``ApplyResult("none")`` (fail-closed).

    Returns:
        An ``ApplyResult`` describing what happened.

    Raises:
        DomainNotAdmissibleError: If the tenant restricts membership to its
            verified domains and the email's domain is not among them (even
            for ``auto_join`` policy).
    """
    tenant_id = resolve_domain_tenant(store, email)
    if tenant_id is None:
        return ApplyResult(kind="none")

    memberships = store.get_memberships_for_identity(identity_id)
    has_membership = any(m.tenant_id == tenant_id for m in memberships)

    settings = OrgSettings.from_dict(store.get_org_settings(tenant_id))
    outcome = decide_domain_join(
        settings.domain_join_policy,
        email_verified=email_verified,
        has_membership=has_membership,
    )

    if isinstance(outcome, AutoJoin):
        assert_domain_admissible(store, tenant_id, email)
        membership = store.create_membership(
            tenant_id=tenant_id,
            identity_id=identity_id,
            roles=[],
            reason="verified-domain self-service join",
        )
        return ApplyResult(kind="joined", membership_id=membership.id)

    if isinstance(outcome, NeedsApproval):
        store.create_join_request(
            tenant_id=tenant_id,
            identity_id=identity_id,
            email=email,
        )
        return ApplyResult(kind="pending")

    # Off or Noop
    return ApplyResult(kind="none")
