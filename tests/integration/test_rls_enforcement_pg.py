"""Adversarial real-PostgreSQL proof of the tenant fence (RLS tenancy Phase B).

This is the **security proof** of Phase B. Tasks 1+2 generate the RLS DDL
(``build_rls_policy_ddl`` / ``build_rls_role_ddl``) and wire the per-transaction
``set_config('dazzle.tenant_id', ...)`` context. This module proves the fence
actually blocks cross-tenant access **at the engine level** by connecting as a
non-superuser, non-``BYPASSRLS`` role (``dazzle_app``) — the only configuration
under which RLS enforces (superusers and ``BYPASSRLS`` roles always bypass).

Each test stands up its OWN disposable scratch database
(``dazzle_rls_enf_<uuid>``) on the target server, loads ``fixtures/tenant_rls``,
``create_all()``s it as the owner/superuser admin connection, creates the
three-role model, applies ``build_rls_policy_ddl(...)``, seeds rows for two
tenants via the admin connection (bypassing the fence to set up), and then runs
its assertions as ``dazzle_app``. The scratch DB **and** the roles are dropped in
a ``finally`` even on failure.

**Roles are cluster-global**, so each test run uses *uniquely-suffixed* role
names (``dazzle_app_<uuid8>`` etc.) to avoid colliding with a real cluster or a
concurrent run. The roles carry the SAME attributes the framework's
``build_rls_role_ddl`` emits (``dazzle_app``: LOGIN, **no** BYPASSRLS;
``dazzle_bypass``: LOGIN BYPASSRLS; ``dazzle_owner``: NOLOGIN) — the exact
*output shape* of ``build_rls_role_ddl`` is pinned separately by Task 1's unit
tests (``tests/unit/test_rls_schema.py``); here we need parametrised names that
are safe to drop, so the role SQL is hand-written with identical attributes.

The seven invariants asserted (companion §9, fence-relevant subset — intra-tenant
scope-policy invariants are Phase C):

1. Cross-tenant READ blocked (+ positive control: own rows visible).
2. Cross-tenant WRITE blocked by the fence ``WITH CHECK``.
3. Fail-closed on missing context (no GUC → 0 rows; writes rejected).
4. Empty context is a HARD error (``''::uuid`` → ``invalid input syntax``).
5. Restrictive-only is deny-all (drop the baseline → correctly-scoped session
   sees nothing — proves the baseline is load-bearing, companion §1.4).
6. Owner does NOT bypass under FORCE (non-superuser table owner, no context →
   denied; live-owner check, not a substitution).
7. Role attributes: ``dazzle_bypass`` has ``rolbypassrls=true`` and CAN see the
   other tenant's rows; ``dazzle_app`` has ``rolbypassrls=false``.

Marked ``e2e`` + ``postgres``: skipped locally without ``TEST_DATABASE_URL`` /
``DATABASE_URL``; CI's ``postgres-tests`` job runs it against a real PostgreSQL.

**If any assertion here fails, the fence is wrong — that is a real cross-tenant
leak. Do not weaken the assertion.**
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
import sqlalchemy as sa
from psycopg import errors as pg_errors

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls")
_APP_PW = "rls_test_app_pw"  # fixture-only test password, never a real secret
_BYPASS_PW = "rls_test_bypass_pw"


def _new_id() -> str:
    return str(uuid.uuid4())


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


def _build_fixture_metadata() -> tuple[sa.MetaData, str, list[str]]:
    """Load the fixture appspec, build its tenant-aware SA metadata.

    Returns ``(metadata, partition_key, sorted_scoped_entity_names)``.
    """
    from dazzle.back.converters.entity_converter import convert_entities
    from dazzle.back.runtime.sa_schema import build_metadata, scoped_entity_names
    from dazzle.core.appspec_loader import load_project_appspec

    appspec = load_project_appspec(_PROJECT_ROOT)
    assert appspec.tenancy is not None, "fixture must declare a tenancy block"
    from dazzle.core.ir.governance import TenancyMode

    assert appspec.tenancy.isolation.mode == TenancyMode.SHARED_SCHEMA, (
        "fixture must be shared_schema for the RLS fence to apply"
    )
    pk = appspec.tenancy.isolation.partition_key

    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    md = build_metadata(
        convert_entities(appspec.domain.entities),
        partition_key=pk,
        tenant_scoped=scoped,
    )
    return md, pk, scoped


@dataclass
class _RlsHarness:
    """A provisioned scratch DB with RLS applied and the three roles created."""

    scratch: str
    suffix: str
    pk: str
    scoped: list[str]
    metadata: sa.MetaData
    admin_engine: sa.Engine
    owner_role: str
    app_role: str
    bypass_role: str
    tenant_a: str
    tenant_b: str
    member_a: str
    member_b: str

    def _conn_url(self, role: str, password: str) -> str:
        """A psycopg connection URL for ``role`` against the scratch DB."""
        base = _admin_url()
        # Splice user:pass@ into the host segment, keep the scratch db path.
        head, _, _hostpart = base.partition("://")
        # Strip any existing credentials from the host segment.
        hostpart = _hostpart.split("@")[-1]
        host_only = hostpart.rpartition("/")[0]
        return f"{head}://{role}:{password}@{host_only}/{self.scratch}"

    def app_conn(self) -> psycopg.Connection:
        return psycopg.connect(self._conn_url(self.app_role, _APP_PW))

    def bypass_conn(self) -> psycopg.Connection:
        return psycopg.connect(self._conn_url(self.bypass_role, _BYPASS_PW))


@pytest.fixture
def harness() -> Iterator[_RlsHarness]:
    """Stand up a disposable scratch DB + RLS + roles; drop everything after.

    The scratch DB and all three uniquely-suffixed roles are dropped in the
    ``finally`` block even if a test raises, so nothing leaks into the cluster.
    """
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")

    from dazzle.back.runtime.rls_schema import build_rls_policy_ddl

    suffix = uuid.uuid4().hex[:8]
    scratch = f"dazzle_rls_enf_{suffix}"
    admin_url = _admin_url()
    owner_role = f"dazzle_owner_{suffix}"
    app_role = f"dazzle_app_{suffix}"
    bypass_role = f"dazzle_bypass_{suffix}"

    base, _, _old_db = admin_url.rpartition("/")
    scratch_url = f"{base}/{scratch}"
    admin_engine: sa.Engine | None = None
    try:
        # CREATE/DROP DATABASE cannot run inside a transaction block. Do it
        # inside the try so the finally always cleans up even if a later setup
        # step (metadata build, role create, RLS apply, seed) raises.
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived db name

        admin_engine = sa.create_engine(
            scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
        )

        md, pk, scoped = _build_fixture_metadata()
        # create_all as the superuser/owner admin connection.
        md.create_all(admin_engine)

        # Roles: same attributes as build_rls_role_ddl emits, but uniquely
        # suffixed so they are safe to drop. (build_rls_role_ddl's output shape
        # is pinned by tests/unit/test_rls_schema.py.) Grants run AFTER
        # create_all so the tables exist to be granted on.
        scratch_admin_url = scratch_url
        with psycopg.connect(scratch_admin_url, autocommit=True) as admin:
            admin.execute(  # nosemgrep — uuid-derived role name
                f'CREATE ROLE "{owner_role}" NOLOGIN'
            )
            admin.execute(  # nosemgrep — uuid-derived role; password is a fixture constant
                f"CREATE ROLE \"{app_role}\" LOGIN PASSWORD '{_APP_PW}'"
            )
            admin.execute(  # nosemgrep — uuid-derived role; BYPASSRLS by design
                f"CREATE ROLE \"{bypass_role}\" LOGIN PASSWORD '{_BYPASS_PW}' BYPASSRLS"
            )
            grant_usage = (
                f'GRANT USAGE ON SCHEMA public TO "{app_role}", "{bypass_role}", "{owner_role}"'
            )
            admin.execute(grant_usage)  # nosemgrep — uuid-derived roles, not user input
            admin.execute(  # nosemgrep — uuid-derived roles
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                f'TO "{app_role}", "{bypass_role}", "{owner_role}"'
            )

            # Apply the framework-generated RLS policy DDL (the artefact under
            # test) verbatim.
            for stmt in build_rls_policy_ddl(scoped, partition_key=pk):
                admin.execute(stmt)

        # Seed two tenants + a row each via the admin (owner/superuser) engine,
        # which bypasses the fence — this is the setup, not an assertion.
        tenant_a = _new_id()
        tenant_b = _new_id()
        # Project now carries an `owner ref Member required` column (Phase C
        # added the intra-tenant scoped shape to the shared fixture), so seed a
        # Member per tenant to own each project. The fence proof here is
        # unchanged — it only ever reads/writes by tenant_id.
        member_a = _new_id()
        member_b = _new_id()
        with admin_engine.begin() as conn:
            ws = md.tables["Workspace"]
            member = md.tables["Member"]
            project = md.tables["Project"]
            conn.execute(
                ws.insert(),
                [{"id": tenant_a, "name": "Tenant A"}, {"id": tenant_b, "name": "Tenant B"}],
            )
            conn.execute(
                member.insert(),
                [
                    {"tenant_id": tenant_a, "id": member_a, "email": "a@example.test"},
                    {"tenant_id": tenant_b, "id": member_b, "email": "b@example.test"},
                ],
            )
            conn.execute(
                project.insert(),
                [
                    {
                        "tenant_id": tenant_a,
                        "id": _new_id(),
                        "name": "A's project",
                        "owner": member_a,
                    },
                    {
                        "tenant_id": tenant_b,
                        "id": _new_id(),
                        "name": "B's project",
                        "owner": member_b,
                    },
                ],
            )

        yield _RlsHarness(
            scratch=scratch,
            suffix=suffix,
            pk=pk,
            scoped=scoped,
            metadata=md,
            admin_engine=admin_engine,
            owner_role=owner_role,
            app_role=app_role,
            bypass_role=bypass_role,
            tenant_a=tenant_a,
            tenant_b=tenant_b,
            member_a=member_a,
            member_b=member_b,
        )
    finally:
        if admin_engine is not None:
            admin_engine.dispose()
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep — uuid-derived
            # Roles are cluster-global; drop them too. Any objects they own in
            # the (now-dropped) scratch DB go with the DB, so a plain DROP ROLE
            # is sufficient here.
            for role in (app_role, bypass_role, owner_role):
                admin.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep — uuid-derived role name


def _assert_app_is_non_superuser(conn: psycopg.Connection) -> None:
    """Sanity guard: the app connection MUST be a non-superuser, non-BYPASSRLS
    role — otherwise RLS is bypassed and every read assertion falsely "passes"
    while the block assertions falsely fail. This guard makes a misconfigured
    harness loud instead of silently invalidating the proof."""
    row = conn.execute(
        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert row is not None
    current_user, rolsuper, rolbypassrls = row
    assert rolsuper is False, (
        f"app connection is a superuser ({current_user}); RLS would be bypassed "
        "and this proof would be vacuous"
    )
    assert rolbypassrls is False, (
        f"app connection ({current_user}) holds BYPASSRLS; the fence would not apply"
    )


def test_cross_tenant_read_blocked(harness: _RlsHarness) -> None:
    """Invariant 1: as dazzle_app with context = tenant A, tenant B's rows are
    invisible; tenant A's own rows are visible (positive control)."""
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        with conn.transaction():
            conn.execute("SELECT set_config('dazzle.tenant_id', %s, true)", (harness.tenant_a,))
            names = [r[0] for r in conn.execute('SELECT name FROM "Project"').fetchall()]
    # Exactly tenant A's project — tenant B's is fenced out.
    assert names == ["A's project"], (
        f"cross-tenant read leak: expected only A's rows, got {names!r}"
    )


