"""/ux-cycle Strategy.EXPLORE wiring.

Invoked by the top-level ux_cycle runner when Step 6 (EXPLORE) fires.
The caller owns example-app lifecycle (typically via ``ModeRunner``) and
passes an already-running ``AppConnection``. This module boots Playwright,
optionally logs in as DSL personas, builds a ``ux_explore`` mission from
``dazzle.agent.missions.ux_explore``, runs the mission through
``DazzleAgent`` with native tool use enabled, and aggregates per-persona
proposals + edge-case findings into an ``ExploreOutcome``.

Requires ``DazzleAgent(use_tool_calls=True)`` to be functional — the legacy
text-action protocol will not reliably emit ``propose_component`` /
``record_edge_case`` payloads, as empirically confirmed in cycle 147.
The 2026-04-14 tool-use + robust-parser fix is a strict prerequisite.

This strategy does NOT own subprocess lifecycle. Caller responsibilities:
    async with ModeRunner(mode_spec=get_mode("a"), project_root=example_root,
                         personas=["admin"], db_policy="preserve") as conn:
        outcome = await run_explore_strategy(
            conn,
            example_root=example_root,
            strategy=Strategy.MISSING_CONTRACTS,
            personas=["admin"],
        )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dazzle.agent.core import DazzleAgent
from dazzle.agent.executor import PlaywrightExecutor
from dazzle.agent.missions.ux_explore import Strategy, build_ux_explore_mission
from dazzle.agent.observer import PlaywrightObserver
from dazzle.cli.runtime_impl.ux_cycle_impl._playwright_helpers import (
    PlaywrightBundle,
    login_as_persona,
    setup_playwright,
)
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir.personas import PersonaSpec
from dazzle.qa.server import AppConnection


@dataclass
class ExploreOutcome:
    """Aggregated outcome from one /ux-cycle EXPLORE run.

    ``proposals`` and ``findings`` are flat lists across all personas —
    each entry is augmented with a ``persona_id`` key so the caller can
    attribute results. ``blocked_personas`` holds ``(persona_id, reason)``
    tuples for any persona whose setup or agent run raised.

    ``degraded`` is True iff at least one persona was blocked OR the agent
    run did not reach ``completed`` outcome for at least one persona.
    """

    strategy: str
    summary: str
    degraded: bool
    proposals: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    blocked_personas: list[tuple[str | None, str]] = field(default_factory=list)
    steps_run: int = 0
    tokens_used: int = 0


@dataclass
class _PersonaRunResult:
    """Per-persona result inside ``run_explore_strategy``'s loop."""

    persona_id: str | None
    proposals: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    outcome: str  # "completed" | "max_steps" | "budget_exceeded" | "error" | "blocked"
    steps: int
    tokens: int
    error: str | None = None


def pick_explore_personas(
    app_spec: Any,
    override: list[str] | None = None,
) -> list[PersonaSpec]:
    """Pick persona(s) for an explore run.

    Auto-pick (override is None): return ALL personas whose
    default_workspace is not framework-scoped (i.e. doesn't start with
    an underscore), sorted alphabetically by id for determinism.
    Returns [] if no business personas exist.

    Override (list of ids): return those personas in caller order,
    looked up from app_spec.personas. Raises ValueError if any id is
    unknown — noisy failure is better than silently dropping a persona
    the caller explicitly requested.
    """
    by_id: dict[str, PersonaSpec] = {p.id: p for p in app_spec.personas}

    if override is not None:
        missing = [pid for pid in override if pid not in by_id]
        if missing:
            raise ValueError(
                f"persona '{missing[0]}' not found in app_spec.personas "
                f"(available: {sorted(by_id.keys())})"
            )
        return [by_id[pid] for pid in override]

    # Auto-pick: filter out framework-scoped personas
    business = [
        p
        for p in app_spec.personas
        if p.default_workspace is None or not p.default_workspace.startswith("_")
    ]
    business.sort(key=lambda p: p.id)
    return business


