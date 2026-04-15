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

import logging
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
from dazzle_ui.converters.workspace_converter import compute_persona_default_routes

logger = logging.getLogger(__name__)


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
    # Cycle 197 — pre-dedup counts per persona, for logging and cross-persona analysis
    raw_proposals_by_persona: dict[str, int] = field(default_factory=dict)
    # Cycle 198 spike — per-persona diagnostic detail for runs that completed
    # (didn't raise) but produced a non-"completed" transcript. Distinct from
    # blocked_personas, which holds only personas whose setup/run raised.
    # Each entry: {"persona_id": str|None, "outcome": str, "error": str|None,
    # "steps": int, "tokens": int}.
    per_persona_results: list[dict[str, Any]] = field(default_factory=list)


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


def _dedup_proposals(raw_proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge proposals with the same (example_app, component_name) key.

    First-seen ordering is preserved. Each merged entry gains a
    'contributing_personas' field listing every persona_id that proposed
    the same component. Comparison on component_name is case-insensitive
    to catch trivial casing variation from LLM output.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []

    for p in raw_proposals:
        key = (p.get("example_app", ""), p.get("component_name", "").lower())
        persona_id = p.get("persona_id")
        if key not in merged:
            entry = dict(p)  # shallow copy
            entry["contributing_personas"] = [persona_id] if persona_id else []
            merged[key] = entry
            order.append(key)
        else:
            if persona_id and persona_id not in merged[key]["contributing_personas"]:
                merged[key]["contributing_personas"].append(persona_id)

    return [merged[k] for k in order]


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


def pick_start_path(persona_spec: PersonaSpec, app_spec: Any) -> str:
    """Compute the start URL path for exploring as persona_spec.

    Delegates to compute_persona_default_routes for the full 5-step
    resolution chain (default_route → default_workspace → persona-access
    workspace → AUTHENTICATED workspace → first workspace). Falls back
    to '/app' if the helper returns no route (pathological DSL with no
    workspaces).
    """
    routes = compute_persona_default_routes(
        personas=[persona_spec],
        workspaces=app_spec.workspaces,
    )
    return routes.get(persona_spec.id) or "/app"


async def run_explore_strategy(
    connection: AppConnection,
    *,
    example_root: Path,
    strategy: Strategy,
    personas: list[str] | None = None,
    start_path: str | None = None,
    mcp_session: Any = None,
    use_tool_calls: bool = True,
) -> ExploreOutcome:
    """Run one EXPLORE cycle per persona and return the aggregated outcome.

    ``personas`` semantics (cycle 197 change):
        None       → auto-pick business personas from the DSL
        []         → anonymous (no login, single run)
        ["admin"]  → explicit override, single persona
        ["a","b"]  → explicit multi-persona fan-out

    ``start_path`` overrides the per-persona computed start path for
    all runs. Defaults to None (each persona uses its DSL default).

    Cycle 198 spike — Path γ support:

    ``mcp_session`` — when non-None, ``DazzleAgent`` routes ``_decide``
    through MCP sampling (Path γ in the Apr 14 spec), subsidised by the
    Claude Code host subscription instead of the metered Anthropic SDK.
    Caller must have an MCP session in scope (e.g. an MCP tool handler
    passing its ``progress_ctx.session``).

    ``use_tool_calls`` — when False (required on Path γ, since MCP
    sampling is text-only), DazzleAgent uses the text protocol with the
    robust parser from cycle 195's first fix. Builtin page actions
    (navigate/click/type/...) come through as text JSON and are handled
    by ``_parse_action``. Flat-schema mission tools like
    ``propose_component`` work fine on this path. This trades the
    cycle 195 second fix (builtin-action-as-tool) for subsidised
    cognition, which is the right trade when an MCP session is
    available.
    """
    app_spec = load_project_appspec(example_root)

    # Persona resolution
    if personas is None:
        # Auto-pick business personas
        persona_specs = pick_explore_personas(app_spec)
        personas_to_run: list[str | None] = (
            [p.id for p in persona_specs] if persona_specs else [None]
        )
        if not persona_specs:
            logger.warning(
                "explore: no business personas found in %s; running anonymously",
                example_root.name,
            )
    elif personas == []:
        # Anonymous escape hatch
        persona_specs = []
        personas_to_run = [None]
    else:
        # Explicit override — resolve and validate
        persona_specs = pick_explore_personas(app_spec, override=personas)
        personas_to_run = [p.id for p in persona_specs]

    persona_lookup: dict[str, PersonaSpec] = {p.id: p for p in app_spec.personas}

    # Resolve start paths per persona if the caller didn't override
    persona_start_paths: dict[str | None, str] = {}
    for pid in personas_to_run:
        if start_path is not None:
            persona_start_paths[pid] = start_path
        elif pid is None:
            persona_start_paths[pid] = "/app"
        else:
            ps = persona_lookup.get(pid)
            persona_start_paths[pid] = pick_start_path(ps, app_spec) if ps is not None else "/app"

    logger.info(
        "[explore] %s: running %d persona(s): %s",
        example_root.name,
        len(personas_to_run),
        [p or "anonymous" for p in personas_to_run],
    )

    bundle: PlaywrightBundle | None = None
    results: list[_PersonaRunResult] = []
    raw_by_persona: dict[str, int] = {}

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
                    ps = persona_lookup.get(persona_id)
                    persona_label = ps.label if ps is not None else persona_id

                result = await _run_one_persona(
                    strategy=strategy,
                    persona_id=persona_id,
                    persona_label=persona_label,
                    page=persona_page,
                    base_url=connection.site_url,
                    start_path=persona_start_paths[persona_id],
                    example_app=example_root.name,
                    persona_lookup=persona_lookup,
                    mcp_session=mcp_session,
                    use_tool_calls=use_tool_calls,
                )
                results.append(result)
                if persona_id is not None:
                    raw_by_persona[persona_id] = len(result.proposals)

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

    outcome = _aggregate(strategy=strategy, results=results)
    # Cycle 197 — dedup proposals across fan-out, attach raw counts
    outcome.proposals = _dedup_proposals(outcome.proposals)
    outcome.raw_proposals_by_persona = raw_by_persona
    # Cycle 198 spike — per-persona diagnostic detail (exposes transcript-level
    # errors that aren't captured by blocked_personas). Callers can grep
    # per_persona_results[*].error to surface why a persona-run degraded even
    # when it didn't raise.
    outcome.per_persona_results = [
        {
            "persona_id": r.persona_id,
            "outcome": r.outcome,
            "error": r.error,
            "steps": r.steps,
            "tokens": r.tokens,
        }
        for r in results
    ]
    return outcome


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
    mcp_session: Any = None,
    use_tool_calls: bool = True,
) -> _PersonaRunResult:
    """Run one explore mission for a single persona and collect tool outputs.

    ``mcp_session`` and ``use_tool_calls`` are propagated to DazzleAgent to
    select the execution path (Path β tool-use on direct SDK when
    mcp_session is None + use_tool_calls is True, Path γ text-protocol
    sampling when mcp_session is non-None + use_tool_calls is False).
    """
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
        mcp_session=mcp_session,
        use_tool_calls=use_tool_calls,
    )
    transcript = await agent.run(mission)

    # Tag each proposal/finding with which persona produced it so callers
    # can attribute results when aggregating across a multi-persona run.
    for p in proposals:
        p["persona_id"] = persona_id
    for f in findings:
        f["persona_id"] = persona_id

    # Propagate transcript-level error into _PersonaRunResult.error so
    # aggregators + callers can surface diagnostic info even when the
    # persona completed (didn't raise) but the agent loop recorded an
    # error (cycle 198 spike finding — Path γ was silently returning
    # degraded=True with zero steps and no error context).
    persona_error: str | None = None
    if transcript.outcome != "completed":
        err = getattr(transcript, "error", None)
        persona_error = f"{transcript.outcome}: {err}" if err else transcript.outcome

    return _PersonaRunResult(
        persona_id=persona_id,
        proposals=proposals,
        findings=findings,
        outcome=transcript.outcome,
        steps=len(transcript.steps),
        tokens=transcript.tokens_used,
        error=persona_error,
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
