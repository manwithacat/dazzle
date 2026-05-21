"""End-to-end tests for the dynamic RBAC verifier (#1171). Requires PostgreSQL."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.postgres

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL")
async def test_disposable_database_creates_and_drops() -> None:
    import psycopg

    from dazzle.rbac.verifier import _DisposableDatabase

    created_url: str | None = None
    async with _DisposableDatabase(_PG_URL) as db_url:
        created_url = db_url
        # The scratch DB exists and is connectable.
        with psycopg.connect(db_url):
            pass  # verify the scratch DB is connectable

    # After exit the scratch DB is gone.
    assert created_url is not None
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(created_url).close()


@pytest.mark.asyncio
@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL")
async def test_verifier_app_context_boots_and_authenticates() -> None:
    """The verifier context boots the Dazzle app in-process, creates a
    bootstrap superuser, and returns an authenticated httpx client."""
    from dazzle.rbac.verifier import (
        _SUPERUSER_EMAIL,
        _DisposableDatabase,
        _verifier_app_context,
    )

    async with _DisposableDatabase(_PG_URL) as db_url:
        async with _verifier_app_context("fixtures/rbac_validation", db_url) as ctx:
            assert ctx.appspec is not None
            # The app booted — /health is always registered by SystemRoutesSubsystem.
            resp = await ctx.client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"

            # The client genuinely carries an authenticated superuser session:
            # /auth/me is auth-gated (401 without a session) and the verifier
            # bootstrap user has is_superuser=True.
            me = await ctx.client.get("/auth/me")
            assert me.status_code == 200, me.text
            me_data = me.json()
            assert me_data["email"] == _SUPERUSER_EMAIL
            assert me_data["is_superuser"] is True