def test_cross_tenant_write_blocked(harness: _RlsHarness) -> None:
    """Invariant 2: under tenant A's context, an INSERT carrying tenant B's
    tenant_id is rejected by the fence WITH CHECK (surfaced by Postgres as
    InsufficientPrivilege / "new row violates row-level security policy")."""
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        # A failed RLS WITH CHECK raises InsufficientPrivilege (SQLSTATE 42501,
        # "new row violates row-level security policy"), NOT a CheckViolation —
        # the latter is for ordinary CHECK constraints.
        with pytest.raises(pg_errors.InsufficientPrivilege, match="row-level security policy"):
            with conn.transaction():
                conn.execute("SELECT set_config('dazzle.tenant_id', %s, true)", (harness.tenant_a,))
                # tenant_id = B while context = A → WITH CHECK fails.
                conn.execute(
                    'INSERT INTO "Project" (tenant_id, id, name, owner) VALUES (%s, %s, %s, %s)',
                    (harness.tenant_b, _new_id(), "smuggled into B", harness.member_b),
                )

    # Positive control: an INSERT with the matching tenant_id succeeds.
    with harness.app_conn() as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('dazzle.tenant_id', %s, true)", (harness.tenant_a,))
            conn.execute(
                'INSERT INTO "Project" (tenant_id, id, name, owner) VALUES (%s, %s, %s, %s)',
                (harness.tenant_a, _new_id(), "legit A project", harness.member_a),
            )


