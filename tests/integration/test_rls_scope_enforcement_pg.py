"""Adversarial real-PostgreSQL proof of the intra-tenant scope policies (Phase C).

This is the **security proof** of Phase C. Phase B proved the *tenant fence*
(cross-tenant isolation) at the engine level; this module proves that *within a
single tenant* the database itself — via the per-verb scope policies generated
from ``entity.access.scopes`` by ``build_rls_scope_policy_ddl`` — enforces
per-user row visibility. It mirrors ``test_rls_enforcement_pg.py``'s harness:
a disposable scratch DB, the three-role model with uniquely-suffixed names, an
app connection as the non-superuser / non-BYPASSRLS ``dazzle_app`` role (the
only configuration under which RLS enforces), and a ``finally`` that drops the
scratch DB **and** the roles even on failure.

The scoped fixture entity is ``Project`` (``fixtures/tenant_rls``), which carries
an ``owner ref Member required`` column and per-verb scope rules::

    read:   owner = current_user
    list:   owner = current_user or visibility = public
    update: owner = current_user
    (no create scope, no delete scope)

``current_user`` compiles to ``current_user.entity_id``, so the scope policies
read ``current_setting('dazzle.user_entity_id', true)::uuid`` — we set that GUC
(via ``USER_GUC_PREFIX`` so the test cannot drift from the policy body) alongside
``dazzle.tenant_id`` on the app connection.

Invariants asserted (all positive-controlled — every "invisible" claim is paired
with a "visible when correctly scoped" control so a broken connection can't
masquerade as enforcement):

1. **Intra-tenant scope (SELECT):** under tenant T + user X, X sees its own rows;
   user Y's *private* (owner-gated) row in the SAME tenant is invisible.
2. **read/list union:** the SELECT policy is the OR of read + list, so X also
   sees Y's *public* row (the ``visibility = public`` list disjunct), and the
   ``scope_select`` policy definition in ``pg_policies`` contains both disjuncts.
3. **Verb coverage:** ``Project`` has no ``scope_insert``/``scope_delete`` policy
   → INSERT and DELETE are denied even with a correct tenant + user; UPDATE
   (which IS scoped) targets only the user's own rows (Y's rows → 0 rows hit).
4. **Cross-tenant still blocked:** the restrictive ``tenant_fence`` ANDs over the
   scope policy — an owner-matching row in a DIFFERENT tenant is invisible.
5. **Fail-closed:** with ``dazzle.user_entity_id`` unset, the owner-gated rows
   are invisible (``owner = NULL`` → false). Public rows remain visible by
   design (the ``visibility = public`` disjunct is not owner-gated).

Marked ``e2e`` + ``postgres``: skipped without ``TEST_DATABASE_URL`` /
``DATABASE_URL``; CI's ``postgres-tests`` job runs it against a real PostgreSQL.

**If any assertion here fails, the intra-tenant scope fence is wrong — that is a
real per-user authorization leak. Do not weaken the assertion.**
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

from dazzle.http.runtime.rls_schema import USER_GUC_PREFIX

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls")
_APP_PW = "rls_test_app_pw"  # fixture-only test password, never a real secret

# The scope policies read current_user as current_user.entity_id, so the GUC the
# test sets must be dazzle.user_entity_id. Derive the name from the single source
# of truth (USER_GUC_PREFIX) so it cannot drift from the policy body.
_TENANT_GUC = "dazzle.tenant_id"
_USER_GUC = f"{USER_GUC_PREFIX}entity_id"  # -> "dazzle.user_entity_id"


def _new_id() -> str:
    return str(uuid.uuid4())


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


def _build_fixture() -> tuple[sa.MetaData, str, list[str], object, object]:
    """Load the scoped fixture; return metadata + the pieces the DDL needs.

    Returns ``(metadata, partition_key, sorted_scoped_names, project_entity,
    scope_policy_inputs)`` where ``scope_policy_inputs`` is
    ``(fk_graph, entity_type_resolver)`` ready for ``build_rls_scope_policy_ddl``.
    """
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.core.ir.governance import TenancyMode
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.predicate_compiler import build_entity_type_resolver
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    appspec = load_project_appspec(_PROJECT_ROOT)
    assert appspec.tenancy is not None, "fixture must declare a tenancy block"
    assert appspec.tenancy.isolation.mode == TenancyMode.SHARED_SCHEMA, (
        "fixture must be shared_schema for RLS to apply"
    )
    pk = appspec.tenancy.isolation.partition_key

    entities = appspec.domain.entities
    specs = convert_entities(entities)
    scoped = sorted(scoped_entity_names(entities, pk))
    md = build_metadata(specs, partition_key=pk, tenant_scoped=scoped)

    project = next(e for e in entities if e.name == "Project")
    assert getattr(project.access, "scopes", None), "Project must declare scope rules"

    fk_graph = FKGraph.from_entities(specs)
    resolver = build_entity_type_resolver(specs)
    return md, pk, scoped, project, (fk_graph, resolver)


@dataclass
class _ScopeHarness:
    scratch: str
    pk: str
    metadata: sa.MetaData
    admin_engine: sa.Engine
    app_role: str
    # One tenant T with two users (X, Y) and their rows + a second tenant T2.
    tenant: str
    tenant_other: str
    user_x: str
    user_y: str
    user_z: str  # a member in T2 (owns the T2 project)
    proj_x_private: str
    proj_x_public: str
    proj_y_private: str
    proj_y_public: str
    proj_other_tenant: str  # in T2, owned by user_z

    def _conn_url(self, role: str, password: str) -> str:
        base = _admin_url()
        head, _, _hostpart = base.partition("://")
        hostpart = _hostpart.split("@")[-1]
        host_only = hostpart.rpartition("/")[0]
        return f"{head}://{role}:{password}@{host_only}/{self.scratch}"

    def app_conn(self) -> psycopg.Connection:
        return psycopg.connect(self._conn_url(self.app_role, _APP_PW))


@pytest.fixture
def harness() -> Iterator[_ScopeHarness]:
    """Stand up a scratch DB with the scope policies applied; drop it after."""
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")

    from dazzle.http.runtime.rls_schema import build_rls_policy_ddl, build_rls_scope_policy_ddl

    suffix = uuid.uuid4().hex[:8]
    scratch = f"dazzle_rls_scope_{suffix}"
    admin_url = _admin_url()
    owner_role = f"dazzle_owner_{suffix}"
    app_role = f"dazzle_app_{suffix}"

    base, _, _old_db = admin_url.rpartition("/")
    scratch_url = f"{base}/{scratch}"
    admin_engine: sa.Engine | None = None
    try:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived db name

        admin_engine = sa.create_engine(
            scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
        )

        md, pk, scoped, project, (fk_graph, resolver) = _build_fixture()
        md.create_all(admin_engine)

        with psycopg.connect(scratch_url, autocommit=True) as admin:
            admin.execute(  # nosemgrep — uuid-derived role name
                f'CREATE ROLE "{owner_role}" NOLOGIN'
            )
            admin.execute(  # nosemgrep — uuid-derived role; password is a fixture constant
                f"CREATE ROLE \"{app_role}\" LOGIN PASSWORD '{_APP_PW}'"
            )
            admin.execute(  # nosemgrep — uuid-derived roles, not user input
                f'GRANT USAGE ON SCHEMA public TO "{app_role}", "{owner_role}"'
            )
            admin.execute(  # nosemgrep — uuid-derived roles
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                f'TO "{app_role}", "{owner_role}"'
            )

            # Apply the framework DDL under test verbatim:
            #  - Project (scoped) → per-verb scope policies (no baseline).
            #  - other scoped entities → Phase B fence + permissive baseline.
            for stmt in build_rls_scope_policy_ddl(project, fk_graph, resolver, partition_key=pk):
                admin.execute(stmt)
            tenant_flat = [n for n in scoped if n != "Project"]
            for stmt in build_rls_policy_ddl(tenant_flat, partition_key=pk):
                admin.execute(stmt)

        # Seed via the admin/owner engine (bypasses RLS for setup, not assertion).
        tenant = _new_id()
        tenant_other = _new_id()
        user_x = _new_id()
        user_y = _new_id()
        user_z = _new_id()
        proj_x_private = _new_id()
        proj_x_public = _new_id()
        proj_y_private = _new_id()
        proj_y_public = _new_id()
        proj_other_tenant = _new_id()

        with admin_engine.begin() as conn:
            ws = md.tables["Workspace"]
            member = md.tables["Member"]
            proj = md.tables["Project"]
            conn.execute(
                ws.insert(),
                [
                    {"id": tenant, "name": "Tenant T"},
                    {"id": tenant_other, "name": "Tenant T2"},
                ],
            )
            conn.execute(
                member.insert(),
                [
                    {"tenant_id": tenant, "id": user_x, "email": "x@example.test"},
                    {"tenant_id": tenant, "id": user_y, "email": "y@example.test"},
                    # A distinct member in T2 (Member.id is globally unique) who
                    # owns the T2 project. The cross-tenant proof scopes a session
                    # to T2 while carrying user_x's id: the scope predicate
                    # (owner = user_x) is SATISFIED by X's rows that live in T,
                    # yet the T2 fence excludes them — fence-over-scope.
                    {"tenant_id": tenant_other, "id": user_z, "email": "z@t2.test"},
                ],
            )
            conn.execute(
                proj.insert(),
                [
                    {
                        "tenant_id": tenant,
                        "id": proj_x_private,
                        "name": "X private",
                        "owner": user_x,
                        "visibility": "private",
                    },
                    {
                        "tenant_id": tenant,
                        "id": proj_x_public,
                        "name": "X public",
                        "owner": user_x,
                        "visibility": "public",
                    },
                    {
                        "tenant_id": tenant,
                        "id": proj_y_private,
                        "name": "Y private",
                        "owner": user_y,
                        "visibility": "private",
                    },
                    {
                        "tenant_id": tenant,
                        "id": proj_y_public,
                        "name": "Y public",
                        "owner": user_y,
                        "visibility": "public",
                    },
                    {
                        "tenant_id": tenant_other,
                        "id": proj_other_tenant,
                        "name": "Z project in T2",
                        "owner": user_z,
                        "visibility": "private",
                    },
                ],
            )

        yield _ScopeHarness(
            scratch=scratch,
            pk=pk,
            metadata=md,
            admin_engine=admin_engine,
            app_role=app_role,
            tenant=tenant,
            tenant_other=tenant_other,
            user_x=user_x,
            user_y=user_y,
            user_z=user_z,
            proj_x_private=proj_x_private,
            proj_x_public=proj_x_public,
            proj_y_private=proj_y_private,
            proj_y_public=proj_y_public,
            proj_other_tenant=proj_other_tenant,
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
            for role in (app_role, owner_role):
                admin.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep — uuid-derived role name


def _assert_app_is_non_superuser(conn: psycopg.Connection) -> None:
    """The app connection MUST be non-superuser AND non-BYPASSRLS, else RLS is
    bypassed and the whole proof is vacuous."""
    row = conn.execute(
        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert row is not None
    current_user, rolsuper, rolbypassrls = row
    assert rolsuper is False, (
        f"app connection is a superuser ({current_user}); RLS would be bypassed"
    )
    assert rolbypassrls is False, (
        f"app connection ({current_user}) holds BYPASSRLS; the scope policy would not apply"
    )


def _set_context(conn: psycopg.Connection, tenant: str, user: str | None) -> None:
    """Set the per-transaction RLS GUCs the scope policies read.

    Always sets ``dazzle.tenant_id``; sets ``dazzle.user_entity_id`` only when
    ``user`` is provided (the fail-closed test leaves it unset → NULL).
    """
    # Both the GUC name and value are bound parameters — set_config takes the
    # parameter name as its first argument, so no SQL string interpolation.
    conn.execute("SELECT set_config(%s, %s, true)", (_TENANT_GUC, tenant))
    if user is not None:
        conn.execute("SELECT set_config(%s, %s, true)", (_USER_GUC, user))


def _names(conn: psycopg.Connection) -> list[str]:
    return sorted(r[0] for r in conn.execute('SELECT name FROM "Project"').fetchall())


def test_intra_tenant_scope_select_enforced(harness: _ScopeHarness) -> None:
    """Invariant 1+2: tenant T + user X sees its own rows and any public row
    (read/list union), but NOT user Y's private (owner-gated) row."""
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        with conn.transaction():
            _set_context(conn, harness.tenant, harness.user_x)
            visible = _names(conn)
    # SELECT policy = read OR list = (owner=X) OR (owner=X OR visibility=public)
    #              = owner=X OR visibility=public.
    # → X's own rows (X private, X public) + every public row (Y public).
    # → Y's PRIVATE row is invisible: the intra-tenant per-user fence.
    assert visible == ["X private", "X public", "Y public"], (
        f"intra-tenant scope leak/loss: expected X's rows + public rows, got {visible!r}"
    )
    assert "Y private" not in visible, (
        "INTRA-TENANT LEAK: user X can see user Y's private row in the same tenant"
    )


