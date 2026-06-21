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
from dazzle.http.runtime.auth.models import AlreadyDecidedError
from dazzle.http.runtime.auth.org_settings import OrgSettings

__all__ = [
    "AlreadyDecidedError",
    "ApplyResult",
    "apply_domain_join",
    "approve_join_request",
    "deny_join_request",
]


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
    if not email_verified:
        return ApplyResult(kind="none")

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


def approve_join_request(store: Any, request_id: str, *, decided_by: str) -> Any:
    """Approve a *pending* join request: create the membership, then mark approved.

    Security-sensitive — approval CREATES a membership. The ordering matters:

    1. Load the request; ``LookupError``-shaped guards apply — if it is missing or
       no longer ``pending`` the decision step raises ``AlreadyDecidedError``.
    2. ``assert_domain_admissible`` — the tenant's verified-domain restriction is
       re-checked at *decision* time (it may have been enabled after the request
       was filed); raises ``DomainNotAdmissibleError`` and creates nothing.
    3. ``store.create_membership`` with default-deny roles (``[]``).
    4. ``store.decide_join_request(status="approved")`` — the pending-only guard.

    Double-decide defence: a second approve of an already-decided request hits the
    store's pending-only guard at step 4 → ``AlreadyDecidedError``. Because that
    guard is the *last* step, a concurrent double-submit could in principle create
    a membership whose decide loses the race; that path is covered by
    ``create_membership``'s idempotent (tenant_id, identity_id) unique constraint —
    so the roster still holds exactly one membership. The single-process
    double-submit covered by the tests creates exactly one membership.

    Args:
        store: Auth store (real or fake).
        request_id: The join request id.
        decided_by: The deciding admin's id (audit: ``decided_by``).

    Returns:
        The decided ``JoinRequestRecord`` (status ``approved``).

    Raises:
        AlreadyDecidedError: The request is missing or no longer pending.
        DomainNotAdmissibleError: The tenant now restricts membership to its
            verified domains and this request's email is not admissible.
    """
    jr = store.get_join_request(request_id)
    if jr is None or jr.status != "pending":
        # Fail fast with the same error the pending-only store guard would raise,
        # before any admission check or membership write.
        raise AlreadyDecidedError(request_id)
    assert_domain_admissible(store, jr.tenant_id, jr.email)
    store.create_membership(
        tenant_id=jr.tenant_id,
        identity_id=jr.identity_id,
        roles=[],
        reason="verified-domain join approved",
    )
    return store.decide_join_request(request_id, status="approved", decided_by=decided_by)


def deny_join_request(store: Any, request_id: str, *, decided_by: str) -> Any:
    """Deny a *pending* join request — mark denied, create no membership.

    Raises ``AlreadyDecidedError`` if the request is missing or already decided.
    """
    return store.decide_join_request(request_id, status="denied", decided_by=decided_by)
