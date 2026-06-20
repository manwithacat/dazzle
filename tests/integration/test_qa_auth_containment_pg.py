"""Real-PG proof of ephemeral QA-tenant provisioning + containment (Phase E.2, #1339)."""

from __future__ import annotations

import os
import time as _time
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.qa_sign import sign_qa_token

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_SECRET = "qa-int-secret"


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_qaauth_{uuid.uuid4().hex[:8]}"
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


def _app(store) -> TestClient:
    os.environ["QA_AUTH_SECRET"] = _SECRET
    from dazzle.http.runtime.qa_secure_routes import create_qa_secure_routes

    app = FastAPI()
    app.state.auth_store = store
    router = create_qa_secure_routes()
    assert router is not None
    app.include_router(router)
    return TestClient(app, follow_redirects=False)


# ── Task 1: provisioning ─────────────────────────────────────────────────────


def test_provision_test_tenant_creates_qa_org_admin_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="run123", roles=["admin"])

    assert prov.org.slug == "qa-run123"
    assert prov.org.is_test is True
    mships = store.get_memberships_for_identity(str(prov.admin.id))
    assert len(mships) == 1
    assert mships[0].tenant_id == prov.org.id
    assert mships[0].roles == ["admin"]


def test_teardown_excises_the_qa_tenant(scratch_url: str) -> None:
    """teardown_test_tenant removes the org + membership + admin identity."""
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant, teardown_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="teardown")
    # A QA tenant with no domain entities: excise needs an appspec with no
    # tenant-scoped entities + no tenant root (framework-org-as-tenant).
    appspec = SimpleNamespace(domain=SimpleNamespace(entities=[]), tenancy=None)
    with psycopg.connect(scratch_url) as conn:
        teardown_test_tenant(appspec, prov.org.id, conn=conn)

    assert store.get_organization_by_slug("qa-teardown") is None
    assert store.get_memberships_for_identity(str(prov.admin.id)) == []
    with psycopg.connect(scratch_url) as c:
        assert (
            c.execute("SELECT count(*) FROM users WHERE id=%s", (str(prov.admin.id),)).fetchone()[0]
            == 0
        )


# ── Task 4: contained QA-auth mint (happy path + adversarial) ────────────────


def test_mint_happy_path_scopes_session_to_test_org(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="rh", roles=["admin"])
    token = sign_qa_token(prov.admin.email, "rh", secret=_SECRET, now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == prov.org.id
    sid = resp.cookies.get("dazzle_session")
    ctx = store.validate_session(sid)
    assert ctx.active_membership is not None
    assert ctx.active_membership.tenant_id == prov.org.id


def test_mint_refuses_real_non_test_org(scratch_url: str) -> None:
    """Containment crux: a validly-signed token cannot mint into a real
    (is_test=false) org — the DB is_test gate refuses."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    real = store.create_organization(slug="qa-realish", name="Real", is_test=False)
    user = store.create_user(email="victim@real.test", password="pw123456", roles=["admin"])
    store.create_membership(tenant_id=real.id, identity_id=str(user.id), roles=["admin"])
    token = sign_qa_token("victim@real.test", "realish", secret=_SECRET, now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 403


def test_mint_rejects_expired_token(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="rx")
    token = sign_qa_token(prov.admin.email, "rx", secret=_SECRET, now=_time.time() - 120)

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 403


def test_mint_rejects_bad_signature(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="rz")
    token = sign_qa_token(prov.admin.email, "rz", secret="WRONG", now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 403


def test_mint_rejects_run_mismatch(scratch_url: str) -> None:
    """A token whose run_id doesn't resolve to a provisioned qa- org → 403."""
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="rm")
    token = sign_qa_token(prov.admin.email, "other", secret=_SECRET, now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 403


def test_mint_scopes_to_test_org_for_user_in_both_test_and_real(scratch_url: str) -> None:
    """A user who belongs to BOTH a test org and a real org: the mint binds the
    TEST org's membership only — never the real one (containment regression lock)."""
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="dual")
    # The same identity also belongs to a REAL org.
    real = store.create_organization(slug="acme", name="Acme", is_test=False)
    store.create_membership(tenant_id=real.id, identity_id=str(prov.admin.id), roles=["admin"])
    token = sign_qa_token(prov.admin.email, "dual", secret=_SECRET, now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == prov.org.id  # the TEST org, not the real one
    ctx = store.validate_session(resp.cookies.get("dazzle_session"))
    assert ctx.active_membership.tenant_id == prov.org.id
    assert ctx.active_membership.tenant_id != real.id
