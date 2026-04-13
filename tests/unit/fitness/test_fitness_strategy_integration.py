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
            new=AsyncMock(return_value=fake_engine),
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
            new=AsyncMock(return_value=fake_engine),
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


@pytest.mark.asyncio
async def test_launch_example_app_stops_handle_on_wait_exception(tmp_path: Path) -> None:
    """If wait_for_ready raises, the handle must be torn down before the exception propagates."""
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
            new=AsyncMock(side_effect=OSError("connection refused")),
        ),
        pytest.raises(OSError, match="connection refused"),
    ):
        await fitness_strategy._launch_example_app(example_root=example_root)

    fake_handle.stop.assert_called_once()


def test_stop_example_app_calls_handle_stop() -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    handle = MagicMock()
    fitness_strategy._stop_example_app(handle)
    handle.stop.assert_called_once()


@pytest.mark.asyncio
async def test_build_engine_wires_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_build_engine` assembles AppSpec + FitnessConfig + agent + snapshot source + LLM."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")

    fake_app_spec = MagicMock(entities=[], stories=[], personas=[])
    fake_config = MagicMock()
    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(
        return_value=MagicMock(
            findings=[],
            profile=MagicMock(degraded=False),
            independence_jaccard=0.0,
            run_metadata={"run_id": "r1"},
        )
    )

    # Playwright bundle: patch the setup helper so no real browser spawns.
    fake_bundle = MagicMock()
    fake_bundle.page = MagicMock()
    fake_bundle.close = AsyncMock()

    async def _fake_setup(base_url: str):
        return fake_bundle

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_project_appspec",
            return_value=fake_app_spec,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_fitness_config",
            return_value=fake_config,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.PostgresBackend"
        ) as mock_backend,
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.LLMAPIClient") as mock_llm,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._setup_playwright",
            new=_fake_setup,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.FitnessEngine",
            return_value=fake_engine,
        ) as mock_engine_cls,
    ):
        handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
        proxy = await fitness_strategy._build_engine(example_root=example_root, handle=handle)
        # Drive the proxy's run() to verify Playwright teardown fires.
        await proxy.run()

    mock_backend.assert_called_once_with(database_url="postgresql://stub")
    mock_llm.assert_called_once_with()
    mock_engine_cls.assert_called_once()
    fake_engine.run.assert_awaited_once()
    fake_bundle.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_engine_raises_when_database_url_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        await fitness_strategy._build_engine(
            example_root=example_root,
            handle=MagicMock(site_url="http://x", api_url="http://y"),
        )


@pytest.mark.asyncio
async def test_engine_proxy_tears_down_playwright_on_engine_failure() -> None:
    """_EngineProxy.run() must close the Playwright bundle even when engine.run() raises."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import _EngineProxy

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(side_effect=RuntimeError("engine exploded"))
    fake_bundle = MagicMock()
    fake_bundle.close = AsyncMock()

    proxy = _EngineProxy(engine=fake_engine, bundle=fake_bundle)

    with pytest.raises(RuntimeError, match="engine exploded"):
        await proxy.run()

    fake_bundle.close.assert_awaited_once()
