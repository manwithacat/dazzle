"""Real-PG proof of the member profile-resolution route (auth Plan 3c.ii).

Boots a minimal app (the profile route + a real MemberProfile Repository over
fixtures/tenant_rls) and proves GET/POST /me/profile get-or-creates the current
member's profile keyed by (active membership tenant_id, current_user.id) —
consuming create-time tenant_id injection (Plan 1d) + the profile schema (3c).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_meprof_{uuid.uuid4().hex[:8]}"
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


def _setup(scratch_url: str):
    """Schema + auth tables + a MemberProfile Repository over the fixture."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.http.runtime.model_generator import generate_all_entity_models
    from dazzle.http.runtime.pg_backend import PostgresBackend
    from dazzle.http.runtime.repository import RepositoryFactory
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    appspec = load_project_appspec(_PROJECT_ROOT)
    pk = appspec.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    back_entities = convert_entities(appspec.domain.entities)
    md = build_metadata(back_entities, partition_key=pk, tenant_scoped=scoped)
    engine = sa.create_engine(scratch_url.replace("postgresql://", "postgresql+psycopg://"))
    md.create_all(engine)

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    models = generate_all_entity_models(back_entities)
    repos = RepositoryFactory(PostgresBackend(scratch_url), models).create_all_repositories(
        back_entities
    )
    return appspec, store, repos


def _app(store, appspec, repos):
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.profile_routes import create_profile_routes

    app = FastAPI()
    app.state.auth_store = store
    app.state.appspec = appspec
    app.state.repositories = repos
    app.state.sitespec = {}
    app.include_router(create_profile_routes())
    return app


def _make_org(store, scratch_url, *, slug, name) -> str:
    """Create an org + its 1:1 tenant-root Workspace row at a shared UUID id.

    Mirrors ``provision_single_org`` (org id == tenant-root uuid). The bare
    ``create_organization`` would mint a token_urlsafe id incompatible with the
    uuid ``Workspace.id``/injected ``tenant_id`` columns — so insert both rows at
    one uuid, as a real archetype-tenant provisioning does.
    """
    from datetime import UTC, datetime

    org_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute('INSERT INTO "Workspace" (id, name) VALUES (%s, %s)', (org_id, name))
        c.execute(
            "INSERT INTO organizations (id, slug, name, status, is_test, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'active', false, %s, %s)",
            (org_id, slug, name, now, now),
        )
    return org_id


def _member_client(app, store, scratch_url, *, email, org_id):
    from fastapi.testclient import TestClient

    user = store.create_user(email=email, password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id=org_id, identity_id=str(user.id), roles=["worker"])
    sid = store.create_session(user).id
    store.set_session_active_membership(sid, m.id, identity_id=str(user.id))
    client = TestClient(app, follow_redirects=False)
    client.cookies.set("dazzle_session", sid)
    return client, user, m


def _profile_rows(scratch_url, identity_id):
    from psycopg.rows import dict_row

    with psycopg.connect(scratch_url, row_factory=dict_row) as c:
        return c.execute(
            'SELECT * FROM "MemberProfile" WHERE identity_id = %s', (identity_id,)
        ).fetchall()


def test_get_empty_then_create_then_update(scratch_url: str) -> None:
    appspec, store, repos = _setup(scratch_url)
    app = _app(store, appspec, repos)
    org_id = _make_org(store, scratch_url, slug="acme", name="Acme")
    client, user, _m = _member_client(app, store, scratch_url, email="a@acme.test", org_id=org_id)

    # GET with no profile → form (empty).
    r = client.get("/me/profile")
    assert r.status_code == 200
    assert "display_name" in r.text and "Your profile in Acme" in r.text
    assert _profile_rows(scratch_url, str(user.id)) == []

    # POST creates — tenant_id auto-injected from the bound GUC, identity_id = caller.
    assert client.post("/me/profile", data={"display_name": "Alice"}).status_code == 303
    rows = _profile_rows(scratch_url, str(user.id))
    assert len(rows) == 1
    assert rows[0]["display_name"] == "Alice"
    assert str(rows[0]["tenant_id"]) == org_id  # create-time injection (Plan 1d)
    assert str(rows[0]["identity_id"]) == str(user.id)

    # POST again updates the SAME row (no duplicate).
    assert client.post("/me/profile", data={"display_name": "Alicia"}).status_code == 303
    rows = _profile_rows(scratch_url, str(user.id))
    assert len(rows) == 1 and rows[0]["display_name"] == "Alicia"


