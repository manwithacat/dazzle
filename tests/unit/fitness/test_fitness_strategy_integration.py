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
    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ) as mock_launch,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"
        ) as mock_stop,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            return_value=fake_engine,
        ) as mock_build,
    ):
        outcome = await run_fitness_strategy(example_app="support_tickets", project_root=tmp_path)

    assert fake_engine.run.await_count == 1
    assert "r1" in outcome.summary
    assert mock_launch.call_count == 1
    mock_stop.assert_called_once_with(fake_handle)
    assert mock_build.call_count == 1


@pytest.mark.asyncio
async def test_fitness_strategy_stops_app_on_engine_failure(tmp_path: Path) -> None:
    """Lifecycle teardown must run even when the engine raises."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(side_effect=RuntimeError("boom"))
    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"
        ) as mock_stop,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            return_value=fake_engine,
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await run_fitness_strategy(example_app="support_tickets", project_root=tmp_path)

    mock_stop.assert_called_once_with(fake_handle)


@pytest.mark.asyncio
async def test_launch_example_app_uses_qa_server(tmp_path: Path) -> None:
    """`_launch_example_app` delegates to dazzle.qa.server.connect_app and waits for ready."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.connect_app",
            return_value=fake_handle,
        ) as mock_connect,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.wait_for_ready",
            new=AsyncMock(return_value=True),
        ) as mock_wait,
    ):
        result = await fitness_strategy._launch_example_app(example_root=example_root)

    assert result is fake_handle
    mock_connect.assert_called_once_with(project_dir=example_root)
    mock_wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_launch_example_app_raises_on_health_timeout(tmp_path: Path) -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.connect_app",
            return_value=fake_handle,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.wait_for_ready",
            new=AsyncMock(return_value=False),
        ),
        pytest.raises(RuntimeError, match="did not become ready"),
    ):
        await fitness_strategy._launch_example_app(example_root=example_root)

    # Teardown must fire even on failed launch.
    fake_handle.stop.assert_called_once()


def test_stop_example_app_calls_handle_stop() -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    handle = MagicMock()
    fitness_strategy._stop_example_app(handle)
    handle.stop.assert_called_once()
