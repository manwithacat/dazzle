"""/ux-cycle Strategy.FITNESS wiring.

Invoked by the top-level ux_cycle runner when it rotates to FITNESS. Owns
example-app lifecycle (starts runtime, runs the engine, tears down) and
aggregates the result into a /ux-cycle outcome.

v1.0.1 wires the real dependencies across three tasks: ``_launch_example_app``
spins up the example via ``dazzle.qa.server`` (Task 3), ``_build_engine``
loads the example's ``AppSpec`` + ``FitnessConfig`` and constructs a
Playwright-backed ``FitnessEngine`` (Task 4), and ``_stop_example_app`` tears
down the subprocess (Task 3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dazzle.agent.core import DazzleAgent
from dazzle.agent.executor import PlaywrightExecutor
from dazzle.agent.observer import PlaywrightObserver
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.fitness.config import load_fitness_config
from dazzle.fitness.engine import FitnessEngine
from dazzle.fitness.pg_snapshot_source import PgSnapshotSource
from dazzle.llm.api_client import LLMAPIClient
from dazzle.qa.server import AppConnection, connect_app, wait_for_ready
from dazzle_back.runtime.pg_backend import PostgresBackend


@dataclass
class StrategyOutcome:
    """Aggregated outcome from one /ux-cycle strategy run."""

    strategy: str
    summary: str
    degraded: bool
    findings_count: int


async def run_fitness_strategy(example_app: str, project_root: Path) -> StrategyOutcome:
    """Run one fitness cycle against ``example_app`` and return a summary.

    Owns the example-app subprocess lifecycle via try/finally, so teardown
    runs even if the engine raises.
    """
    example_root = _resolve_example_root(example_app=example_app, project_root=project_root)
    handle = await _launch_example_app(example_root=example_root)
    try:
        engine = await _build_engine(example_root=example_root, handle=handle)
        result = await engine.run()
    finally:
        _stop_example_app(handle)

    summary = (
        f"fitness run {result.run_metadata.get('run_id')}: "
        f"{len(result.findings)} findings, "
        f"independence={result.independence_jaccard:.3f}"
    )
    return StrategyOutcome(
        strategy="FITNESS",
        summary=summary,
        degraded=result.profile.degraded,
        findings_count=len(result.findings),
    )


def _resolve_example_root(example_app: str, project_root: Path) -> Path:
    """Resolve ``examples/<example_app>`` relative to the Dazzle repo root."""
    return project_root / "examples" / example_app


async def _launch_example_app(example_root: Path) -> AppConnection:
    """Launch the example app subprocess and wait for the API to become ready.

    Raises:
        RuntimeError: if the API does not respond within the readiness timeout.
    """
    handle: AppConnection = connect_app(project_dir=example_root)
    try:
        ready = await wait_for_ready(handle.api_url, timeout=120.0)
    except Exception:
        handle.stop()
        raise

    if not ready:
        handle.stop()
        raise RuntimeError(f"example app at {handle.api_url} did not become ready within 120s")
    return handle


def _stop_example_app(handle: AppConnection) -> None:
    """Terminate the example-app subprocess owned by ``handle`` (no-op if external)."""
    handle.stop()


@dataclass
class _PlaywrightBundle:
    """Playwright resources owned by the strategy for one fitness cycle."""

    playwright: Any
    browser: Any
    context: Any
    page: Any

    async def close(self) -> None:
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()


async def _setup_playwright(base_url: str) -> _PlaywrightBundle:
    """Spin up a headless Chromium page pointed at ``base_url``.

    Separate from ``_build_engine`` so tests can patch it cleanly.
    """
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(base_url=base_url)
    page = await context.new_page()
    return _PlaywrightBundle(playwright=pw, browser=browser, context=context, page=page)


class _EngineProxy:
    """Wraps a ``FitnessEngine`` so ``run()`` also tears down Playwright."""

    def __init__(self, engine: Any, bundle: Any) -> None:
        self._engine = engine
        self._bundle = bundle

    async def run(self) -> Any:
        try:
            return await self._engine.run()
        finally:
            await self._bundle.close()


async def _build_engine(example_root: Path, handle: Any) -> Any:
    """Construct a ``FitnessEngine`` for the given example app.

    Reads ``DATABASE_URL`` from env to wire the snapshot source. Returns an
    ``_EngineProxy`` whose ``run()`` tears down the Playwright bundle when
    the engine finishes.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "fitness_strategy._build_engine: DATABASE_URL env var must be set "
            "so PgSnapshotSource can read the example app's database"
        )

    app_spec = load_project_appspec(example_root)
    config = load_fitness_config(example_root)

    backend = PostgresBackend(database_url=database_url)
    snapshot_source = PgSnapshotSource(backend)
    llm = LLMAPIClient()

    bundle = await _setup_playwright(base_url=handle.site_url)

    agent = DazzleAgent(
        observer=PlaywrightObserver(page=bundle.page),
        executor=PlaywrightExecutor(page=bundle.page),
    )

    engine = FitnessEngine(
        project_root=example_root,
        config=config,
        app_spec=app_spec,
        spec_md_path=example_root / "SPEC.md",
        agent=agent,
        executor=PlaywrightExecutor(page=bundle.page),
        snapshot_source=snapshot_source,
        llm=llm,
    )
    return _EngineProxy(engine=engine, bundle=bundle)
