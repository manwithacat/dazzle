"""Ephemeral QA test-tenant provisioning + teardown (RLS Phase E.2, #1339).

A QA test tenant is a framework ``organizations`` row (``slug=qa-<run_id>``,
``is_test=true``) plus a seeded admin identity + membership — the framework org
IS the tenant (no domain tenant-root row, so no Plan-1d coupling). Teardown
reuses the E.1 excision primitive.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

QA_SLUG_PREFIX = "qa-"


@dataclass
class ProvisionedTestTenant:
    org: Any  # OrganizationRecord
    admin: Any  # UserRecord


def provision_test_tenant(
    auth_store: Any,
    run_id: str,
    *,
    roles: list[str] | tuple[str, ...] = ("admin",),
    admin_email: str | None = None,
) -> ProvisionedTestTenant:
    """Provision an ephemeral, reserved-namespace, is_test org + admin (Phase E.2).

    ``slug = qa-<run_id>`` (the reserved namespace, with the unforgeable +
    queryable ``is_test`` flag the containment invariant keys off). The admin gets
    a random password (login is via the signed QA mint, not credentials) and a
    membership in the org carrying ``roles``.
    """
    org = auth_store.create_organization(
        slug=f"{QA_SLUG_PREFIX}{run_id}", name=f"QA {run_id}", is_test=True
    )
    email = admin_email or f"qa-admin-{run_id}@qa.test"
    admin = auth_store.create_user(
        email=email, password=secrets.token_urlsafe(32), roles=list(roles)
    )
    auth_store.create_membership(tenant_id=org.id, identity_id=str(admin.id), roles=list(roles))
    return ProvisionedTestTenant(org=org, admin=admin)


def teardown_test_tenant(appspec: Any, org_id: str, *, conn: Any) -> Any:
    """Excise a provisioned QA tenant (delegates to the E.1 engine)."""
    from dazzle.db.excision import excise_tenant

    return excise_tenant(appspec, org_id, conn=conn)
