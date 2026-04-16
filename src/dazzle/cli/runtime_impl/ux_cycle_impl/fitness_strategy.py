"""/ux-cycle Strategy.FITNESS wiring.

Invoked by the top-level ux_cycle runner when it rotates to FITNESS. The
caller (typically ``dazzle.e2e.runner.ModeRunner``) owns example-app lifecycle
and passes an already-running ``AppConnection``. This module runs the fitness
engine and aggregates the result into a /ux-cycle outcome.
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
from dazzle.cli.runtime_impl.ux_cycle_impl._playwright_helpers import (
    PlaywrightBundle as _PlaywrightBundle,
)
from dazzle.cli.runtime_impl.ux_cycle_impl._playwright_helpers import (
    login_as_persona as _login_as_persona,
)
from dazzle.cli.runtime_impl.ux_cycle_impl._playwright_helpers import (
    setup_playwright as _setup_playwright,
)
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.fitness.config import load_fitness_config
from dazzle.fitness.engine import FitnessEngine
from dazzle.fitness.pg_snapshot_source import PgSnapshotSource
from dazzle.llm.api_client import LLMAPIClient
from dazzle.qa.server import AppConnection
from dazzle_back.runtime.pg_backend import PostgresBackend


@dataclass
class StrategyOutcome:
    """Aggregated outcome from one /ux-cycle strategy run."""

    strategy: str
    summary: str
    degraded: bool
    findings_count: int


async def run_fitness_strategy(
    connection: AppConnection,
    *,
    app_root: Path,
    component_contract_path: Path | None = None,
    personas: list[str] | None = None,
) -> StrategyOutcome:
    """Run one fitness cycle per persona and return an aggregated outcome.

    The caller is responsible for launching + tearing down the subprocess —
    typically via ``dazzle.e2e.runner.ModeRunner``. This function only runs
    the fitness engine against an already-running example app reachable at
    ``connection.site_url``.

    When ``personas`` is None, runs a single anonymous cycle (v1.0.2
    behavior) using the Playwright bundle's original context and page.

    When ``personas`` is a non-empty list, loops once per persona:
        1. Create a fresh ``browser.new_context()`` for cookie isolation.
        2. Call ``_login_as_persona`` to authenticate via the QA mode
           magic-link flow (#768).
        3. Build a per-persona ``FitnessEngine`` via ``_build_engine``
           (which navigates to the contract anchor if one is present).
        4. Run the engine. Record outcome or BLOCKED stand-in on failure.
        5. Close the fresh context.

    Per-persona failures are recorded as BLOCKED outcomes but do not abort
    the loop — other personas continue to run. The strategy owns bundle
    teardown in the outer finally so the shared browser is always released.
    """
    handle = connection  # local alias — rest of the function already uses `handle`
    bundle: Any = None
    outcomes: list[tuple[str | None, Any]] = []
    try:
        bundle = await _setup_playwright(base_url=handle.site_url)

        personas_to_run: list[str | None] = list(personas) if personas else [None]

        for persona_id in personas_to_run:
            persona_context: Any = None
            persona_page: Any

            try:
                if persona_id is None:
                    # Anonymous — reuse the bundle's original context/page
                    persona_page = bundle.page
                else:
                    # Named persona — fresh context, login, then continue
                    persona_context = await bundle.browser.new_context(base_url=handle.site_url)
                    persona_page = await persona_context.new_page()
                    await _login_as_persona(
                        page=persona_page,
                        persona_id=persona_id,
                        api_url=handle.api_url,
                    )

                # Build a persona-local bundle view so _build_engine uses the
                # right page. We reuse the bundle dataclass but with the
                # per-persona context/page swapped in.
                persona_bundle = _PlaywrightBundle(
                    playwright=bundle.playwright,
                    browser=bundle.browser,
                    context=persona_context or bundle.context,
                    page=persona_page,
                )

                engine = await _build_engine(
                    app_root=app_root,
                    handle=handle,
                    bundle=persona_bundle,
                    component_contract_path=component_contract_path,
                )
                result = await engine.run()
                outcomes.append((persona_id, result))

            except Exception as e:  # noqa: BLE001 — recording the error is the point
                outcomes.append((persona_id, _BlockedRunResult(error=str(e))))
            finally:
                # persona_context is None for the anonymous case (bundle.context is
                # owned by the outer bundle.close()) and non-None when we created
                # a fresh context for a named persona — close those even if new_page
                # or _login_as_persona raised before the engine ran.
                if persona_context is not None:
                    await persona_context.close()

    finally:
        if bundle is not None:
            await bundle.close()
        # handle teardown is the caller's responsibility (typically ModeRunner)

    return _aggregate_outcomes(outcomes)


@dataclass
class _BlockedProfile:
    """Stand-in profile for a blocked run — always degraded."""

    degraded: bool = True


@dataclass
class _BlockedRunResult:
    """Stand-in result for a persona whose engine construction or run raised.

    Shaped to match the subset of FitnessRunResult fields that
    _aggregate_outcomes reads, so the aggregator does not need to distinguish
    blocked from normal results.
    """

    error: str

    @property
    def findings(self) -> list[Any]:
        return []

    @property
    def profile(self) -> Any:
        return _BlockedProfile()

    @property
    def independence_jaccard(self) -> float:
        return 0.0

    @property
    def run_metadata(self) -> dict[str, Any]:
        return {"run_id": "blocked", "error": self.error}


def _aggregate_outcomes(outcomes: list[tuple[str | None, Any]]) -> StrategyOutcome:
    """Reduce a list of (persona_id, FitnessRunResult) pairs to one StrategyOutcome.

    Single-persona format (len(outcomes) == 1):
        "fitness run r1: N findings, independence=X.XXX"

    Multi-persona format:
        "fitness run [admin:r_admin, editor:r_editor]: N findings total "
        "(admin=a, editor=e), independence=Y.YYY (max)"

    ``degraded`` is OR-reduced. ``findings_count`` is summed.
    """
    if not outcomes:
        return StrategyOutcome(
            strategy="FITNESS",
            summary="fitness run: no personas ran",
            degraded=True,
            findings_count=0,
        )

    total_findings = sum(len(result.findings) for _, result in outcomes)
    any_degraded = any(result.profile.degraded for _, result in outcomes)

    if len(outcomes) == 1:
        _, result = outcomes[0]
        summary = (
            f"fitness run {result.run_metadata.get('run_id')}: "
            f"{len(result.findings)} findings, "
            f"independence={result.independence_jaccard:.3f}"
        )
    else:
        run_ids = ", ".join(
            f"{persona or 'anon'}:{result.run_metadata.get('run_id')}"
            for persona, result in outcomes
        )
        per_persona_counts = ", ".join(
            f"{persona or 'anon'}={len(result.findings)}" for persona, result in outcomes
        )
        max_independence = max(result.independence_jaccard for _, result in outcomes)
        summary = (
            f"fitness run [{run_ids}]: "
            f"{total_findings} findings total ({per_persona_counts}), "
            f"independence={max_independence:.3f} (max)"
        )

    return StrategyOutcome(
        strategy="FITNESS",
        summary=summary,
        degraded=any_degraded,
        findings_count=total_findings,
    )


class _EngineProxy:
    """Wraps a ``FitnessEngine`` so the strategy can pass around a uniform run() surface.

    v1.0.2 owned bundle teardown inside the proxy. v1.0.3 moves that
    responsibility up to the strategy so multi-persona runs can share the
    same browser across iterations. The proxy now just forwards run().
    """

    def __init__(self, engine: Any) -> None:
        self._engine = engine

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
    app_root: Path,
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

    app_spec = load_project_appspec(app_root)
    config = load_fitness_config(app_root)

    backend = PostgresBackend(database_url=database_url)
    snapshot_source = PgSnapshotSource(backend)
    llm = LLMAPIClient()

    # Parse the contract once so we can (a) pass the path to the engine and
    # (b) navigate to the anchor URL before the walker snapshots the page.
    contract: ComponentContract | None = None
    if component_contract_path is not None:
        contract = parse_component_contract(component_contract_path)
        if contract.anchor is not None:
            # Normalize leading slash — contract authors may write `anchor: login`
            # or `anchor: /login`; both must produce a well-formed URL.
            anchor_path = (
                contract.anchor if contract.anchor.startswith("/") else f"/{contract.anchor}"
            )
            await bundle.page.goto(handle.site_url + anchor_path)

    agent = DazzleAgent(
        observer=PlaywrightObserver(page=bundle.page),
        executor=PlaywrightExecutor(page=bundle.page),
    )

    contract_paths: list[Path] = [component_contract_path] if component_contract_path else []
    contract_observer = _ContractObserver(page=bundle.page) if component_contract_path else None

    engine = FitnessEngine(
        project_root=app_root,
        config=config,
        app_spec=app_spec,
        spec_md_path=app_root / "SPEC.md",
        agent=agent,
        executor=PlaywrightExecutor(page=bundle.page),
        snapshot_source=snapshot_source,
        llm=llm,
        contract_paths=contract_paths,
        contract_observer=contract_observer,
    )
    return _EngineProxy(engine=engine)
