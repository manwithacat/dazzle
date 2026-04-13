"""E2E: fitness engine runs against support_tickets example app.

Preconditions:
  1. ``support_tickets`` example has lifecycle applied (Ticket entity with
     status lifecycle + fitness.repr_fields).
  2. Dazzle runtime is available and ``DATABASE_URL`` is set.

Slow (spins up runtime, runs full engine) — marked ``e2e`` and skipped in
the default ``pytest tests/ -m "not e2e"`` run.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _require_database_url() -> None:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — required for PgSnapshotSource")


def _example_root() -> Path:
    dazzle_root = Path(__file__).parents[3]
    example_root = dazzle_root / "examples" / "support_tickets"
    if not example_root.exists():
        pytest.skip(f"missing example dir: {example_root}")
    return example_root


@pytest.mark.asyncio
async def test_support_tickets_fitness_cycle_completes() -> None:
    """A full fitness cycle against support_tickets returns a StrategyOutcome.

    Assertions are intentionally loose — the point is that the engine runs
    end-to-end without crashing. Coverage assertions live in unit tests.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )
    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner

    _require_database_url()
    example_root = _example_root()

    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=example_root,
        personas=None,
        db_policy="preserve",
    ) as conn:
        outcome = await run_fitness_strategy(
            conn,
            example_root=example_root,
        )

    assert outcome.strategy == "FITNESS"
    assert "fitness run" in outcome.summary
    # Engine must have written its log + backlog files.
    assert (example_root / "dev_docs" / "fitness-log.md").exists()
    assert (example_root / "dev_docs" / "fitness-backlog.md").exists()


@pytest.mark.asyncio
async def test_support_tickets_induced_regression_is_caught() -> None:
    """Self-validation: v1 success criterion #5 — regression comparator catches
    an intentionally-buggy correction.

    v1.0.3 work — requires the replay harness that does not yet exist.
    """
    pytest.skip("v1.0.3 — regression-comparator replay harness not yet implemented")


@pytest.mark.asyncio
async def test_support_tickets_multi_persona_cycle_completes() -> None:
    """Multi-persona fitness cycle against support_tickets returns an aggregated outcome.

    Assertions are intentionally loose — the point is that the multi-persona
    loop runs end-to-end without crashing.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )
    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner

    _require_database_url()
    example_root = _example_root()

    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=example_root,
        personas=["admin", "customer", "agent", "manager"],
        db_policy="preserve",
    ) as conn:
        outcome = await run_fitness_strategy(
            conn,
            example_root=example_root,
            personas=["admin", "customer", "agent", "manager"],
        )

    assert outcome.strategy == "FITNESS"
    # Multi-persona summary format is bracketed and contains all persona IDs
    assert "[" in outcome.summary
    assert "admin" in outcome.summary
    assert "customer" in outcome.summary
    assert "agent" in outcome.summary
    assert "manager" in outcome.summary
    # Engine must have written its log + backlog files
    assert (example_root / "dev_docs" / "fitness-log.md").exists()
    assert (example_root / "dev_docs" / "fitness-backlog.md").exists()


@pytest.mark.asyncio
async def test_support_tickets_baseline_restore_idempotent() -> None:
    """Mode A with db_policy=restore should cache the baseline between runs.

    First run lazy-builds the baseline file; second run restores from the
    cached file and should be measurably faster.
    """
    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner

    _require_database_url()
    example_root = _example_root()

    t1 = time.time()
    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=example_root,
        personas=None,
        db_policy="restore",
    ) as conn:
        assert conn.site_url.startswith("http://localhost:")
    first_duration = time.time() - t1

    t2 = time.time()
    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=example_root,
        personas=None,
        db_policy="restore",
    ) as conn:
        assert conn.site_url.startswith("http://localhost:")
    second_duration = time.time() - t2

    # Second run hits cached baseline; should be measurably faster.
    # Conservative multiplier: second run at least 2× faster than first.
    assert second_duration < first_duration / 2, (
        f"Baseline cache ineffective: first={first_duration:.1f}s second={second_duration:.1f}s"
    )
