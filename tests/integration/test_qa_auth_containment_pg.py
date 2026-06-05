"""Real-PG proof of ephemeral QA-tenant provisioning + containment (Phase E.2, #1339)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    from dazzle.back.runtime.qa_secure_routes import create_qa_secure_routes

    app = FastAPI()
    app.state.auth_store = store
    router = create_qa_secure_routes()
    assert router is not None
    app.include_router(router)
    return TestClient(app, follow_redirects=False)


# ── Task 1: provisioning ─────────────────────────────────────────────────────


def test_provision_test_tenant_creates_qa_org_admin_membership(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.back.runtime.auth.store import AuthStore

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

    from dazzle.back.runtime.auth.qa_provision import provision_test_tenant, teardown_test_tenant
    from dazzle.back.runtime.auth.store import AuthStore

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
