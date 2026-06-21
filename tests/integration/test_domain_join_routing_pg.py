"""Live security-invariant tests: post-join routing + anti-enumeration (#1424 phase 5).

Three invariants proved end-to-end against a real scratch Postgres database:

1. **Post-join routing (auto_join):** A verified-email user with a matching verified
   domain gets a membership via ``apply_domain_join`` and apex discovery then resolves
   them to the tenant's host URL.

2. **No pre-membership routing (admin_approval):** Under ``admin_approval`` policy, a
   verified-email user gets a pending join request (no membership), and apex discovery
   does NOT route them to a tenant host — only after admin approval does a membership
   exist and routing resolve.

3. **Anti-enumeration:** ``apply_domain_join`` returns kind=="none" for BOTH (a) an
   unverified email whose domain maps to a tenant, and (b) an email whose domain maps to
   no tenant — an unauthenticated probe cannot distinguish the two cases.
"""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture(autouse=True)
def _conn_key(monkeypatch):
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())


@pytest.fixture
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_djroute_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (scratch,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _store(store_url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    s = AuthStore(database_url=store_url)
    s._init_db()
    return s


class _FakeResolver:
    """Injected DNS resolver returning a fixed mapping of domain → TXT records."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._m = mapping

    def resolve_txt(self, domain: str) -> list[str]:
        return self._m.get(domain, [])


def _verify_domain_for_conn(store, conn, domain: str) -> None:
    """Helper: verify ``domain`` on ``conn`` via the txt_record idiom (mirrors existing tests)."""
    from dazzle.http.runtime.auth.domain_verification import txt_record, verify_domain

    resolver = _FakeResolver({domain: [txt_record(conn.id, domain)]})
    result = verify_domain(store, conn, domain, resolver=resolver)
    assert result is True, f"Domain verification failed for {domain!r}"


# ---------------------------------------------------------------------------
# Invariant 1: post-join routing — auto_join policy
# ---------------------------------------------------------------------------


def test_auto_join_creates_membership_and_apex_routes_to_tenant(store_url: str) -> None:
    """After auto_join, membership exists and apex discovery returns the tenant host URL."""
    from dazzle.http.runtime.auth.apex_discovery import resolve_apex_redirect
    from dazzle.http.runtime.auth.join_requests import apply_domain_join
    from dazzle.http.runtime.auth.org_settings import OrgSettings

    store = _store(store_url)

    # Provision org + domain connection + verify domain.
    org = store.create_organization(slug="acmecorp", name="Acme Corp")
    conn = store.create_connection(
        tenant_id=org.id,
        type="domain",
        config={},
        secrets={},
        domains=["acmecorp.example"],
    )
    _verify_domain_for_conn(store, conn, "acmecorp.example")

    # Set auto_join policy.
    settings = OrgSettings(domain_join_policy="auto_join")
    store.set_org_settings(org.id, settings.to_dict())

    # Create an identity whose email matches the verified domain.
    user = store.create_user(email="alice@acmecorp.example", password="test-pw-1")
    identity_id = str(user.id)

    # --- Security invariant: no membership exists before the join attempt ---
    pre_memberships = store.get_memberships_for_identity(identity_id)
    assert len(pre_memberships) == 0, "Should have zero memberships before apply_domain_join"

    # Apply domain join with verified email.
    result = apply_domain_join(
        store,
        identity_id=identity_id,
        email="alice@acmecorp.example",
        email_verified=True,
    )

    assert result.kind == "joined", f"Expected 'joined', got {result.kind!r}"
    assert result.membership_id is not None, "membership_id must be set on a 'joined' result"

    # Membership must now exist in the store.
    post_memberships = store.get_memberships_for_identity(identity_id)
    assert len(post_memberships) == 1
    assert post_memberships[0].tenant_id == org.id
    assert post_memberships[0].id == result.membership_id

    # Apex discovery routes to the tenant host.
    def slug_for_tenant(tid: str) -> str | None:
        fetched = store.get_organization(tid)
        return fetched.slug if fetched else None

    redirect = resolve_apex_redirect(
        post_memberships,
        domain="example.com",
        slug_for_tenant=slug_for_tenant,
        memberships_required=True,
    )

    assert redirect == "https://acmecorp.example.com/", (
        f"Expected routing to tenant host, got {redirect!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 2: no pre-membership routing — admin_approval policy
# ---------------------------------------------------------------------------


def test_admin_approval_blocks_routing_until_approved(store_url: str) -> None:
    """Under admin_approval: pending → no membership → apex doesn't route; approved → does route."""
    from dazzle.http.runtime.auth.apex_discovery import NO_ORGS_PATH, resolve_apex_redirect
    from dazzle.http.runtime.auth.join_requests import apply_domain_join, approve_join_request
    from dazzle.http.runtime.auth.org_settings import OrgSettings

    store = _store(store_url)

    org = store.create_organization(slug="pendingorg", name="Pending Org")
    conn = store.create_connection(
        tenant_id=org.id,
        type="domain",
        config={},
        secrets={},
        domains=["pendingorg.example"],
    )
    _verify_domain_for_conn(store, conn, "pendingorg.example")

    # Set admin_approval policy.
    settings = OrgSettings(domain_join_policy="admin_approval")
    store.set_org_settings(org.id, settings.to_dict())

    # Provision an admin identity (used to approve later) and the user.
    admin = store.create_user(email="admin@pendingorg.example", password="admin-pw-1")
    user = store.create_user(email="bob@pendingorg.example", password="user-pw-1")
    identity_id = str(user.id)

    # --- Phase A: apply → pending ---
    result = apply_domain_join(
        store,
        identity_id=identity_id,
        email="bob@pendingorg.example",
        email_verified=True,
    )
    assert result.kind == "pending", f"Expected 'pending', got {result.kind!r}"

    # --- Security invariant: NO membership must exist before approval ---
    pre_memberships = store.get_memberships_for_identity(identity_id)
    assert len(pre_memberships) == 0, (
        "Membership must NOT be created under admin_approval before the request is approved"
    )

    # --- Apex routing must NOT return a tenant host URL for a zero-membership identity ---
    def slug_for_tenant(tid: str) -> str | None:
        fetched = store.get_organization(tid)
        return fetched.slug if fetched else None

    redirect_before = resolve_apex_redirect(
        pre_memberships,  # empty list
        domain="example.com",
        slug_for_tenant=slug_for_tenant,
        memberships_required=True,
    )
    # Must be the "no orgs" path — not a tenant-host redirect.
    assert redirect_before == NO_ORGS_PATH, (
        f"Expected {NO_ORGS_PATH!r} for zero-membership identity, got {redirect_before!r}"
    )
    # Explicit: must never be a tenant-host URL.
    assert redirect_before != "https://pendingorg.example.com/", (
        "Apex routing must NEVER return a tenant-host URL for an un-approved join request"
    )

    # --- Phase B: admin approves the pending request ---
    pending_requests = store.get_pending_join_requests(org.id)
    assert len(pending_requests) == 1
    join_request_id = pending_requests[0].id

    decided = approve_join_request(store, join_request_id, decided_by=str(admin.id))
    assert decided.status == "approved"

    # --- Membership must now exist ---
    post_memberships = store.get_memberships_for_identity(identity_id)
    assert len(post_memberships) == 1
    assert post_memberships[0].tenant_id == org.id

    # --- Apex routing now resolves to the tenant host ---
    redirect_after = resolve_apex_redirect(
        post_memberships,
        domain="example.com",
        slug_for_tenant=slug_for_tenant,
        memberships_required=True,
    )
    assert redirect_after == "https://pendingorg.example.com/", (
        f"Expected tenant-host URL after approval, got {redirect_after!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 3: anti-enumeration oracle
# ---------------------------------------------------------------------------


def test_anti_enumeration_unverified_vs_no_tenant_same_response(store_url: str) -> None:
    """
    An unauthenticated probe cannot distinguish:
      (a) email whose domain maps to a tenant but the user is unverified, and
      (b) email whose domain maps to NO tenant.

    Both must return kind=="none" from apply_domain_join.
    """
    from dazzle.http.runtime.auth.join_requests import apply_domain_join
    from dazzle.http.runtime.auth.org_settings import OrgSettings

    store = _store(store_url)

    # Provision one org with a verified domain + auto_join policy.
    org = store.create_organization(slug="secretcorp", name="Secret Corp")
    conn = store.create_connection(
        tenant_id=org.id,
        type="domain",
        config={},
        secrets={},
        domains=["secretcorp.example"],
    )
    _verify_domain_for_conn(store, conn, "secretcorp.example")
    settings = OrgSettings(domain_join_policy="auto_join")
    store.set_org_settings(org.id, settings.to_dict())

    # Create a user identity to use as the probe.
    user = store.create_user(email="probe@secretcorp.example", password="probe-pw-1")
    identity_id = str(user.id)

    # --- Case (a): domain maps to tenant but email is UNVERIFIED ---
    result_unverified = apply_domain_join(
        store,
        identity_id=identity_id,
        email="probe@secretcorp.example",
        email_verified=False,  # unverified → must be a no-op
    )

    # --- Case (b): domain maps to NO tenant (different domain entirely) ---
    # Use the same identity but an email whose domain doesn't exist in any connection.
    result_no_tenant = apply_domain_join(
        store,
        identity_id=identity_id,
        email="probe@unknowndomain.example",
        email_verified=True,  # verified — but no tenant has this domain
    )

    # Both must return the same observable shape: kind=="none"
    assert result_unverified.kind == "none", (
        f"Unverified-email probe must return 'none', got {result_unverified.kind!r} — "
        "this is an enumeration oracle: a probe can tell whether the domain belongs to a tenant"
    )
    assert result_no_tenant.kind == "none", (
        f"No-tenant probe must return 'none', got {result_no_tenant.kind!r}"
    )

    # Neither case must have created a membership.
    memberships_after = store.get_memberships_for_identity(identity_id)
    assert len(memberships_after) == 0, (
        "No membership must be created for either enumeration-probe case"
    )

    # Response shape parity: both are indistinguishable (same kind, same membership_id=None).
    assert result_unverified.kind == result_no_tenant.kind, (
        "Response kind must be identical for both probe cases — "
        "any difference is an enumeration oracle"
    )
    assert result_unverified.membership_id is None
    assert result_no_tenant.membership_id is None
