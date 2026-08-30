"""Apex tenant discovery — Phase B of multi-tenant login (#1404).

When an **authenticated** identity hits the **apex** (canonical) host — the
shared-domain landing, not a tenant subdomain — route them to where their
membership(s) say they belong:

* exactly one active membership  → 302 to ``https://{slug}.{domain}/``
  **only when** ``topology == provider_subdomain`` **and**
  ``cookie_scope: apex``. Topology A never slug-bounces (ADR-0055).
  Default ``cookie_scope: host`` stays on the canonical host — ``__Host-*``
  cookies cannot travel to the slug host (#1657).
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

from dazzle.http.runtime.auth.models import MembershipRecord
from dazzle.http.runtime.auth.org_activation import (
    Activated,
    NeedsPicker,
    NoOrgs,
    resolve_activation,
)
from dazzle.http.runtime.slug_validator import validate_slug

PICKER_PATH = "/auth/select-org"
NO_ORGS_PATH = "/auth/no-orgs"


# Cheap bounce counter for PR1 regression detector
# (dazzle_apex_bounce_total{topology,outcome}). Tests read this dict.
_BOUNCE_COUNTS: dict[tuple[str, str], int] = {}


def note_apex_bounce(topology: str, outcome: str) -> None:
    key = (topology or "", outcome)
    _BOUNCE_COUNTS[key] = _BOUNCE_COUNTS.get(key, 0) + 1


def resolve_apex_redirect(
    memberships: list[MembershipRecord],
    *,
    domain: str,
    slug_for_tenant: Callable[[str], str | None],
    memberships_required: bool,
    cookie_scope: str = "host",
    topology: str = "apex",
) -> str | None:
    """Decide where to send an authed identity that hit the apex root, or ``None``.

    ``slug_for_tenant`` maps an active membership's ``tenant_id`` to that org's
    host slug (the glue builds it from the resolver's ``fetch_by_id`` + the kind's
    ``slug_field``). ``memberships_required`` is the app's membership-model gate
    (ADR-0037 / #1418): when an app does NOT gate on membership, a zero-membership
    identity is **not** routed to ``/auth/no-orgs`` — the apex is just its landing,
    so pass through (``None``).

    ``cookie_scope`` is the cookie-name / bounce-intent knob. ``topology`` is
    the ADR-0055 hosting plane (runtime ``str`` so leftover tokens never
    invent B). Cross-host slug bounce fires only when
    ``topology == "provider_subdomain"`` **and** ``cookie_scope == "apex"``.
    That bounce is not session sharing until Domain cookies are wired.
    Leftover topology/scope stay put (no invented bounce). Picker / no-orgs
    are same-host paths and do not consult topology.

    Returns an absolute ``https://{slug}.{domain}/`` URL for the B + apex
    cookie case, a relative apex path for picker / no-orgs, or ``None`` to
    serve the apex page unchanged.
    """
    outcome = resolve_activation(memberships=memberships, host_tenant_id=None)

    if isinstance(outcome, Activated):
        if topology != "provider_subdomain" or cookie_scope != "apex":
            note_apex_bounce(topology, "suppressed")
            return None
        tenant_id = next((m.tenant_id for m in memberships if m.id == outcome.membership_id), None)
        slug = slug_for_tenant(tenant_id) if tenant_id is not None else None
        if not slug:
            return None  # can't resolve the org host → fail safe, don't redirect
        try:
            validate_slug(slug)  # never build a redirect from an unvalidated slug
        except ValueError:
            return None
        url = f"https://{slug}.{domain}/"
        note_apex_bounce(topology, "redirect")
        return url

    if isinstance(outcome, NeedsPicker):
        return PICKER_PATH

    if isinstance(outcome, NoOrgs):
        # Only a membership-gated app routes an org-less identity to "no orgs yet".
        # An ungated app's apex is its own landing — leave it be.
        return NO_ORGS_PATH if memberships_required else None

    return None
