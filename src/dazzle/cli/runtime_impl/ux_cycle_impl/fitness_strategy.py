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
from typing import Any, cast

from dazzle.agent.core import DazzleAgent
from dazzle.agent.executor import PlaywrightExecutor
from dazzle.agent.missions._shared import ComponentContract, parse_component_contract
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


async def run_fitness_strategy(
    example_app: str,
    project_root: Path,
    component_contract_path: Path | None = None,
) -> StrategyOutcome:
    """Run one fitness cycle against ``example_app`` and return a summary.

    Owns the example-app subprocess lifecycle via try/finally, so teardown
    runs even if the engine raises. Also owns the Playwright bundle lifecycle
    in v1.0.3+ — the browser is launched once and torn down in the outer
    finally, regardless of how many personas run against it.
    """
    example_root = _resolve_example_root(example_app=example_app, project_root=project_root)
    handle = await _launch_example_app(example_root=example_root)
    bundle: Any = None
    try:
        bundle = await _setup_playwright(base_url=handle.site_url)
        engine = await _build_engine(
            example_root=example_root,
            handle=handle,
            bundle=bundle,
            component_contract_path=component_contract_path,
        )
        result = await engine.run()
    finally:
        if bundle is not None:
            await bundle.close()
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
    """Wraps a ``FitnessEngine`` so the strategy can pass around a uniform run() surface.

    v1.0.2 owned bundle teardown inside the proxy. v1.0.3 moves that
    responsibility up to the strategy so multi-persona runs can share the
    same browser across iterations. The proxy now just forwards run().
    """

    def __init__(self, engine: Any, bundle: Any) -> None:
        self._engine = engine
        self._bundle = bundle

    async def run(self) -> Any:
        return await self._engine.run()


class _ContractObserver:
    """Adapts a Playwright page to the fitness contract walker's _ObserverLike protocol.

    v1.0.2 observes whatever the page currently shows (no navigation). A
    future version will navigate to a contract-declared anchor URL.
    """

    def __init__(self, page: Any) -> None:
        self._page = page

    async def snapshot(self) -> str:
        return cast(str, await self._page.content())


async def _build_engine(
    example_root: Path,
    handle: Any,
    bundle: Any,
    component_contract_path: Path | None = None,
) -> Any:
    """Construct a ``FitnessEngine`` for the given example app.

    Reads ``DATABASE_URL`` from env to wire the snapshot source. Takes a
    pre-built Playwright ``bundle`` — the caller owns bundle lifecycle.
    If ``component_contract_path`` points at a contract with a ``## Anchor``
    section, navigates ``bundle.page`` to ``handle.site_url + anchor`` before
    building the engine, so the contract walker observes the right component.
    Returns an ``_EngineProxy`` whose ``run()`` forwards to the wrapped
    engine; the proxy no longer owns bundle teardown (the strategy does).
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

    # Parse the contract once so we can (a) pass the path to the engine and
    # (b) navigate to the anchor URL before the walker snapshots the page.
    contract: ComponentContract | None = None
    if component_contract_path is not None:
        contract = parse_component_contract(component_contract_path)
        if contract.anchor is not None:
            await bundle.page.goto(handle.site_url + contract.anchor)

    agent = DazzleAgent(
        observer=PlaywrightObserver(page=bundle.page),
        executor=PlaywrightExecutor(page=bundle.page),
    )

    contract_paths: list[Path] = [component_contract_path] if component_contract_path else []
    contract_observer = _ContractObserver(page=bundle.page) if component_contract_path else None

    engine = FitnessEngine(
        project_root=example_root,
        config=config,
        app_spec=app_spec,
        spec_md_path=example_root / "SPEC.md",
        agent=agent,
        executor=PlaywrightExecutor(page=bundle.page),
        snapshot_source=snapshot_source,
        llm=llm,
        contract_paths=contract_paths,
        contract_observer=contract_observer,
    )
    return _EngineProxy(engine=engine, bundle=bundle)
