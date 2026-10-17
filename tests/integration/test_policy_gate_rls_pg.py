"""Real-PG proof that a ``# dazzle:implements`` override reads through the RLS fence (#1801).

Boots a ``tenancy: shared_schema`` app (``fixtures/tenant_rls``'s scoped Project,
plus a surface so the CRUD read route exists) in-process as a
NON-superuser role that owns the scratch database, so the runtime-applied
``FORCE ROW LEVEL SECURITY`` fences the app's own connections (superusers bypass
RLS; a table owner does not under FORCE). A real ``AuthStore`` session with an
active membership signs in; the override is mounted through the real
``_wrap_with_policy_gate``.

The gate used to read a ``request.state.auth_context`` nothing set (401 for every
signed-in user) and, once a host set it, ran its scoped pre-read with no tenant
GUC bound (404 for every real row). It now resolves the session and binds the
GUCs through the CRUD auth dependency's own resolver, so the override sees the
row the same user reads via ``GET /projects/{id}``.
"""

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi import Request

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_MANIFEST = """[project]
name = "gate_rls"
version = "0.1.0"
root = "gate_rls"

[modules]
paths = ["./dsl"]
"""
_DSL = """module gate_rls

app gate_rls "Gate RLS probe"

tenancy:
  mode: shared_schema
  partition_key: tenant_id
  entities_excluded: [User]

entity Workspace "Workspace":
  archetype: tenant
  id: uuid pk
  name: str(100) required

persona worker "Worker":
  description: "Tenant member scoped to their own projects"

entity User "User":
  id: uuid pk
  email: str(200) required unique

entity Project "Project":
  id: uuid pk
  name: str(100) required
  owner: ref User required

  permit:
    read: role(worker)
    list: role(worker)

  scope:
    read: owner = current_user
      as: worker
    list: owner = current_user
      as: worker

surface project_list "Projects":
  uses entity Project
  mode: list
  section main:
    field name "Name"
"""
_ROLE_PW = "gate-owner-pw"  # nosec B105 — disposable scratch role only


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


def _with(url: str, *, db: str, user: str | None = None, password: str | None = None) -> str:
    head, _, rest = url.partition("://")
    creds, _, hostpart = rest.rpartition("@")
    host = hostpart.rpartition("/")[0] if "/" in hostpart else hostpart
    login = f"{user}:{password}@" if user else (f"{creds}@" if creds else "")
    return f"{head}://{login}{host}/{db}"


@pytest.fixture
def owner_db() -> Iterator[tuple[str, str]]:
    """(owner_url, superuser_url) for a scratch DB owned by a non-superuser role."""
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _admin_url()
    suffix = uuid.uuid4().hex[:8]
    role, db = f"gate_owner_{suffix}", f"dazzle_gate_rls_{suffix}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{_ROLE_PW}'")  # nosemgrep
        a.execute(f'CREATE DATABASE "{db}" OWNER "{role}"')  # nosemgrep
    try:
        yield _with(admin, db=db, user=role, password=_ROLE_PW), _with(admin, db=db)
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')  # nosemgrep
            a.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep


def _write_project(root: Path) -> Path:
    """``fixtures/tenant_rls``'s Project shape plus a surface, so ``/projects/{id}`` exists."""
    (root / "dsl").mkdir()
    (root / "dazzle.toml").write_text(_MANIFEST)
    (root / "dsl" / "app.dsl").write_text(_DSL)
    return root


def _boot(owner_url: str, root: Path) -> Any:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.runtime.app_factory import build_server_config
    from dazzle.http.runtime.server import DazzleBackendApp

    appspec = load_project_appspec(root)
    config = build_server_config(
        appspec,
        database_url=owner_url,
        enable_auth=True,
        enable_test_mode=True,
        project_root=root,
    )
    builder = DazzleBackendApp(appspec, config=config)
    return builder, builder.build()


def _mount_gated_override(app: Any) -> None:
    # No `from __future__ import annotations` in this module: FastAPI must see the
    # real `Request` annotation on the handler (ADR-0014).
    from dazzle.http.runtime.route_overrides import _wrap_with_policy_gate

    async def read_project(request: Request, project_id: str) -> dict[str, Any]:
        return {"via": "override", "project_id": project_id}

    app.add_api_route(
        "/gate/projects/{project_id}",
        _wrap_with_policy_gate(read_project, entity="Project", op="read", via="project_id"),
        methods=["GET"],
    )


def _seed_tenant(superuser_url: str, store: Any, *, slug: str) -> tuple[str, str]:
    """An org + its tenant-root Workspace at one id, a worker member, and their project.

    Returns ``(session_id, project_id)``. Domain rows go in as superuser (bypassing
    the fence the app itself is subject to).
    """
    org_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
    user = store.create_user(email=f"worker@{slug}.test", password="pw123456", roles=["worker"])
    now = datetime.now(UTC).isoformat()
    with psycopg.connect(superuser_url, autocommit=True) as c:
        c.execute('INSERT INTO "Workspace" (id, name) VALUES (%s, %s)', (org_id, slug))
        c.execute(
            "INSERT INTO organizations (id, slug, name, status, is_test, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'active', false, %s, %s)",
            (org_id, slug, slug, now, now),
        )
        # The domain User row (matched by email) is what bare `current_user` resolves to.
        domain_user_id = str(uuid.uuid4())
        c.execute(
            'INSERT INTO "User" (id, email) VALUES (%s, %s)',
            (domain_user_id, f"worker@{slug}.test"),
        )
        c.execute(
            'INSERT INTO "Project" (tenant_id, id, name, owner) VALUES (%s, %s, %s, %s)',
            (org_id, project_id, f"{slug} project", domain_user_id),
        )
    membership = store.create_membership(
        tenant_id=org_id, identity_id=str(user.id), roles=["worker"]
    )
    session_id = store.create_session(user).id
    store.set_session_active_membership(session_id, membership.id, identity_id=str(user.id))
    return session_id, project_id


def test_gated_override_reads_the_row_the_crud_route_reads(
    owner_db: tuple[str, str], tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    owner_url, superuser_url = owner_db
    builder, app = _boot(owner_url, _write_project(tmp_path))
    _mount_gated_override(app)
    store = builder.auth_store
    assert store is not None
    session_a, project_a = _seed_tenant(superuser_url, store, slug="acme")
    _session_b, project_b = _seed_tenant(superuser_url, store, slug="globex")

    with psycopg.connect(owner_url) as c:
        # The app's own role is fenced: no tenant bound, no rows.
        assert c.execute('SELECT count(*) FROM "Project"').fetchone() == (0,)

    try:
        client = TestClient(app, follow_redirects=False)
        client.cookies.set("dazzle_session", session_a)

        crud = client.get(f"/projects/{project_a}")
        assert crud.status_code == 200, crud.text

        gated = client.get(f"/gate/projects/{project_a}")
        assert gated.status_code == 200, gated.text
        assert gated.json() == {"via": "override", "project_id": project_a}

        # Another tenant's row is invisible through the same gate.
        assert client.get(f"/gate/projects/{project_b}").status_code == 404

        anonymous = TestClient(app, follow_redirects=False)
        assert anonymous.get(f"/gate/projects/{project_a}").status_code == 401
    finally:
        db_manager = getattr(builder, "_db_manager", None)
        if db_manager is not None:
            db_manager.close_pool()