def test_fail_closed_on_missing_context(harness: _RlsHarness) -> None:
    """Invariant 3: with no dazzle.tenant_id set, reads return zero rows and
    writes are rejected (current_setting(..., true) → NULL → fail-closed)."""
    # Read: zero rows.
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        with conn.transaction():
            count = conn.execute('SELECT count(*) FROM "Project"').fetchone()[0]
    assert count == 0, f"fail-open read leak: saw {count} rows with no context set"

    # Write: rejected by the fence WITH CHECK (tenant_id = NULL is not true).
    # An RLS WITH CHECK failure surfaces as InsufficientPrivilege (42501).
    with harness.app_conn() as conn:
        with pytest.raises(pg_errors.InsufficientPrivilege, match="row-level security policy"):
            with conn.transaction():
                conn.execute(
                    'INSERT INTO "Project" (tenant_id, id, name, owner) VALUES (%s, %s, %s, %s)',
                    (harness.tenant_a, _new_id(), "no-context insert", harness.member_a),
                )


def test_empty_context_denies_not_errors(harness: _RlsHarness) -> None:
    """Invariant 4 (#1400): an empty-string GUC must fail-closed by DENYING
    (zero rows on read, RLS rejection on write), NOT by raising
    'invalid input syntax for type uuid' on a bare ``''::uuid``.

    Before #1400 the fence read ``current_setting(..)::uuid`` directly, so the
    empty-string GUC state (reachable on a pooled connection whose placeholder
    reverted to '') surfaced as a 500 — and a per-tenant DoS vector. The fence
    now wraps the read in ``NULLIF(.., '')``, collapsing '' to NULL so it denies
    identically to the unset state. Reads return no rows; writes are blocked by
    the RESTRICTIVE WITH CHECK."""
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        # Read: empty-string context → NULL fence → no rows, no error.
        with conn.transaction():
            conn.execute("SELECT set_config('dazzle.tenant_id', '', true)")
            count = conn.execute('SELECT count(*) FROM "Project"').fetchone()[0]
        assert count == 0, "empty-string GUC must deny (0 rows), not leak"
        # Write: empty-string context → WITH CHECK fails → RLS rejection,
        # never an InvalidTextRepresentation cast error.
        with pytest.raises(pg_errors.InsufficientPrivilege, match="row-level security policy"):
            with conn.transaction():
                conn.execute("SELECT set_config('dazzle.tenant_id', '', true)")
                conn.execute(
                    'INSERT INTO "Project" (tenant_id, id, name, owner) VALUES (%s, %s, %s, %s)',
                    (harness.tenant_a, _new_id(), "empty-context insert", harness.member_a),
                )


