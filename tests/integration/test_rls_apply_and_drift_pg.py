"""Real-PostgreSQL proof of the Phase D production apply + drift chain.

This is the functional proof that ``apply_rls_policies`` (Task 2) and
``detect_rls_drift`` (Task 4) actually work end-to-end against a live database —
the surfaces Tasks 1-3 had unit coverage for but no real-PG apply test.

The flow (one scratch DB per test, dropped in ``finally``):

1. **apply + idempotency** — load ``fixtures/tenant_rls``, ``create_all`` as the
   owner (sync SQLAlchemy, mirroring the Phase B/C harness), then run the async
   ``apply_rls_policies`` against the same scratch DB via psycopg3. Assert
   ``pg_policies`` / ``pg_class`` show the fence + baseline + scope policies and
   RLS enabled+forced on the tenant-scoped tables. Re-apply → no error, identical
   policy set (the DDL is DROP-then-CREATE).
2. **no drift after a clean apply** — ``detect_rls_drift`` returns ``[]``.
3. **drift detected** — drop ``tenant_fence`` on ``Project`` → ``detect_rls_drift``
   reports exactly that table's missing fence and nothing for the clean tables.

``apply_rls_policies`` / ``detect_rls_drift`` are async (psycopg3 since #1341);
the existing Phase B/C tests use sync psycopg. Here we use sync SQLAlchemy for
``create_all`` setup (as those tests do) and drive the async funcs via
``asyncio.run`` over the REAL ``dazzle.db.connection.get_connection`` factory
against the same scratch DB — exercising the exact conn the ``dazzle db`` CLI
uses in production.

Marked ``e2e`` + ``postgres``: skipped without ``TEST_DATABASE_URL`` /
``DATABASE_URL``; CI's ``postgres-tests`` job runs it against real PostgreSQL.

**If apply or drift behaves wrong here, the whole Phase D prod-apply chain is
wrong — do not weaken the assertions.**
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


def _load_appspec_and_entities() -> tuple[Any, list[Any], str, list[str]]:
    """Load the fixture appspec + converted back-spec entities.

    Returns ``(appspec, entities, partition_key, sorted_scoped_names)``.
    """
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.ir.governance import TenancyMode
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import scoped_entity_names

    appspec = load_project_appspec(_PROJECT_ROOT)
    assert appspec.tenancy is not None, "fixture must declare a tenancy block"
    assert appspec.tenancy.isolation.mode == TenancyMode.SHARED_SCHEMA, (
        "fixture must be shared_schema for RLS to apply"
    )
    pk = appspec.tenancy.isolation.partition_key
    entities = convert_entities(appspec.domain.entities)
    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    return appspec, entities, pk, scoped


def _build_metadata(appspec: Any, entities: list[Any], pk: str, scoped: list[str]) -> sa.MetaData:
    from dazzle.http.runtime.sa_schema import build_metadata

    return build_metadata(entities, partition_key=pk, tenant_scoped=scoped)


@dataclass
class _ApplyHarness:
    """A scratch DB with the fixture schema created (RLS NOT yet applied)."""

    scratch: str
    scratch_url: str
    appspec: Any
    entities: list[Any]
    pk: str
    scoped: list[str]

    def conn_url(self) -> str:
        # get_connection → psycopg.AsyncConnection.connect wants a plain
        # postgresql:// URL (no +psycopg SQLAlchemy-dialect suffix).
        return self.scratch_url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def harness() -> Iterator[_ApplyHarness]:
    """Stand up a scratch DB, create_all the fixture schema as owner; drop after."""
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    scratch = f"dazzle_rls_apply_{suffix}"
    admin_url = _admin_url()
    base, _, _old_db = admin_url.rpartition("/")
    scratch_url = f"{base}/{scratch}"

    admin_engine: sa.Engine | None = None
    try:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived db name

        appspec, entities, pk, scoped = _load_appspec_and_entities()
        md = _build_metadata(appspec, entities, pk, scoped)

        admin_engine = sa.create_engine(
            scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
        )
        # create_all as the owner (the admin connection owns the tables — the
        # role privilege RLS DDL requires).
        md.create_all(admin_engine)

        yield _ApplyHarness(
            scratch=scratch,
            scratch_url=scratch_url,
            appspec=appspec,
            entities=entities,
            pk=pk,
            scoped=scoped,
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


async def _with_conn(url: str, coro_factory: Any) -> Any:
    """Open a psycopg3 async conn via the production db-CLI factory, run, close.

    Uses the real ``dazzle.db.connection.get_connection`` so the test drives the
    exact connection (autocommit + dict rows) the ``dazzle db`` CLI uses.
    """
    from dazzle.db.connection import get_connection

    conn = await get_connection(explicit_url=url)
    try:
        return await coro_factory(conn)
    finally:
        await conn.close()


def _live_policy_names(scratch_url: str, table: str) -> set[str]:
    """Policy names on ``table`` (via a sync psycopg read — assertion helper)."""
    sync_url = scratch_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(sync_url) as conn:
        rows = conn.execute(
            "SELECT policyname FROM pg_policies WHERE schemaname='public' AND tablename=%s",
            (table,),
        ).fetchall()
    return {r[0] for r in rows}


def _rls_flags(scratch_url: str, table: str) -> tuple[bool, bool]:
    """``(relrowsecurity, relforcerowsecurity)`` for a table."""
    sync_url = scratch_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(sync_url) as conn:
        row = conn.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname=%s AND relnamespace='public'::regnamespace",
            (table,),
        ).fetchone()
    assert row is not None, f"table {table} missing"
    return (bool(row[0]), bool(row[1]))


def test_apply_creates_expected_policies_and_is_idempotent(harness: _ApplyHarness) -> None:
    """(a) apply_rls_policies writes the fence/baseline/scope policies + enables
    and forces RLS on the tenant-scoped tables; re-apply is a no-op (same set)."""
    from dazzle.db.rls_apply import apply_rls_policies

    async def _apply(conn: Any) -> int:
        return await apply_rls_policies(conn, harness.appspec, harness.entities)

    count = asyncio.run(_with_conn(harness.conn_url(), _apply))
    assert count > 0, "expected a non-empty RLS DDL set for the shared_schema fixture"

    # Project is the scoped entity: restrictive fence + per-verb scope policies
    # (read/list → scope_select, update → scope_update); NO baseline, no
    # scope_insert/scope_delete (no create/delete scope rule in the fixture).
    project_policies = _live_policy_names(harness.scratch_url, "Project")
    assert project_policies == {"tenant_fence", "scope_select", "scope_update"}, (
        f"unexpected Project policy set: {project_policies}"
    )
    p_enabled, p_forced = _rls_flags(harness.scratch_url, "Project")
    assert p_enabled and p_forced, "Project must have RLS enabled AND forced"

    # Member/Task are tenant-flat scoped → restrictive fence + permissive
    # baseline.
    for flat in ("Member", "Task"):
        flat_policies = _live_policy_names(harness.scratch_url, flat)
        assert flat_policies == {"tenant_fence", "tenant_baseline"}, (
            f"unexpected {flat} policy set: {flat_policies}"
        )
        f_enabled, f_forced = _rls_flags(harness.scratch_url, flat)
        assert f_enabled and f_forced, f"{flat} must have RLS enabled AND forced"

    # Workspace is the tenant ROOT (not tenant-scoped) → no RLS policies.
    assert _live_policy_names(harness.scratch_url, "Workspace") == set(), (
        "the tenant-root Workspace must NOT carry RLS policies"
    )

    # Idempotency: re-apply → no error, identical policy set + count.
    count2 = asyncio.run(_with_conn(harness.conn_url(), _apply))
    assert count2 == count, "re-apply changed the statement count (not idempotent)"
    assert _live_policy_names(harness.scratch_url, "Project") == project_policies
    assert _rls_flags(harness.scratch_url, "Project") == (True, True)


def test_no_drift_after_clean_apply(harness: _ApplyHarness) -> None:
    """(b) detect_rls_drift returns [] immediately after a clean apply."""
    from dazzle.db.rls_apply import apply_rls_policies
    from dazzle.db.rls_drift import detect_rls_drift

    async def _apply(conn: Any) -> int:
        return await apply_rls_policies(conn, harness.appspec, harness.entities)

    async def _drift(conn: Any) -> list[dict[str, Any]]:
        return await detect_rls_drift(conn, harness.appspec, harness.entities)

    asyncio.run(_with_conn(harness.conn_url(), _apply))
    drifts = asyncio.run(_with_conn(harness.conn_url(), _drift))
    assert drifts == [], f"a clean apply must show NO drift, got {drifts}"


def test_drift_detected_after_policy_dropped(harness: _ApplyHarness) -> None:
    """(c) Dropping tenant_fence on Project → detect_rls_drift reports exactly
    that table's missing fence; the clean tables report nothing."""
    from dazzle.db.rls_apply import apply_rls_policies
    from dazzle.db.rls_drift import detect_rls_drift

    async def _apply(conn: Any) -> int:
        return await apply_rls_policies(conn, harness.appspec, harness.entities)

    async def _drift(conn: Any) -> list[dict[str, Any]]:
        return await detect_rls_drift(conn, harness.appspec, harness.entities)

    asyncio.run(_with_conn(harness.conn_url(), _apply))

    # Drop the fence on Project (as the owner/admin — DDL is not RLS-governed).
    sync_url = harness.conn_url()
    with psycopg.connect(sync_url, autocommit=True) as admin:
        admin.execute('DROP POLICY tenant_fence ON "Project"')

    drifts = asyncio.run(_with_conn(harness.conn_url(), _drift))

    by_entity = {d["entity"]: d for d in drifts}
    assert "Project" in by_entity, f"Project drift not detected; got {drifts}"
    project_issues = by_entity["Project"]["issues"]
    assert any("tenant_fence" in i and "missing" in i for i in project_issues), (
        f"expected a missing tenant_fence issue on Project, got {project_issues}"
    )
    # Exactly one drifted table — the clean tables (Member/Task) report nothing.
    assert set(by_entity) == {"Project"}, (
        f"only Project should have drifted, but got {set(by_entity)}"
    )


