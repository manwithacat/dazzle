"""Two-phase auth: Phase-2 org-context activation (auth Plan 1b).

Phase 1 (prove identity) lives in the existing login routes. This module is
Phase 2: given the proven identity's memberships and an optional host-pinned org
id, decide which org context the session activates — or whether the user must
pick, has no orgs, or is forbidden on this host.

The core resolver is pure (no DB, no request) so it is exhaustively unit-tested;
``host_tenant_id_from_request`` and ``activate_session_for_login`` are the thin
glue that read the request + the auth store. ``_login_redirect_for_outcome`` is
the single mapper every interactive login route shares, so the picker / no-orgs
/ 403 behaviour is defined once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle.back.runtime.auth.models import MembershipRecord


@dataclass(frozen=True)
class Activated:
    """Exactly one org context resolved — bind this membership to the session."""

    membership_id: str


@dataclass(frozen=True)
class NeedsPicker:
    """The identity has >1 active membership and no host pin — show the picker."""

    memberships: tuple[MembershipRecord, ...]


@dataclass(frozen=True)
class NoOrgs:
    """The identity has no active membership — "no orgs yet" (await invite/create)."""


@dataclass(frozen=True)
class HostForbidden:
    """Host-pinned to an org the identity has no active membership in → 403."""


ActivationOutcome = Activated | NeedsPicker | NoOrgs | HostForbidden

# Sentinel redirect target meaning "raise 403" — the caller turns it into an
# HTTPException so this pure module stays free of FastAPI imports.
FORBIDDEN_SENTINEL = "__forbidden__"


def resolve_activation(
    *, memberships: list[MembershipRecord], host_tenant_id: str | None
) -> ActivationOutcome:
    """Pure Phase-2 decision.

    ``host_tenant_id`` is ``str(ResolvedTenant.id)`` when the request is
    host-pinned (subdomain → org, #1289), else None (shared-domain switcher).
    Only ``status="active"`` memberships are eligible (a suspended/invited
    membership must never silently scope the session).
    """
    active = [m for m in memberships if m.status == "active"]
    if host_tenant_id is not None:
        match = next((m for m in active if m.tenant_id == host_tenant_id), None)
        return Activated(match.id) if match is not None else HostForbidden()
    if not active:
        return NoOrgs()
    if len(active) == 1:
        return Activated(active[0].id)
    return NeedsPicker(tuple(active))


def host_tenant_id_from_request(request: Any) -> str | None:
    """The host-pinned org id (``str``) for this request, or None.

    ``TenantResolutionMiddleware`` (#1289) sets ``request.state.tenant`` to a
    ``ResolvedTenant`` for a subdomain-pinned host, or ``None`` for the canonical
    host / apps without ``tenant_host:``. Organization IS the tenant root, so the
    resolved tenant's ``id`` is the membership discriminator (``tenant_id``).
    """
    state = getattr(request, "state", None)
    resolved = getattr(state, "tenant", None) if state is not None else None
    tid = getattr(resolved, "id", None)
    return str(tid) if tid is not None else None


def memberships_required(request: Any) -> bool:
    """Whether this app has opted into the membership model (Plan 1c gate).

    Default False: pre-1c apps have no memberships, so a zero-membership login
    proceeds with the legacy fence (see ``_login_redirect_for_outcome``).
    """
    state = getattr(getattr(request, "app", None), "state", None)
    return bool(getattr(state, "memberships_required", False))


def derive_memberships_required(appspec: Any, *, auto_provision: bool) -> bool:
    """Whether membership-gated login is on for this app (#1393 Phase A).

    True when EITHER:
      * ``auto_provision`` (``auto_provision_single_org``) is set — the original
        Plan 1c gate; or
      * the app declares ``tenant_host:`` on any entity — declaring host-based
        tenancy IMPLIES membership gating, so a non-member on a tenant host gets a
        clean 403 (host-pin path) and an org-less identity on the canonical host
        routes to ``/auth/no-orgs`` rather than a silently-empty legacy session.

    Detected the same way ``app_factory`` decides whether to mount the tenant
    middleware: any ``domain.entities`` member with a non-None ``tenant_host``.
    """
    if auto_provision:
        return True
    entities = getattr(getattr(appspec, "domain", None), "entities", None) or []
    return any(getattr(e, "tenant_host", None) is not None for e in entities)


def single_org_auto_provision(request: Any) -> bool:
    """Whether this app lazily provisions a single default org at activation
    (Plan 1c). Default False — pre-1c / multi-org apps don't auto-provision."""
    state = getattr(getattr(request, "app", None), "state", None)
    return bool(getattr(state, "single_org_auto_provision", False))


def activate_session_for_login(auth_store: Any, user: Any, request: Any) -> ActivationOutcome:
    """Resolve Phase 2 for a just-proven ``user`` on this ``request``.

    Plan 1c: when the app opts into single-org auto-provision and the identity
    has no membership *and* the request is not host-pinned, lazily ensure a
    default-org membership first. This makes single-org Phase 2 invisible and
    backfills pre-1c users on next login. The host-pin guard is load-bearing: a
    host-pinned request names a specific org, so a missing membership there must
    stay ``HostForbidden`` (403) — never silently provision a default and admit.
    """
    host_tenant_id = host_tenant_id_from_request(request)
    memberships = auth_store.get_memberships_for_identity(str(user.id))
    if not memberships and host_tenant_id is None and single_org_auto_provision(request):
        # Plan 1d: pass the AppSpec so an is_tenant_root app provisions the org
        # with a matching tenant-root row at the shared id (1:1 mirror); a
        # rootless app falls back to the framework-org behaviour (appspec=None).
        app_state = getattr(getattr(request, "app", None), "state", None)
        appspec = getattr(app_state, "appspec", None)
        auth_store.ensure_single_org_membership(user, appspec=appspec)
        memberships = auth_store.get_memberships_for_identity(str(user.id))
    return resolve_activation(memberships=memberships, host_tenant_id=host_tenant_id)


def _login_redirect_for_outcome(
    outcome: ActivationOutcome, next_target: str, *, memberships_required: bool = False
) -> tuple[str | None, str]:
    """Map a Phase-2 activation outcome → ``(active_membership_id, redirect_path)``.

    ``active_membership_id`` is None unless exactly one org resolved.
    ``HostForbidden`` is signalled by the ``FORBIDDEN_SENTINEL`` redirect, which
    the caller turns into a 403.

    ``memberships_required`` is the transition gate. Until Plan 1c auto-provisions
    a single-org membership at signup, *no existing app has memberships*, so a
    zero-membership identity (``NoOrgs``) must keep logging in exactly as before —
    a membership-less session that falls back to the legacy preferences-sourced
    fence (1a). Only an app that has opted into the membership model
    (``app.state.memberships_required``, set by 1c) routes a genuinely org-less
    user to the "no orgs yet" page. ``NeedsPicker`` (≥2 memberships) always
    intercepts — a user with multiple orgs is unambiguously membership-based.
    """
    if isinstance(outcome, Activated):
        return outcome.membership_id, next_target
    if isinstance(outcome, NeedsPicker):
        return None, "/auth/select-org"
    if isinstance(outcome, HostForbidden):
        return None, FORBIDDEN_SENTINEL
    # NoOrgs
    if memberships_required:
        return None, "/auth/no-orgs"
    return None, next_target  # legacy transition: membership-less session, proceed
