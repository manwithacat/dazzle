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

import json
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
    personas: list[str] | None = None,
) -> StrategyOutcome:
    """Run one fitness cycle per persona and return an aggregated outcome.

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
    example_root = _resolve_example_root(example_app=example_app, project_root=project_root)
    handle = await _launch_example_app(example_root=example_root)
    bundle: Any = None
    outcomes: list[tuple[str | None, Any]] = []
    try:
        bundle = await _setup_playwright(base_url=handle.site_url)

        personas_to_run: list[str | None] = list(personas) if personas else [None]

        for persona_id in personas_to_run:
            persona_context: Any = None
            persona_page: Any
            close_context_after: bool = False

            try:
                if persona_id is None:
                    # Anonymous — reuse the bundle's original context/page
                    persona_page = bundle.page
                else:
                    # Named persona — fresh context, login, then continue
                    persona_context = await bundle.browser.new_context(base_url=handle.site_url)
                    persona_page = await persona_context.new_page()
                    close_context_after = True
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
                    example_root=example_root,
                    handle=handle,
                    bundle=persona_bundle,
                    component_contract_path=component_contract_path,
                )
                result = await engine.run()
                outcomes.append((persona_id, result))

            except Exception as e:  # noqa: BLE001 — recording the error is the point
                outcomes.append((persona_id, _BlockedRunResult(error=str(e))))
            finally:
                if close_context_after and persona_context is not None:
                    await persona_context.close()

    finally:
        if bundle is not None:
            await bundle.close()
        _stop_example_app(handle)

    return _aggregate_outcomes(outcomes)


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


async def _login_as_persona(page: Any, persona_id: str, api_url: str) -> None:
    """Log a Playwright page in as a DSL persona via QA mode's magic-link flow.

    Two-step flow from issue #768:
        1. ``POST {api_url}/qa/magic-link`` with ``{"persona_id": persona_id}`` —
           gated by DAZZLE_ENV=development + DAZZLE_QA_MODE=1 on the example
           subprocess. Returns a single-use token.
        2. ``GET {api_url}/auth/magic/{token}?next=/`` — validates token,
           creates session cookie, redirects to ``next``.

    Raises:
        RuntimeError: if any step fails. Distinguishing messages let the
            strategy loop record BLOCKED outcomes with useful context:
            - "magic-link endpoint returned 404" (404 on generator — QA flags
              missing OR persona not provisioned; see qa_routes.py:59,65)
            - "magic-link generation failed: HTTP {status}" (other non-2xx)
            - "persona login rejected: magic-link consumer did not create a session"
              (final page path is /auth/login or /login — path-exact check)
    """
    generator_url = f"{api_url}/qa/magic-link"
    response = await page.request.post(
        generator_url,
        data=json.dumps({"persona_id": persona_id}),
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        if response.status == 404:
            # 404 covers two distinct cases per qa_routes.py:
            #  (a) QA mode env flags not set (DAZZLE_ENV + DAZZLE_QA_MODE)
            #  (b) persona email not provisioned in the auth store
            raise RuntimeError(
                f"magic-link endpoint returned 404 for persona {persona_id!r} at "
                f"{generator_url} — check DAZZLE_ENV=development + DAZZLE_QA_MODE=1, "
                f"or that the persona is provisioned"
            )
        raise RuntimeError(
            f"magic-link generation failed: HTTP {response.status} at {generator_url}"
        )

    magic_link_payload = await response.json()
    # The QA endpoint (dazzle_back/runtime/qa_routes.py:79) returns
    # MagicLinkResponse(url=f"/auth/magic/{token}") — a server-relative path.
    magic_link_path = magic_link_payload["url"]

    consumer_url = f"{api_url}{magic_link_path}?next=/"
    await page.goto(consumer_url)

    # Detect token rejection: consumer redirects to /auth/login (or /login) on failure.
    # Use path-exact match to avoid false positives on unrelated routes that
    # happen to contain "login" (e.g. /app/logins, /admin/login-history).
    from urllib.parse import urlparse

    final_path = urlparse(page.url).path
    if final_path in ("/auth/login", "/login"):
        raise RuntimeError(
            f"persona login rejected: magic-link consumer did not create a session "
            f"for persona {persona_id!r} (final URL: {page.url})"
        )


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
    return _EngineProxy(engine=engine)
