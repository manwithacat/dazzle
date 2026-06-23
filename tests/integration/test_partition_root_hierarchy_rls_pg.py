"""#1463 canonical proof: a LEAF (School) membership in a two-level hierarchy
(Trust ▸ School) fences Trust-partitioned RLS data as a non-superuser, and stays
host-confined to its own School.

The bug: the RLS GUC bound the raw membership tenant (School), but rows are
partitioned at the archetype:tenant root (Trust), so the fence hid everything.
The fix stores ``partition_root_id`` on the membership (resolved at write time via
the tenant-host parent walk) and binds *that*. This test drives the real write
path (``create_membership`` with a hierarchy installed → real SQL walk on PG) and
the real fence, and asserts host-confinement via ``resolve_activation``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_proot_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _conn_url(scratch_url: str, role: str, password: str) -> str:
    head, _, hostpart = scratch_url.partition("://")
    host_only = hostpart.split("@")[-1].rpartition("/")[0]
    db = scratch_url.rpartition("/")[2]
    return f"{head}://{role}:{password}@{host_only}/{db}"


def _make_hierarchy_schema(scratch_url: str) -> None:
    """Trust(root) ◂ School(leaf) tenant kinds + a Trust-partitioned Report."""
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute('CREATE TABLE "Trust" (id uuid PRIMARY KEY, name text)')
        c.execute(
            'CREATE TABLE "School" (id uuid PRIMARY KEY, name text, '
            'trust uuid NOT NULL REFERENCES "Trust"(id))'
        )
        # Report is partitioned at the ROOT: its tenant_id column carries the Trust id.
        c.execute(
            'CREATE TABLE "Report" (id uuid PRIMARY KEY, title text, '
            'tenant_id uuid NOT NULL, school uuid NOT NULL REFERENCES "School"(id))'
        )


def test_leaf_membership_resolves_root_and_fences_to_it(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.partition_root import PartitionHierarchy
    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.http.runtime.rls_schema import build_rls_policy_ddl
    from dazzle.http.runtime.scope_filters import _resolve_user_attribute

    _make_hierarchy_schema(scratch_url)

    # Two roots (Trusts) each with one School; rows partitioned at the Trust.
    trust_a, trust_b = str(uuid.uuid4()), str(uuid.uuid4())
    school_a, school_b = str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute(
            'INSERT INTO "Trust" (id, name) VALUES (%s,%s),(%s,%s)',
            (trust_a, "Trust A", trust_b, "Trust B"),
        )
        c.execute(
            'INSERT INTO "School" (id, name, trust) VALUES (%s,%s,%s),(%s,%s,%s)',
            (school_a, "School A1", trust_a, school_b, "School B1", trust_b),
        )
        for tid, label, sch in ((trust_a, "A-report", school_a), (trust_b, "B-report", school_b)):
            c.execute(
                'INSERT INTO "Report" (id, title, tenant_id, school) VALUES (%s,%s,%s,%s)',
                (str(uuid.uuid4()), label, tid, sch),
            )

    # Real write path: create a LEAF (School A1) membership with the hierarchy
    # installed → create_membership runs the real SQL walk on PG.
    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.set_partition_hierarchy(PartitionHierarchy(parent_edges={"School": ("trust", "Trust")}))
    user = store.create_user(email="a@b.test", password="pw123456", roles=["staff"])
    m = store.create_membership(tenant_id=school_a, identity_id=str(user.id), roles=["staff"])

    # 1) write-path: partition_root_id is the Trust (root), not the raw School.
    assert m.partition_root_id == trust_a, "leaf membership must store the partition root (Trust A)"

    # 2) bind-path: _resolve_user_attribute('tenant_id') binds the root.
    ctx = type("Ctx", (), {"active_membership": m, "user": None, "preferences": {}})()
    assert _resolve_user_attribute("tenant_id", ctx) == trust_a

    # 3) real fence as a NON-superuser (superusers bypass RLS).
    role = f"proot_app_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(scratch_url, autocommit=True) as c:
        for stmt in build_rls_policy_ddl(["Report"], partition_key="tenant_id"):
            c.execute(stmt)  # nosemgrep — framework-generated DDL
        c.execute(
            f"CREATE ROLE \"{role}\" LOGIN PASSWORD 'app-pw' NOSUPERUSER NOBYPASSRLS"
        )  # nosemgrep
        c.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')  # nosemgrep
        c.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{role}"')  # nosemgrep

    try:
        # Bound to the resolved root (Trust A) → sees only Trust A's report.
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn:
            conn.execute("SELECT set_config('dazzle.tenant_id', %s, false)", (m.partition_root_id,))
            own = conn.execute('SELECT title FROM "Report"').fetchall()
            conn.rollback()
        # Bound to the RAW leaf tenant (School A1) → the OLD-bug binding → sees nothing
        # (rows are partitioned at the Trust, not the School). Proves why the fix matters.
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn_raw:
            conn_raw.execute("SELECT set_config('dazzle.tenant_id', %s, false)", (school_a,))
            raw = conn_raw.execute('SELECT count(*) FROM "Report"').fetchall()
            conn_raw.rollback()
        # Bound to a FOREIGN root (Trust B) → never sees Trust A's rows.
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn_f:
            conn_f.execute("SELECT set_config('dazzle.tenant_id', %s, false)", (trust_b,))
            foreign = {r[0] for r in conn_f.execute('SELECT title FROM "Report"').fetchall()}
            conn_f.rollback()
        # No GUC bound → restrictive fence denies all (fail-closed).
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn_n:
            denied = conn_n.execute('SELECT count(*) FROM "Report"').fetchall()
            conn_n.rollback()
    finally:
        with psycopg.connect(scratch_url, autocommit=True) as c:
            c.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"')  # nosemgrep
            c.execute(f'REVOKE USAGE ON SCHEMA public FROM "{role}"')  # nosemgrep
            c.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep

    assert {r[0] for r in own} == {"A-report"}, "root-bound leaf member sees its Trust's rows"
    assert raw[0][0] == 0, "raw-School binding (the #1463 bug) would have seen nothing"
    assert "A-report" not in foreign, "a foreign Trust must never see Trust A's rows"
    assert denied[0][0] == 0, "unbound dazzle.tenant_id denies all (fail-closed)"


def test_leaf_membership_host_confined_to_own_school(scratch_url: str) -> None:
    """Host-confinement keys off the LEAF tenant_id: the School-A1 member activates
    at its own School host but is HostForbidden at sibling School B1 (same tree)."""
    from dazzle.http.runtime.auth.models import MembershipRecord
    from dazzle.http.runtime.auth.org_activation import (
        Activated,
        HostForbidden,
        resolve_activation,
    )

    trust_a, trust_b = str(uuid.uuid4()), str(uuid.uuid4())
    school_a, school_b = str(uuid.uuid4()), str(uuid.uuid4())
    # A leaf membership at School A1 whose stored root is Trust A.
    m = MembershipRecord(
        id="m1", tenant_id=school_a, identity_id="u1", partition_root_id=trust_a, roles=["staff"]
    )

    # At its own School host (ancestor chain includes Trust A) → Activated.
    own = resolve_activation(memberships=[m], host_tenant_id=school_a, host_ancestor_ids=(trust_a,))
    assert isinstance(own, Activated) and own.membership_id == "m1"

    # At a sibling School host under a DIFFERENT trust → forbidden.
    sib = resolve_activation(memberships=[m], host_tenant_id=school_b, host_ancestor_ids=(trust_b,))
    assert isinstance(sib, HostForbidden), "sibling-school host (other trust) must be HostForbidden"

    # The critical #1463 invariant: a sibling School under the SAME trust (Trust A is
    # in the host's ancestor chain — the member's stored partition root!) must STILL be
    # HostForbidden. Activation keys off the leaf tenant_id, not partition_root_id, so
    # binding the root for the data fence must NOT also admit the member at a sibling
    # leaf host of the same trust. If this ever flips, a leaf member would reach a
    # sibling school's host.
    sib_same = resolve_activation(
        memberships=[m], host_tenant_id=school_b, host_ancestor_ids=(trust_a,)
    )
    assert isinstance(sib_same, HostForbidden), (
        "sibling-school host under the SAME trust must be HostForbidden (activation "
        "must not widen to the partition root)"
    )

    # Even at the ROOT (Trust A) host, this LEAF membership does NOT match (tenant_id
    # is the School, not the Trust) → forbidden, confirming we did not widen activation.
    at_root = resolve_activation(memberships=[m], host_tenant_id=trust_a, host_ancestor_ids=())
    assert isinstance(at_root, HostForbidden), "leaf membership must not activate at the root host"