def test_profile_is_identity_scoped(scratch_url: str) -> None:
    appspec, store, repos = _setup(scratch_url)
    app = _app(store, appspec, repos)
    org_id = _make_org(store, scratch_url, slug="acme", name="Acme")
    a_client, a_user, _ = _member_client(
        app, store, scratch_url, email="a@acme.test", org_id=org_id
    )
    b_client, b_user, _ = _member_client(
        app, store, scratch_url, email="b@acme.test", org_id=org_id
    )

    a_client.post("/me/profile", data={"display_name": "Alice"})
    # B (same org) has no profile yet — sees the empty form, not Alice's.
    assert _profile_rows(scratch_url, str(b_user.id)) == []
    b_client.post("/me/profile", data={"display_name": "Bob"})
    assert _profile_rows(scratch_url, str(a_user.id))[0]["display_name"] == "Alice"
    assert _profile_rows(scratch_url, str(b_user.id))[0]["display_name"] == "Bob"


def test_same_identity_two_orgs_returns_active_org_profile(scratch_url: str) -> None:
    appspec, store, repos = _setup(scratch_url)
    app = _app(store, appspec, repos)
    from fastapi.testclient import TestClient

    org_a = _make_org(store, scratch_url, slug="a", name="Org A")
    org_b = _make_org(store, scratch_url, slug="b", name="Org B")
    user = store.create_user(email="multi@x.test", password="pw123456", roles=["worker"])
    ma = store.create_membership(tenant_id=org_a, identity_id=str(user.id), roles=["worker"])
    mb = store.create_membership(tenant_id=org_b, identity_id=str(user.id), roles=["worker"])
    sid = store.create_session(user).id

    # Active in A → create A's profile.
    store.set_session_active_membership(sid, ma.id, identity_id=str(user.id))
    client = TestClient(app, follow_redirects=False)
    client.cookies.set("dazzle_session", sid)
    client.post("/me/profile", data={"display_name": "In A"})

    # Switch active to B → create B's profile; the GET reflects the active org only.
    store.set_session_active_membership(sid, mb.id, identity_id=str(user.id))
    client.post("/me/profile", data={"display_name": "In B"})
    rget = client.get("/me/profile")
    assert "In B" in rget.text and "In A" not in rget.text  # active = B

    rows = _profile_rows(scratch_url, str(user.id))
    by_tenant = {str(r["tenant_id"]): r["display_name"] for r in rows}
    assert by_tenant == {org_a: "In A", org_b: "In B"}  # two distinct profiles, one per org


def test_client_cannot_smuggle_identity_or_tenant(scratch_url: str) -> None:
    appspec, store, repos = _setup(scratch_url)
    app = _app(store, appspec, repos)
    org_id = _make_org(store, scratch_url, slug="acme", name="Acme")
    other_org = _make_org(store, scratch_url, slug="other", name="Other")
    client, user, _ = _member_client(app, store, scratch_url, email="a@acme.test", org_id=org_id)

    # Extra identity_id/tenant_id/id form fields must be ignored (managed fields).
    client.post(
        "/me/profile",
        data={
            "display_name": "Alice",
            "identity_id": str(uuid.uuid4()),
            "tenant_id": other_org,
            "id": str(uuid.uuid4()),
        },
    )
    rows = _profile_rows(scratch_url, str(user.id))
    assert len(rows) == 1
    assert str(rows[0]["identity_id"]) == str(user.id)  # caller's, not smuggled
    assert str(rows[0]["tenant_id"]) == org_id  # bound GUC, not smuggled
