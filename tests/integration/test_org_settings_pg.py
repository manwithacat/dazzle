"""Real-PG proof of organizations.settings round-trip (#1424 phase 1)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_orgsettings_{uuid.uuid4().hex[:8]}"
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


@pytest.mark.postgres
def test_org_settings_roundtrip_pg(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    store.set_org_settings(org.id, {"domain_join_policy": "auto_join"})
    assert store.get_org_settings(org.id) == {"domain_join_policy": "auto_join"}


@pytest.mark.postgres
def test_org_settings_default_empty_pg(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="beta", name="Beta Corp")
    assert store.get_org_settings(org.id) == {}


@pytest.mark.postgres
def test_org_settings_missing_org_pg(store_url: str) -> None:
    store = _store(store_url)
    assert store.get_org_settings("nonexistent-id") == {}
