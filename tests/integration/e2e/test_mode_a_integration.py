"""Integration tests for Mode A against a real Postgres + real subprocess.

Gated by @pytest.mark.integration. Skipped in the default pytest run.
Opt-in: `pytest -m integration tests/integration/e2e/ -v`.

Requires:
  - DATABASE_URL set to a reachable Postgres instance
  - REDIS_URL set to a reachable Redis instance
  - pg_dump and pg_restore on PATH
  - examples/support_tickets/ present with dazzle.toml
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest

from dazzle.e2e.errors import ModeAlreadyRunningError
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

pytestmark = pytest.mark.integration


def _has_infra() -> bool:
    return bool(os.environ.get("DATABASE_URL")) and bool(os.environ.get("REDIS_URL"))


@pytest.fixture(autouse=True)
def _skip_if_no_infra() -> None:
    if not _has_infra():
        pytest.skip("DATABASE_URL and REDIS_URL must be set for integration tests")


@pytest.fixture
def support_tickets_root() -> Path:
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        candidate = parent / "examples" / "support_tickets"
        if candidate.exists() and (candidate / "dazzle.toml").exists():
            return candidate
    pytest.skip("examples/support_tickets not found in repo")
    raise AssertionError  # unreachable


@pytest.mark.asyncio
async def test_mode_a_launch_and_teardown(support_tickets_root: Path) -> None:
    """Real subprocess launch, health check, teardown."""
    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=support_tickets_root,
        personas=None,
        db_policy="preserve",
    ) as conn:
        # AppConnection URLs come from runtime.json, not hardcoded
        assert conn.site_url.startswith("http://localhost:")
        assert conn.api_url.startswith("http://localhost:")

        # /docs is up
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{conn.api_url}/docs")
            assert resp.status_code == 200

    # Post-teardown: lock released
    lock = support_tickets_root / ".dazzle" / "mode_a.lock"
    assert not lock.exists()


@pytest.mark.asyncio
async def test_mode_a_concurrent_same_example_raises(
    support_tickets_root: Path,
) -> None:
    """Two concurrent runs against the same example → second raises."""

    async def _inner() -> None:
        async with ModeRunner(
            mode_spec=get_mode("a"),
            project_root=support_tickets_root,
            personas=None,
            db_policy="preserve",
        ) as conn:
            # Hold the lock briefly
            del conn
            await asyncio.sleep(2)

    task = asyncio.create_task(_inner())
    # Wait for the first runner to actually acquire the lock
    lock_path = support_tickets_root / ".dazzle" / "mode_a.lock"
    for _ in range(40):
        if lock_path.exists():
            break
        await asyncio.sleep(0.1)
    else:
        task.cancel()
        pytest.fail(
            f"first runner did not acquire {lock_path} within 4s — "
            "cannot verify concurrent-lock semantics"
        )

    # Second run should fail
    try:
        with pytest.raises(ModeAlreadyRunningError):
            async with ModeRunner(
                mode_spec=get_mode("a"),
                project_root=support_tickets_root,
                personas=None,
                db_policy="preserve",
            ):
                pass
    finally:
        # Let the first one finish
        await task


@pytest.mark.asyncio
async def test_mode_a_stale_lock_recovery(support_tickets_root: Path) -> None:
    """Stale lock (dead PID) is deleted automatically."""
    lock = support_tickets_root / ".dazzle" / "mode_a.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps(
            {
                "pid": 999999,  # Unlikely to be alive
                "mode": "a",
                "started_at": "2020-01-01T00:00:00Z",  # Very old
                "log_file": "/tmp/nope.log",
            }
        )
    )

    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=support_tickets_root,
        personas=None,
        db_policy="preserve",
    ):
        pass

    # Lock should have been replaced then released
    assert not lock.exists()
