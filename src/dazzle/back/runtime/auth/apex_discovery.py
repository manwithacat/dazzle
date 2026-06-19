"""Apex tenant discovery — Phase B of multi-tenant login (#1404).

When an **authenticated** identity hits the **apex** (canonical) host — the
shared-domain landing, not a tenant subdomain — route them to where their
membership(s) say they belong:

* exactly one active membership  → 302 to ``https://{slug}.{domain}/`` (their org host)
* two or more active memberships → the org picker (``/auth/select-org``)
* zero active memberships        → the "no orgs yet" page (``/auth/no-orgs``)

This module is the **pure decision mapper** (no request, no DB, no FastAPI) so it
is exhaustively unit-tested; the thin ``ApexDiscoveryMiddleware`` glue (gating +
auth/membership reads + the ``tenant_id → slug`` closure) lives in ``app_factory``.

It reuses the Phase-2 ``resolve_activation`` (with ``host_tenant_id=None``, since
the apex is not host-pinned), so the apex landing and the in-host login share one
membership-resolution rule. Fail-safe: any case it can't resolve returns ``None``
(pass through to the normal apex page) rather than guessing a redirect.
"""

from __future__ import annotations

from collections.abc import Callable

from dazzle.back.runtime.auth.models import MembershipRecord
from dazzle.back.runtime.auth.org_activation import (
    Activated,
    NeedsPicker,
    NoOrgs,
    resolve_activation,
)
from dazzle.back.runtime.slug_validator import validate_slug

PICKER_PATH = "/auth/select-org"
NO_ORGS_PATH = "/auth/no-orgs"


def resolve_apex_redirect(
    memberships: list[MembershipRecord],
    *,
    domain: str,
    slug_for_tenant: Callable[[str], str | None],
    memberships_required: bool,
) -> str | None:
    """Decide where to send an authed identity that hit the apex root, or ``None``.

    ``slug_for_tenant`` maps an active membership's ``tenant_id`` to that org's
    host slug (the glue builds it from the resolver's ``fetch_by_id`` + the kind's
    ``slug_field``). ``memberships_required`` is the app's membership-model gate
    (ADR-0037 / #1418): when an app does NOT gate on membership, a zero-membership
    identity is **not** routed to ``/auth/no-orgs`` — the apex is just its landing,
    so pass through (``None``).

    Returns an absolute ``https://{slug}.{domain}/`` URL for the single-org case (a
    cross-host redirect, so it cannot loop on the apex), a relative apex path for
    the picker / no-orgs cases, or ``None`` to serve the apex page unchanged.
    """
    outcome = resolve_activation(memberships=memberships, host_tenant_id=None)

    if isinstance(outcome, Activated):
        tenant_id = next((m.tenant_id for m in memberships if m.id == outcome.membership_id), None)
        slug = slug_for_tenant(tenant_id) if tenant_id is not None else None
        if not slug:
            return None  # can't resolve the org host → fail safe, don't redirect
        try:
            validate_slug(slug)  # never build a redirect from an unvalidated slug
        except ValueError:
            return None
        return f"https://{slug}.{domain}/"

    if isinstance(outcome, NeedsPicker):
        return PICKER_PATH

    if isinstance(outcome, NoOrgs):
        # Only a membership-gated app routes an org-less identity to "no orgs yet".
        # An ungated app's apex is its own landing — leave it be.
        return NO_ORGS_PATH if memberships_required else None

    return None
