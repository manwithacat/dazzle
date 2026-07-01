"""Cross-tenant session guard (#1289 slice 5).

Enforces the truth table from the design spec so a tenant-bound cookie
can't be reused on a different tenant's host, and an apex super-admin
cookie can't be presented on a tenant host without the super-admin role.

The auth dependency calls `check_cross_tenant()` after loading the user
from the session and either passes through (returning `GuardOutcome.PASS`)
or raises one of three typed exceptions, which the dependency translates
to HTTP 403 with specific error codes.

#1518: the session's bound tenant is the **active membership's `tenant_id`**
(the org id, which equals `ResolvedTenant.id`), NOT a slug on the user object.
The original wiring read a `user.tenant_slug` attribute that no production
`UserRecord` carries, so `session_tenant_id` was always `None` and every
host-bound request false-403'd (surfaced by magic-link QA sessions). The
comparison is id-based and honours the ADR-0037 hierarchy: a member of an
**ancestor** tenant (e.g. the Trust root) reaches a descendant host, so the
session passes when its bound tenant is the host **or any of the host's
ancestors**. A host-bound cookie that carries no active-membership binding
fails **closed** — every membership-gated `tenant_host:` login binds a
membership, so this only rejects the unexercised `membership_gated: false`
path.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal


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
    session_tenant_id: str | None,
    request_tenant_id: str | None,
    request_ancestor_ids: tuple[str, ...] = (),
    user_role: str,
    super_admin_role: str,
) -> GuardOutcome:
    """Apply the cross-tenant truth table; pass or raise.

    `cookie_kind` is None for unauthenticated requests (no session cookie).
    `session_tenant_id` is `str(active_membership.tenant_id)`, or None when the
    session has no active membership. `request_tenant_id` is `str(ResolvedTenant.id)`,
    or None for an apex (no-tenant) request; `request_ancestor_ids` is the host's
    `parent:` chain ids (ADR-0037), so a member of an ancestor tenant passes.
    """
    if cookie_kind is None:
        return GuardOutcome.PASS

    if cookie_kind == "host":
        if request_tenant_id is None:
            raise HostCookieMissingTenant("host-bound cookie presented on apex (no tenant) request")
        if session_tenant_id is None:
            # Fail-closed (#1518): a host-bound cookie whose session carries no
            # active-membership tenant binding cannot be proven to belong to this
            # host. Every membership-gated tenant_host login binds a membership,
            # so this only rejects the unexercised membership_gated:false path.
            raise HostCookieMissingTenant(
                "host-bound cookie carries no active-membership tenant binding"
            )
        acceptable = {request_tenant_id, *request_ancestor_ids}
        if session_tenant_id not in acceptable:
            raise CrossTenantForbidden(
                f"host-bound cookie for tenant {session_tenant_id!r} "
                f"presented on {request_tenant_id!r}"
            )
        return GuardOutcome.PASS

    # cookie_kind == "apex"
    if user_role != super_admin_role:
        raise ApexCookieNotSuperAdmin(
            f"apex cookie presented by role {user_role!r}, requires {super_admin_role!r}"
        )
    return GuardOutcome.PASS
