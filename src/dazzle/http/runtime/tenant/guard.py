"""Cross-tenant session guard (#1289 slice 5).

Enforces the truth table from the design spec so a tenant-bound cookie
can't be reused on a different tenant's host, and an apex super-admin
cookie can't be presented on a tenant host without the super-admin role.

The auth dependency calls `check_cross_tenant()` after loading the user
from the session and either passes through (returning `GuardOutcome.PASS`)
or raises one of three typed exceptions, which the dependency translates
to HTTP 403 with specific error codes.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from dazzle.http.runtime.tenant.resolver import ResolvedTenant


class GuardOutcome(Enum):
    PASS = "pass"


class CrossTenantForbidden(Exception):
    pass


class HostCookieMissingTenant(Exception):
    pass


class ApexCookieNotSuperAdmin(Exception):
    pass


def check_cross_tenant(
    *,
    cookie_kind: Literal["host", "apex"] | None,
    session_tenant_slug: str | None,
    request_tenant: ResolvedTenant | None,
    user_role: str,
    super_admin_role: str,
) -> GuardOutcome:
    """Apply the cross-tenant truth table; pass or raise.

    `cookie_kind` is None for unauthenticated requests (no session cookie).
    """
    if cookie_kind is None:
        return GuardOutcome.PASS

    if cookie_kind == "host":
        if request_tenant is None:
            raise HostCookieMissingTenant("host-bound cookie presented on apex (no tenant) request")
        if request_tenant.slug != session_tenant_slug:
            raise CrossTenantForbidden(
                f"host-bound cookie for {session_tenant_slug!r} "
                f"presented on {request_tenant.slug!r}"
            )
        return GuardOutcome.PASS

    # cookie_kind == "apex"
    if user_role != super_admin_role:
        raise ApexCookieNotSuperAdmin(
            f"apex cookie presented by role {user_role!r}, requires {super_admin_role!r}"
        )
    return GuardOutcome.PASS