async def run_explore_strategy(
    connection: AppConnection,
    *,
    example_root: Path,
    strategy: Strategy,
    personas: list[str] | None = None,
    start_path: str = "/app",
) -> ExploreOutcome:
    """Run one EXPLORE cycle per persona and return the aggregated outcome.

    Caller owns example-app lifecycle (typically ``ModeRunner``). This
    function only runs the explore mission against an already-running
    example app reachable at ``connection.site_url``.

    Args:
        connection: Live ``AppConnection`` from a ``ModeRunner`` context.
        example_root: Path to the example app directory (e.g.
            ``examples/contact_manager``). Used to load the AppSpec so
            persona IDs can be resolved to full ``PersonaSpec`` objects
            for the mission prompt.
        strategy: ``Strategy.MISSING_CONTRACTS`` or ``Strategy.EDGE_CASES``.
        personas: List of persona IDs (e.g. ``["admin"]``). When None or
            empty, runs a single anonymous cycle (no login) using the
            bundle's original context and page — appropriate for public
            surfaces. Otherwise loops once per persona, each with a fresh
            browser context + magic-link login.
        start_path: Server-relative path to navigate to after login.
            Defaults to ``/app`` which is the canonical Dazzle app shell
            entry point. The mission's ``start_url`` is built by combining
            ``connection.site_url + start_path``.

    Returns:
        ``ExploreOutcome`` with flat proposals/findings across personas,
        aggregated summary, and a degraded flag.

    Raises:
        RuntimeError: if the Playwright bundle itself cannot start, or if
            all personas are blocked (no useful result to return).
    """
    app_spec = load_project_appspec(example_root)
    persona_lookup: dict[str, PersonaSpec] = {p.id: p for p in app_spec.personas}

    personas_to_run: list[str | None] = list(personas) if personas else [None]

    bundle: PlaywrightBundle | None = None
    results: list[_PersonaRunResult] = []

    try:
        bundle = await setup_playwright(base_url=connection.site_url)

        for persona_id in personas_to_run:
            persona_context: Any = None
            try:
                if persona_id is None:
                    persona_page = bundle.page
                    persona_label = "anonymous"
                else:
                    persona_context = await bundle.browser.new_context(base_url=connection.site_url)
                    persona_page = await persona_context.new_page()
                    await login_as_persona(
                        page=persona_page,
                        persona_id=persona_id,
                        api_url=connection.api_url,
                    )
                    persona_spec = persona_lookup.get(persona_id)
                    persona_label = persona_spec.label if persona_spec is not None else persona_id

                result = await _run_one_persona(
                    strategy=strategy,
                    persona_id=persona_id,
                    persona_label=persona_label,
                    page=persona_page,
                    base_url=connection.site_url,
                    start_path=start_path,
                    example_app=example_root.name,
                    persona_lookup=persona_lookup,
                )
                results.append(result)

            except Exception as e:  # noqa: BLE001 — recording the error is the point
                results.append(
                    _PersonaRunResult(
                        persona_id=persona_id,
                        proposals=[],
                        findings=[],
                        outcome="blocked",
                        steps=0,
                        tokens=0,
                        error=str(e),
                    )
                )
            finally:
                if persona_context is not None:
                    await persona_context.close()

    finally:
        if bundle is not None:
            await bundle.close()

    if not results or all(r.outcome == "blocked" for r in results):
        blocked_summary = "; ".join(
            f"{r.persona_id or 'anon'}: {r.error}" for r in results if r.error
        )
        raise RuntimeError(
            f"explore strategy: all personas blocked ({blocked_summary or 'no results'})"
        )

    return _aggregate(strategy=strategy, results=results)


async def _run_one_persona(
    *,
    strategy: Strategy,
    persona_id: str | None,
    persona_label: str,
    page: Any,
    base_url: str,
    start_path: str,
    example_app: str,
    persona_lookup: dict[str, PersonaSpec],
) -> _PersonaRunResult:
    """Run one explore mission for a single persona and collect tool outputs."""
    proposals: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    # The mission builder reads ``persona.label`` and ``persona.id`` for
    # prompt formatting. Use a real PersonaSpec where available so the
    # prompt gets a human-readable role name, otherwise fall back to a
    # lightweight shim exposing the same attributes.
    persona_obj: Any = persona_lookup.get(persona_id) if persona_id else None
    if persona_obj is None:
        persona_obj = _AnonymousPersona(id=persona_id or "anonymous", label=persona_label)

    mission = build_ux_explore_mission(
        strategy=strategy,
        persona=persona_obj,
        example_app=example_app,
        base_url=base_url.rstrip("/") + start_path,
        proposals=proposals,
        findings=findings,
    )

    agent = DazzleAgent(
        observer=PlaywrightObserver(page=page),
        executor=PlaywrightExecutor(page=page),
        use_tool_calls=True,
    )
    transcript = await agent.run(mission)

    # Tag each proposal/finding with which persona produced it so callers
    # can attribute results when aggregating across a multi-persona run.
    for p in proposals:
        p["persona_id"] = persona_id
    for f in findings:
        f["persona_id"] = persona_id

    return _PersonaRunResult(
        persona_id=persona_id,
        proposals=proposals,
        findings=findings,
        outcome=transcript.outcome,
        steps=len(transcript.steps),
        tokens=transcript.tokens_used,
    )


@dataclass(frozen=True)
class _AnonymousPersona:
    """Shim used when running an explore cycle without a DSL persona.

    Exposes the ``id`` + ``label`` attributes the explore mission prompt
    formatter reads (see ``ux_explore._build_missing_contracts_prompt``).
    """

    id: str
    label: str


def _aggregate(
    *,
    strategy: Strategy,
    results: list[_PersonaRunResult],
) -> ExploreOutcome:
    """Reduce per-persona ``_PersonaRunResult`` items to one ``ExploreOutcome``."""
    all_proposals: list[dict[str, Any]] = []
    all_findings: list[dict[str, Any]] = []
    blocked_personas: list[tuple[str | None, str]] = []
    total_steps = 0
    total_tokens = 0
    degraded = False

    for r in results:
        all_proposals.extend(r.proposals)
        all_findings.extend(r.findings)
        total_steps += r.steps
        total_tokens += r.tokens
        if r.outcome == "blocked":
            blocked_personas.append((r.persona_id, r.error or "unknown"))
            degraded = True
        elif r.outcome != "completed":
            # max_steps / budget_exceeded / error are all "didn't finish cleanly"
            degraded = True

    def _persona_count(r: _PersonaRunResult, kind: str) -> int:
        return len(r.proposals) if kind == "proposals" else len(r.findings)

    kind = "proposals" if strategy == Strategy.MISSING_CONTRACTS else "findings"
    per_persona = ", ".join(f"{r.persona_id or 'anon'}={_persona_count(r, kind)}" for r in results)
    total = len(all_proposals) if kind == "proposals" else len(all_findings)

    summary = (
        f"explore {strategy.value} [{len(results)} persona(s)]: "
        f"{total} {kind} total ({per_persona}), "
        f"steps={total_steps}, tokens={total_tokens}"
    )

    return ExploreOutcome(
        strategy=f"EXPLORE/{strategy.value}",
        summary=summary,
        degraded=degraded,
        proposals=all_proposals,
        findings=all_findings,
        blocked_personas=blocked_personas,
        steps_run=total_steps,
        tokens_used=total_tokens,
    )
