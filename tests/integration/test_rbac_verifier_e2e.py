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
            assert ctx.client._transport is not None  # type: ignore[attr-defined]
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
    """_seed_baseline_rows creates a baseline row via a create-capable role.

    Uses `examples/simple_task` rather than `fixtures/rbac_validation`:
    entity REST CRUD routes are generated from `surface` declarations
    (mode: create -> POST), and rbac_validation has no surfaces. The seed
    POST goes through `permit:` AND `scope:` gates, so the request must
    come from a role-user that satisfies both — the roles-less bootstrap
    superuser is rejected by every create gate (403). #1171 Task 6:
    `_seed_baseline_rows` now derives a create-capable role from the static
    matrix and seeds the row through that role's authenticated client.
    """
    from dazzle.rbac.matrix import generate_access_matrix
    from dazzle.rbac.verifier import (
        _DisposableDatabase,
        _probe_transport,
        _seed_baseline_rows,
        _seed_role_users,
        _verifier_app_context,
    )

    async with _DisposableDatabase(_PG_URL) as db_url:
        async with _verifier_app_context("examples/simple_task", db_url) as ctx:
            assert ctx.auth_store is not None
            matrix = generate_access_matrix(ctx.appspec)
            creds = await _seed_role_users(ctx.auth_store, roles=list(matrix.roles))

            assert ctx.client._transport is not None  # type: ignore[attr-defined]
            transport = _probe_transport(ctx.client._transport)  # type: ignore[attr-defined]
            baseline = await _seed_baseline_rows(
                transport=transport,
                base_url="http://verifier.local",
                matrix=matrix,
                creds=creds,
                entities=["Task"],
                appspec=ctx.appspec,
            )

            assert "Task" in baseline, (
                "Task create is permitted for role(admin|manager|member) and "
                "the entity has only a required str field — _seed_baseline_rows "
                "should pick a create-capable role and seed it successfully"
            )
            assert baseline["Task"]  # non-empty id string


@pytest.mark.asyncio
@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL")
async def test_verify_runs_end_to_end_and_produces_cells() -> None:
    """`verify()` runs the full orchestration against `examples/simple_task`.

    `examples/simple_task` is a correct-by-design app: every entity's
    observed HTTP behaviour must match its static RBAC matrix, so a clean
    run shows **zero violations**. This test pins both the orchestration
    (disposable DB, in-process boot, role-user seeding, per-cell probing)
    *and* the substance of the verdict — that a meaningful share of cells
    reach a definitive PASS rather than an inconclusive WARNING.

    Baseline-fix history (#1171 Task 6)
    -----------------------------------
    Before the baseline-seeding fix the report was 22 PASS / 0 VIOLATION /
    113 WARNING: baseline rows were seeded by the roles-less bootstrap
    superuser, which every `permit:`/`scope: create:` gate rejects with 403,
    so no rows existed and every read/update/delete cell 404'd to a WARNING.
    The fix seeds each entity via a create-capable role-user, probes
    create/update with valid bodies, teaches `compare_cell` the modern
    `PERMIT_SCOPED` decision, and sends the CSRF token on `PUT`. After the
    fix the run is ~75 PASS / 0 VIOLATION / ~60 WARNING.

    The residual WARNINGs are structurally legitimate: ~48 of them are
    framework/admin entities (AIJob, SystemHealth, SystemMetric,
    DeployHistory) that declare **no CRUD `surface`**, so they have no
    POST/PUT/DELETE routes to probe (405) and no seedable rows (404). The
    verifier correctly cannot turn "there is no route" into a definitive
    verdict — that is a property of the app, not a verifier weakness.
    """
    from pathlib import Path

    from dazzle.rbac.verifier import CellResult, VerificationReport, verify

    assert _PG_URL is not None
    project_root = Path("examples/simple_task")
    report = await verify(project_root, server_database_url=_PG_URL)

    assert isinstance(report, VerificationReport)
    assert report.app_name == str(project_root)
    assert report.matrix is not None

    # The orchestration ran cleanly — no boot/provisioning failure.
    assert report.error is None, f"verify() boot failed: {report.error}"

    # The matrix has roles × entities × operations cells; verify() probes
    # every one of them, so the report must be populated and self-consistent.
    assert report.total > 0, "verify() should probe at least one matrix cell"
    assert report.total == len(report.cells)
    assert report.total == report.passed + report.violated + report.warnings

    # A correct-by-design app must show no RBAC violations. A violation here
    # is a genuine finding — either an enforcement bug in simple_task or a
    # verifier bug — and must be investigated, never silenced.
    violations = [
        (c.role, c.entity, c.operation, c.observed_status)
        for c in report.cells
        if c.result == CellResult.VIOLATION
    ]
    assert report.violated == 0, (
        "examples/simple_task is correct-by-design — a violation indicates a "
        f"real RBAC enforcement bug or a verifier bug: {violations}"
    )

    # The baseline-seeding fix must produce *definitive* verdicts, not a wall
    # of inconclusive WARNINGs. Two concrete, justified thresholds:
    #
    #  1. PASS is the majority outcome — more cells reach a definitive PASS
    #     than land in WARNING. (Post-fix ~75 PASS vs ~60 WARNING; the 60 are
    #     the no-CRUD-surface framework entities described above.)
    #  2. WARNINGs sit in a justified band — a *two-sided* regression guard.
    #     Upper bound (< 90): WARNINGs dropped well below the pre-fix count of
    #     113, with headroom for framework-entity drift; fails loudly if the
    #     baseline fix ever regresses toward all-superuser-seeding.
    #     Lower bound (>= 40): ~48 residual WARNINGs are framework/admin
    #     entities (AIJob, SystemHealth, SystemMetric, DeployHistory) that
    #     declare no CRUD `surface` — they have no routes to probe and cannot
    #     yield a definitive verdict. If WARNINGs ever fall below this floor,
    #     a no-route probe (404/405) is silently being counted as a PASS,
    #     inflating the PASS share — that must fail the test, not pass quietly.
    assert report.passed > report.warnings, (
        "expected PASS to be the majority verdict after the baseline fix, "
        f"got {report.passed} PASS vs {report.warnings} WARNING"
    )
    assert 40 <= report.warnings < 90, (
        f"WARNINGs ({report.warnings}) left the expected band [40, 90): "
        "above 90 means baseline seeding regressed; below 40 means a "
        "no-route probe is being miscounted as a definitive PASS"
    )
    assert report.passed > 0

    # Every cell carries the expected structure.
    for cell in report.cells:
        assert cell.role
        assert cell.entity
        assert cell.operation
        assert isinstance(cell.result, CellResult)
        assert isinstance(cell.observed_status, int)