def test_read_list_union_in_policy_definition(harness: _ScopeHarness) -> None:
    """Invariant 2: the scope_select policy body is the OR of the read and list
    predicates — it must reference both the owner GUC and the public literal."""
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        row = conn.execute(
            "SELECT qual FROM pg_policies WHERE tablename = 'Project' AND policyname = %s",
            ("scope_select",),
        ).fetchone()
    assert row is not None, "scope_select policy is missing on Project"
    qual = row[0]
    assert _USER_GUC in qual, f"scope_select must read the owner GUC; body was {qual!r}"
    assert "public" in qual, (
        f"scope_select must include the list `visibility = public` disjunct (read/list "
        f"union); body was {qual!r}"
    )


def test_verb_coverage_insert_and_delete_denied(harness: _ScopeHarness) -> None:
    """Invariant 3: Project declares no create/delete scope rule, so no
    scope_insert/scope_delete policy is emitted → those verbs are DENIED even
    with a correct tenant + user (companion §1.4). UPDATE IS scoped, so it works
    for the user's OWN row and silently affects 0 of another user's rows."""
    # No scope_insert policy → INSERT denied (new row violates RLS).
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        with pytest.raises(pg_errors.InsufficientPrivilege, match="row-level security policy"):
            with conn.transaction():
                _set_context(conn, harness.tenant, harness.user_x)
                conn.execute(
                    'INSERT INTO "Project" (tenant_id, id, name, owner, visibility) '
                    "VALUES (%s, %s, %s, %s, %s)",
                    (harness.tenant, _new_id(), "new", harness.user_x, "private"),
                )

    # No scope_delete policy → DELETE targets zero rows (USING is empty/deny).
    with harness.app_conn() as conn:
        with conn.transaction():
            _set_context(conn, harness.tenant, harness.user_x)
            cur = conn.execute('DELETE FROM "Project" WHERE id = %s', (harness.proj_x_private,))
            deleted = cur.rowcount
    assert deleted == 0, (
        f"DELETE is unscoped on Project but removed {deleted} row(s) — verb coverage gap"
    )

    # UPDATE IS scoped (owner = current_user): X may update its own row, but an
    # UPDATE aimed at Y's row hits 0 rows (USING filters it out — no error).
    with harness.app_conn() as conn:
        with conn.transaction():
            _set_context(conn, harness.tenant, harness.user_x)
            own = conn.execute(
                'UPDATE "Project" SET name = %s WHERE id = %s',
                ("X private renamed", harness.proj_x_private),
            ).rowcount
            other = conn.execute(
                'UPDATE "Project" SET name = %s WHERE id = %s',
                ("hijack Y", harness.proj_y_private),
            ).rowcount
    assert own == 1, f"scope_update should let X update its own row, hit {own}"
    assert other == 0, (
        f"INTRA-TENANT LEAK: scope_update let X update user Y's row ({other} row(s) hit)"
    )