def test_drift_detected_when_rls_disabled(harness: _ApplyHarness) -> None:
    """Disabling RLS on one table → detect_rls_drift reports that table's
    RLS-not-enabled issue and leaves the clean tables alone."""
    from dazzle.db.rls_apply import apply_rls_policies
    from dazzle.db.rls_drift import detect_rls_drift

    async def _apply(conn: Any) -> int:
        return await apply_rls_policies(conn, harness.appspec, harness.entities)

    async def _drift(conn: Any) -> list[dict[str, Any]]:
        return await detect_rls_drift(conn, harness.appspec, harness.entities)

    asyncio.run(_with_conn(harness.conn_url(), _apply))

    sync_url = harness.conn_url()
    with psycopg.connect(sync_url, autocommit=True) as admin:
        admin.execute('ALTER TABLE "Member" DISABLE ROW LEVEL SECURITY')

    drifts = asyncio.run(_with_conn(harness.conn_url(), _drift))
    by_entity = {d["entity"]: d for d in drifts}
    assert "Member" in by_entity, f"Member drift not detected; got {drifts}"
    assert any("not enabled" in i for i in by_entity["Member"]["issues"])
    assert set(by_entity) == {"Member"}, (
        f"only Member should have drifted, but got {set(by_entity)}"
    )