def test_restrictive_only_is_deny_all(harness: _RlsHarness) -> None:
    """Invariant 5: dropping the permissive tenant_baseline leaves only the
    RESTRICTIVE fence; a correctly-scoped session then sees nothing — proving
    the baseline is load-bearing (companion §1.4: restrictive policies only
    subtract; a fenced table with no permissive policy is deny-all)."""
    # Drop the baseline on Project (as admin/owner — DDL is not RLS-governed).
    with psycopg.connect(
        _admin_url().rpartition("/")[0] + f"/{harness.scratch}", autocommit=True
    ) as admin:
        admin.execute('DROP POLICY tenant_baseline ON "Project"')

    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        with conn.transaction():
            conn.execute("SELECT set_config('dazzle.tenant_id', %s, true)", (harness.tenant_a,))
            # Correctly scoped to A, but with no permissive policy left, the
            # effective set is empty.
            count = conn.execute('SELECT count(*) FROM "Project"').fetchone()[0]
    assert count == 0, (
        "restrictive-only table is NOT deny-all — the permissive baseline is "
        f"not load-bearing as required (saw {count} rows)"
    )


def test_owner_does_not_bypass_under_force(harness: _RlsHarness) -> None:
    """Invariant 6: FORCE ROW LEVEL SECURITY subjects even the table OWNER to the
    policies. A non-superuser owner with no context is denied — the live-owner
    check, not a relforcerowsecurity substitution.

    We reassign ownership of a fenced table to the non-superuser dazzle_owner
    role, give it LOGIN + a password for this test, connect as it, and assert
    it sees zero rows with no context (and rows only when correctly scoped)."""
    owner_pw = "rls_test_owner_pw"
    scratch_admin_url = _admin_url().rpartition("/")[0] + f"/{harness.scratch}"
    with psycopg.connect(scratch_admin_url, autocommit=True) as admin:
        # Make dazzle_owner the actual owner of Project, and loginable for the
        # duration of this test.
        alter_owner = f'ALTER TABLE "Project" OWNER TO "{harness.owner_role}"'
        admin.execute(alter_owner)  # nosemgrep — uuid-derived role, not user input
        admin.execute(  # nosemgrep — uuid-derived role; fixture password
            f"ALTER ROLE \"{harness.owner_role}\" LOGIN PASSWORD '{owner_pw}'"
        )
        # Confirm FORCE is actually on the table (belt-and-braces; the live
        # connection below is the real proof).
        forced = admin.execute(
            "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'Project'"
        ).fetchone()[0]
        assert forced is True, "Project must have FORCE ROW LEVEL SECURITY"

    head = _admin_url().partition("://")[0]
    hostpart = _admin_url().partition("://")[2].split("@")[-1]
    host_only = hostpart.rpartition("/")[0]
    owner_url = f"{head}://{harness.owner_role}:{owner_pw}@{host_only}/{harness.scratch}"

    with psycopg.connect(owner_url) as conn:
        # The owner is a non-superuser (sanity-guard reuse).
        row = conn.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert row == (False, False), f"owner role unexpectedly has elevated attributes: {row}"

        # No context → owner sees nothing despite owning the table (FORCE).
        with conn.transaction():
            count = conn.execute('SELECT count(*) FROM "Project"').fetchone()[0]
        assert count == 0, f"owner bypassed RLS under FORCE — saw {count} rows with no context"

        # Correctly scoped → owner sees exactly its tenant's row (proves it is
        # the fence filtering, not a blanket grant failure).
        with conn.transaction():
            conn.execute("SELECT set_config('dazzle.tenant_id', %s, true)", (harness.tenant_a,))
            scoped_count = conn.execute('SELECT count(*) FROM "Project"').fetchone()[0]
        assert scoped_count == 1, (
            f"owner with context = A should see exactly A's row, saw {scoped_count}"
        )