def test_cross_tenant_still_blocked(harness: _ScopeHarness) -> None:
    """Invariant 4: the restrictive tenant_fence ANDs over the scope policy —
    fence-over-scope. Carry user_x's id but scope the session to tenant T2: the
    scope predicate (owner = user_x) IS satisfied by X's rows, which live in
    tenant T — yet the T2 fence excludes them, so X sees none of its own T rows
    from a T2 session. Positive control: those same rows ARE visible from a T
    session (so it's the fence, not a blanket grant failure)."""
    # Positive control: X-in-T sees X's owned rows.
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        with conn.transaction():
            _set_context(conn, harness.tenant, harness.user_x)
            in_t = _names(conn)
    assert "X private" in in_t and "X public" in in_t, (
        f"positive control failed: X-in-T should see its own rows, got {in_t!r}"
    )

    # X's id, but scoped to T2: owner = user_x still matches X's T rows, yet the
    # T2 fence blocks them. X sees ONLY the T2 project — none of its T rows.
    with harness.app_conn() as conn:
        with conn.transaction():
            _set_context(conn, harness.tenant_other, harness.user_x)
            in_t2 = _names(conn)
    assert "X private" not in in_t2 and "X public" not in in_t2, (
        "CROSS-TENANT LEAK: X's tenant-T rows are visible to an X-in-T2 session "
        "(the tenant_fence is NOT ANDing over the scope policy)"
    )
    # The T2 project is public-private owned by user_z, so X (owner=user_x) does
    # not see it via owner; visibility=private means the public disjunct doesn't
    # apply either → X sees nothing in T2.
    assert in_t2 == [], f"X-in-T2 should see no rows (none owned by X, none public), got {in_t2!r}"


