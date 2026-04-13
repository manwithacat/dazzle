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
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_support_tickets_fitness_cycle_completes() -> None:
    """A full fitness cycle against support_tickets returns a StrategyOutcome.

    Assertions are intentionally loose — the point is that the engine runs
    end-to-end without crashing. Coverage assertions live in unit tests.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — required for PgSnapshotSource")

    dazzle_root = Path(__file__).parents[3]
    example_root = dazzle_root / "examples" / "support_tickets"
    assert example_root.exists(), f"missing example dir: {example_root}"

    outcome = await run_fitness_strategy(
        example_app="support_tickets",
        project_root=dazzle_root,
    )

    assert outcome.strategy == "FITNESS"
    assert "fitness run" in outcome.summary
    assert outcome.findings_count >= 0
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
