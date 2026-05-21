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


@pytest.mark.asyncio
@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL")
async def test_seed_role_users_creates_one_user_per_role() -> None:
    """_seed_role_users creates one user per role and the users can authenticate."""
    import httpx

    from dazzle.cli.rbac import _login
    from dazzle.rbac.verifier import (
        _DisposableDatabase,
        _seed_role_users,
        _verifier_app_context,
    )

    async with _DisposableDatabase(_PG_URL) as db_url:
        async with _verifier_app_context("fixtures/rbac_validation", db_url) as ctx:
            assert ctx.auth_store is not None, "auth_store must be present in _VerifierContext"
            creds = await _seed_role_users(ctx.auth_store, roles=["doctor", "nurse"])

            # One entry per requested role.
            assert set(creds.keys()) == {"doctor", "nurse"}
            for role, (email, password) in creds.items():
                assert role in email, f"email {email!r} should contain the role name"
                assert password

            # The seeded users can actually authenticate — use the same in-process
            # transport as ctx.client so no network is required.
            transport = ctx.client._transport  # type: ignore[attr-defined]
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://verifier.local",
                follow_redirects=True,
            ) as role_client:
                await _login(role_client, "http://verifier.local", *creds["doctor"])
                me = await role_client.get("/auth/me")
                assert me.status_code == 200, me.text
                me_data = me.json()
                assert me_data["email"] == creds["doctor"][0]

            # Idempotent — calling again does not raise.
            creds2 = await _seed_role_users(ctx.auth_store, roles=["doctor"])
            assert creds2["doctor"] == creds["doctor"]


@pytest.mark.asyncio
@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL")
async def test_seed_baseline_rows_returns_entity_ids() -> None:
    """_seed_baseline_rows creates at least one seedable entity and returns its id."""
    from dazzle.rbac.verifier import (
        _DisposableDatabase,
        _seed_baseline_rows,
        _verifier_app_context,
    )

    async with _DisposableDatabase(_PG_URL) as db_url:
        async with _verifier_app_context("fixtures/rbac_validation", db_url) as ctx:
            # rbac_validation has Staff (no FK deps) — seed just that entity
            # to keep the test focused and fast.
            baseline = await _seed_baseline_rows(
                ctx.client,
                entities=["Staff"],
                appspec=ctx.appspec,
            )
            assert "Staff" in baseline, (
                "Staff has no FK dependencies and should always seed successfully"
            )
            assert baseline["Staff"]  # non-empty id string
