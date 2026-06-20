"""Real-PG verification of Phase-A tenant construction rules (RLS tenancy).

Builds the ``fixtures/tenant_rls`` metadata, ``create_all()``s it on a disposable
database, and asserts the engine-level guarantees the Phase-A construction rules
buy — WITHOUT RLS (that lands in Phase B):

* **Composite FKs forbid cross-tenant references.** ``Task`` carries a composite
  FK ``(tenant_id, project) -> Project(tenant_id, id)``. A ``Task`` in tenant B
  that points at a ``Project`` row living in tenant A has no matching
  ``(tenant_id, id)`` parent and is rejected by Postgres with a foreign-key
  violation — the integrity hole that would otherwise let an attacker reference
  another tenant's row is closed at the engine level.
* **Uniqueness is tenant-scoped.** ``Member.email`` (an author-declared
  ``unique`` natural key) becomes ``UNIQUE(tenant_id, email)``: the same email
  succeeds under two different tenants, but a duplicate under the SAME tenant
  raises a unique violation.

It also sanity-checks that the framework actually injected ``tenant_id`` on the
descendant tables (a silent injection regression would otherwise pass other
gates) — see ``_build_fixture_metadata``.

Marked ``postgres`` (+ ``e2e``): skipped locally without ``TEST_DATABASE_URL`` /
``DATABASE_URL``; CI's ``postgres-tests`` job runs it against a real
``postgres:16`` service. The test stands up its OWN disposable scratch database
(``dazzle_rls_constraints_<uuid>``) on the target server and drops it in a
``finally`` so it never touches existing ``dazzle*`` databases.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import sqlalchemy as sa
from psycopg import errors as pg_errors

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls")


def _build_fixture_metadata() -> tuple[sa.MetaData, str]:
    """Load the fixture appspec and build its tenant-aware SA metadata.

    Asserts the framework injected the partition key on the descendant entities
    (so a silent injection regression is caught here, not just downstream).
    """
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    appspec = load_project_appspec(_PROJECT_ROOT)
    assert appspec.tenancy is not None, "fixture must declare a tenancy block"
    pk = appspec.tenancy.isolation.partition_key

    entities_by_name = {e.name: e for e in appspec.domain.entities}
    # The fixture declares Project/Task/Member WITHOUT tenant_id — injection must
    # have added it. Workspace (the tenant root) must NOT carry it.
    for scoped_name in ("Project", "Task", "Member"):
        ent = entities_by_name[scoped_name]
        assert any(f.name == pk for f in ent.fields), (
            f"{scoped_name} should have framework-injected {pk!r}; "
            f"got {[f.name for f in ent.fields]}"
        )
    assert all(f.name != pk for f in entities_by_name["Workspace"].fields), (
        "tenant root Workspace must not be tenant-scoped"
    )

    scoped = scoped_entity_names(appspec.domain.entities, pk)
    md = build_metadata(
        convert_entities(appspec.domain.entities),
        partition_key=pk,
        tenant_scoped=scoped,
    )
    return md, pk


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    """Yield an engine bound to a fresh disposable scratch database.

    Creates ``dazzle_rls_constraints_<uuid>`` on the configured server,
    ``create_all()``s the fixture metadata into it, and drops the database in a
    ``finally`` (even on failure) so nothing leaks and no existing ``dazzle*``
    DB is touched.
    """
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")

    scratch = f"dazzle_rls_constraints_{uuid.uuid4().hex[:12]}"
    admin_url = _PG_URL.replace("postgresql+psycopg://", "postgresql://")

    # CREATE/DROP DATABASE cannot run inside a transaction block.
    with psycopg.connect(admin_url, autocommit=True) as admin:
        # `scratch` is a uuid-derived identifier, never user input.
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived db name

    # Build the scratch URL by swapping the database segment of the admin URL.
    base, _, _old_db = admin_url.rpartition("/")
    # Drop any query string off the old db segment before splicing the new name.
    scratch_url = f"{base}/{scratch}"
    eng = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    try:
        md, _pk = _build_fixture_metadata()
        md.create_all(eng)
        yield eng
    finally:
        eng.dispose()
        with psycopg.connect(admin_url, autocommit=True) as admin:
            # Terminate any lingering backends so DROP DATABASE succeeds.
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep — uuid-derived


def _new_id() -> str:
    return str(uuid.uuid4())


def test_composite_fk_rejects_cross_tenant_reference(engine: sa.Engine) -> None:
    """A Task in tenant B referencing a Project that lives in tenant A is rejected
    by the composite FK ``(tenant_id, project) -> Project(tenant_id, id)``."""
    md, _pk = _build_fixture_metadata()
    workspace = md.tables["Workspace"]
    member = md.tables["Member"]
    project = md.tables["Project"]
    task = md.tables["Task"]

    tenant_a = _new_id()
    tenant_b = _new_id()
    project_id = _new_id()
    member_id = _new_id()

    with engine.begin() as conn:
        conn.execute(workspace.insert(), [{"id": tenant_a, "name": "Tenant A"}])
        conn.execute(workspace.insert(), [{"id": tenant_b, "name": "Tenant B"}])
        # Project now carries `owner ref Member required` (Phase C), so seed a
        # Member to own it. Project lives in tenant A.
        conn.execute(
            member.insert(),
            [{"tenant_id": tenant_a, "id": member_id, "email": "owner@example.test"}],
        )
        conn.execute(
            project.insert(),
            [{"tenant_id": tenant_a, "id": project_id, "name": "A's project", "owner": member_id}],
        )

    # A same-tenant Task is fine (control).
    with engine.begin() as conn:
        conn.execute(
            task.insert(),
            [
                {
                    "tenant_id": tenant_a,
                    "id": _new_id(),
                    "title": "In-tenant task",
                    "project": project_id,
                }
            ],
        )

    # A cross-tenant Task (tenant B referencing tenant A's project) must fail:
    # there is no Project row with (tenant_id=B, id=project_id).
    with pytest.raises(sa.exc.IntegrityError) as excinfo:
        with engine.begin() as conn:
            conn.execute(
                task.insert(),
                [
                    {
                        "tenant_id": tenant_b,
                        "id": _new_id(),
                        "title": "Cross-tenant task",
                        "project": project_id,
                    }
                ],
            )
    assert isinstance(excinfo.value.orig, pg_errors.ForeignKeyViolation), (
        f"expected a foreign-key violation, got {type(excinfo.value.orig).__name__}"
    )


def test_uniqueness_is_tenant_scoped(engine: sa.Engine) -> None:
    """``Member.email`` is unique per-tenant: the same email succeeds under two
    different tenants, but a duplicate under the same tenant raises."""
    md, _pk = _build_fixture_metadata()
    workspace = md.tables["Workspace"]
    member = md.tables["Member"]

    tenant_a = _new_id()
    tenant_b = _new_id()
    email = "alice@example.com"

    with engine.begin() as conn:
        conn.execute(workspace.insert(), [{"id": tenant_a, "name": "Tenant A"}])
        conn.execute(workspace.insert(), [{"id": tenant_b, "name": "Tenant B"}])

    # Same email under two DIFFERENT tenants both succeed (tenant-scoped uniqueness).
    with engine.begin() as conn:
        conn.execute(member.insert(), [{"tenant_id": tenant_a, "id": _new_id(), "email": email}])
        conn.execute(member.insert(), [{"tenant_id": tenant_b, "id": _new_id(), "email": email}])

    # The same email TWICE under the same tenant violates UNIQUE(tenant_id, email).
    with pytest.raises(sa.exc.IntegrityError) as excinfo:
        with engine.begin() as conn:
            conn.execute(
                member.insert(), [{"tenant_id": tenant_a, "id": _new_id(), "email": email}]
            )
    assert isinstance(excinfo.value.orig, pg_errors.UniqueViolation), (
        f"expected a unique violation, got {type(excinfo.value.orig).__name__}"
    )