def test_apply_follows_physical_column_type_1531(harness: _ApplyHarness) -> None:
    """(#1531) A scope column whose LIVE type is TEXT — a deployment whose
    column-type migration hasn't been generated yet (the pre-#1522 belongs_to
    shape: TEXT, no FK) — must get a ``::text`` GUC cast. The logical-only
    resolver emitted ``::uuid`` and ``CREATE POLICY`` failed with
    ``operator does not exist: text = uuid`` on the production upgrade path."""
    from dazzle.db.rls_apply import apply_rls_policies

    # Degrade Project.owner to the pre-migration physical shape: drop its FK
    # constraint(s), then retype the column TEXT.
    with psycopg.connect(harness.conn_url(), autocommit=True) as admin:
        fks = admin.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = '\"Project\"'::regclass AND contype = 'f'"
        ).fetchall()
        for (conname,) in fks:
            admin.execute(f'ALTER TABLE "Project" DROP CONSTRAINT "{conname}"')
        admin.execute('ALTER TABLE "Project" ALTER COLUMN owner TYPE text USING owner::text')

    async def _apply(conn: Any) -> int:
        return await apply_rls_policies(conn, harness.appspec, harness.entities)

    # Pre-fix this raised psycopg.errors.UndefinedFunction (text = uuid).
    count = asyncio.run(_with_conn(harness.conn_url(), _apply))
    assert count > 0

    # The applied scope policy casts the GUC to the physical TEXT type.
    with psycopg.connect(harness.conn_url()) as conn:
        row = conn.execute(
            "SELECT qual FROM pg_policies "
            "WHERE schemaname='public' AND tablename='Project' AND policyname='scope_select'"
        ).fetchone()
    assert row is not None, "scope_select policy missing after apply"
    qual = row[0]
    assert "::text" in qual, f"expected a ::text GUC cast, got: {qual}"
    assert "::uuid" not in qual, f"no ::uuid cast may target the TEXT column: {qual}"


def test_partial_failure_rolls_back_prior_policies_1531(
    harness: _ApplyHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(#1531 blast radius) apply runs DROP-then-CREATE per policy on an
    autocommit conn; a mid-run failure used to leave the dropped policy absent
    (intra-tenant scope silently lapsed). The single-transaction apply must
    roll back so the pre-existing policy survives a failed run."""
    import dazzle.http.runtime.rls_schema as rls_schema_mod
    from dazzle.db.rls_apply import apply_rls_policies

    async def _apply(conn: Any) -> int:
        return await apply_rls_policies(conn, harness.appspec, harness.entities)

    # Clean apply first: scope_select exists on Project.
    asyncio.run(_with_conn(harness.conn_url(), _apply))
    assert "scope_select" in _live_policy_names(harness.scratch_url, "Project")

    # Second apply drops scope_select then fails before recreating anything.
    def _failing_ddl(*args: Any, **kwargs: Any) -> list[str]:
        return ['DROP POLICY IF EXISTS scope_select ON "Project"', "SELECT 1/0"]

    monkeypatch.setattr(rls_schema_mod, "build_all_rls_ddl", _failing_ddl)
    with pytest.raises(Exception, match="division by zero"):
        asyncio.run(_with_conn(harness.conn_url(), _apply))

    # The transaction rolled back — the previously-applied policy is intact.
    assert "scope_select" in _live_policy_names(harness.scratch_url, "Project"), (
        "a failed apply must not leave the table without its scope policy"
    )