def test_role_attributes(harness: _RlsHarness) -> None:
    """Invariant 7: dazzle_bypass has rolbypassrls=true and (with no context, or
    a foreign context) CAN see the other tenant's rows; dazzle_app has
    rolbypassrls=false."""
    # Attribute assertions (read from pg_roles).
    with harness.admin_engine.connect() as conn:
        rows = {
            r[0]: r[1]
            for r in conn.execute(
                sa.text(
                    "SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN (:app, :bypass)"
                ),
                {"app": harness.app_role, "bypass": harness.bypass_role},
            ).fetchall()
        }
    assert rows[harness.app_role] is False, "dazzle_app must NOT hold BYPASSRLS"
    assert rows[harness.bypass_role] is True, "dazzle_bypass must hold BYPASSRLS"

    # Behavioural: dazzle_bypass, with NO context, sees BOTH tenants' rows
    # (bypass actually bypasses the fence). It must be a non-superuser to make
    # this a real bypass-vs-fence test rather than a superuser short-circuit.
    with harness.bypass_conn() as conn:
        row = conn.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()
        assert row[0] is False, "bypass role must be a non-superuser for a real test"
        with conn.transaction():
            count = conn.execute('SELECT count(*) FROM "Project"').fetchone()[0]
    assert count == 2, f"dazzle_bypass should see both tenants' rows with no context, saw {count}"
