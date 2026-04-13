"""Task 20 — /ux-cycle Strategy.FITNESS integration test."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_fitness_strategy_calls_engine_run(tmp_path: Path) -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(
        return_value=MagicMock(
            findings=[],
            profile=MagicMock(degraded=False),
            independence_jaccard=0.4,
            run_metadata={"run_id": "r1"},
        )
    )

    with patch(
        "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
        return_value=fake_engine,
    ):
        outcome = await run_fitness_strategy(example_app="support_tickets", project_root=tmp_path)

    assert fake_engine.run.await_count == 1
    assert "r1" in outcome.summary
