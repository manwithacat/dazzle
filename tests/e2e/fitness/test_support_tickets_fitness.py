"""E2E: fitness engine runs against support_tickets example app.

Preconditions:
  1. `support_tickets` example has lifecycle ADR applied (Ticket entity with
     status lifecycle + fitness.repr_fields).
  2. Dazzle runtime is available.

This test is slow (spins up runtime, runs full engine). It is marked `e2e`
and skipped in the default `pytest tests/ -m "not e2e"` run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_support_tickets_fitness_cycle_completes() -> None:
    # Construct real engine dependencies via RuntimeServices.
    # The engine must:
    #  - Run at least one Pass 1 story walk (support_tickets has several)
    #  - Produce a FitnessDiff whose row counts are non-negative
    #  - Emit at least zero findings (may be zero on a perfectly-spec'd app)
    #  - Write fitness-backlog.md and fitness-log.md to the project dev_docs/
    #  - Complete in under 10 minutes
    from dazzle.fitness.config import FitnessConfig  # noqa: F401
    from dazzle.fitness.engine import FitnessEngine  # noqa: F401

    example_root = Path(__file__).parents[3] / "examples" / "support_tickets"
    assert example_root.exists(), f"missing example dir: {example_root}"

    # Skeleton wiring — Task 0 discovery determines the real RuntimeServices
    # call. The implementing agent must fill this in based on what exists in
    # the codebase, following the same pattern used by `dazzle ux verify`.
    pytest.skip("E2E wiring pending — requires RuntimeServices handle from Task 0")


@pytest.mark.asyncio
async def test_support_tickets_induced_regression_is_caught() -> None:
    """Self-validation: an intentionally broken correction must be caught
    by the regression comparator on the next cycle.

    v1 success criterion #5: at least one intentionally-buggy correction
    is caught by the regression comparator.
    """
    pytest.skip("E2E self-validation pending — requires full engine wiring")