def test_fail_closed_when_user_unset(harness: _ScopeHarness) -> None:
    """Invariant 5: with dazzle.user_entity_id UNSET (tenant set), the owner-gated
    rows fall out (owner = current_setting(...) → owner = NULL → false). Public
    rows remain visible by design (the visibility = public list disjunct is not
    owner-gated) — so we assert the OWNER-gated private rows are gone, with a
    positive control that they ARE visible once the user GUC is set."""
    # Positive control: with the user set, X's private row is visible.
    with harness.app_conn() as conn:
        _assert_app_is_non_superuser(conn)
        with conn.transaction():
            _set_context(conn, harness.tenant, harness.user_x)
            with_user = _names(conn)
    assert "X private" in with_user, "positive control failed: X should see its private row"

    # User unset → owner clause is NULL/false. Private (owner-only) rows vanish;
    # only public rows survive (the non-owner-gated list disjunct).
    with harness.app_conn() as conn:
        with conn.transaction():
            _set_context(conn, harness.tenant, user=None)
            without_user = _names(conn)
    assert "X private" not in without_user, (
        "FAIL-OPEN: owner-gated private row visible with dazzle.user_entity_id unset"
    )
    assert "Y private" not in without_user, (
        "FAIL-OPEN: owner-gated private row visible with dazzle.user_entity_id unset"
    )
    # By-design: public rows are still visible (not an owner leak).
    assert set(without_user) == {"X public", "Y public"}, (
        f"fail-closed shape wrong: expected only public rows with no user GUC, got {without_user!r}"
    )
