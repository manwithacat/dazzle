"""Runner: resolves clusters, builds case files, drives the mission, writes results.

The runner is the only place that decides (a) whether to re-investigate
(idempotence via proposal files on disk) and (b) how to translate mission
outcomes into Proposal objects or blocked artefacts.

Because the DazzleAgent LLM client is external, this module exposes a
stub-friendly shape: the caller provides an `llm_client` that is either a
real LLMAPIClient (production) or a test double. `_drive_mission`
discriminates on `hasattr(llm_client, "script")` — stub clients have a
pre-recorded script of tool calls; real clients do not.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Protocol

from dazzle.fitness.investigator.attempted import (
    load_attempted,
    mark_attempted,
    save_attempted,
)
from dazzle.fitness.investigator.case_file import (
    CaseFileBuildError,
    build_case_file,
)
from dazzle.fitness.investigator.metrics import append_metric
from dazzle.fitness.investigator.mission import build_investigator_mission
from dazzle.fitness.investigator.proposal import (
    Proposal,
    list_proposals,
)
from dazzle.fitness.triage import Cluster, read_queue_file


@dataclass(frozen=True)
class InvestigationResult:
    """Structured outcome of one run_investigation call.

    Used internally; callers normally receive a Proposal (or None) directly
    from run_investigation.
    """

    status: str  # "proposed" | "blocked_invalid_proposal" | "blocked_write_error" | "blocked_step_cap" | "blocked_stagnation"
    proposal_id: str | None
    cluster_id: str


class LlmClient(Protocol):
    """Minimal contract the runner needs from an LLM client or test double.

    Production: LLMAPIClient from dazzle.llm.api_client.
    Tests: _StubLlmClient with a scripted list of tool calls.
    """

    run_id: str


async def run_investigation(
    *,
    cluster: Cluster,
    dazzle_root: Path,
    llm_client: Any,
    force: bool = False,
    dry_run: bool = False,
) -> Proposal | None:
    """Investigate one cluster.

    Flow:
      - If force=False and a proposal for this cluster already exists on
        disk, return it without running the LLM.
      - If dry_run=True, print the case file and return None.
      - Otherwise build the case file, run the mission, write the proposal
        or blocked artefact, append metrics, update the attempted index,
        and return the Proposal (or None if blocked).
    """
    # 1. Idempotence check
    if not force:
        existing = _find_existing_proposal(dazzle_root, cluster.cluster_id)
        if existing is not None:
            return existing

    # 2. Build case file
    try:
        case_file = build_case_file(cluster, dazzle_root)
    except CaseFileBuildError as e:
        print(f"build_case_file failed: {e}")
        return None

    # 3. Dry-run: print and stop
    if dry_run:
        print(case_file.to_prompt_text())
        return None

    # 4. Build the mission
    mission, tool_state = build_investigator_mission(
        case_file=case_file,
        dazzle_root=dazzle_root,
        llm_run_id=llm_client.run_id,
    )

    # 5. Drive the mission
    t0 = monotonic()
    await _drive_mission(mission, tool_state, llm_client)
    duration_ms = int((monotonic() - t0) * 1000)

    # 6. Resolve terminal status
    status = tool_state.terminal_status or "blocked_step_cap"

    # 7. Append metric (token counts are 0 in v1 — real counts need
    #    DazzleAgent integration which isn't wired up yet)
    append_metric(
        dazzle_root,
        cluster_id=cluster.cluster_id,
        proposal_id=tool_state.terminal_proposal_id,
        status=status,
        tokens_in=0,
        tokens_out=0,
        tool_calls=len(tool_state.tool_calls_summary),
        duration_ms=duration_ms,
        model=getattr(llm_client, "model", "unknown"),
    )

    # 8. Update attempted index
    index = load_attempted(dazzle_root)
    mark_attempted(
        index,
        cluster.cluster_id,
        proposal_id=tool_state.terminal_proposal_id,
        status="proposed" if status == "proposed" else "blocked",
    )
    save_attempted(index, dazzle_root)

    # 9. Return
    if status == "proposed" and tool_state.terminal_proposal_id is not None:
        return _find_existing_proposal(dazzle_root, cluster.cluster_id)
    return None


async def walk_queue(
    *,
    dazzle_root: Path,
    llm_client: Any,
    top: int,
    force: bool,
    dry_run: bool,
) -> list[Proposal | None]:
    """Walk the top N clusters from fitness-queue.md, investigating each in sequence."""
    queue_path = dazzle_root / "dev_docs" / "fitness-queue.md"
    if not queue_path.exists():
        return []

    try:
        clusters = read_queue_file(queue_path)
    except Exception:
        return []

    selected = clusters[:top]
    results: list[Proposal | None] = []
    for cluster in selected:
        result = await run_investigation(
            cluster=cluster,
            dazzle_root=dazzle_root,
            llm_client=llm_client,
            force=force,
            dry_run=dry_run,
        )
        results.append(result)
    return results


def _find_existing_proposal(dazzle_root: Path, cluster_id: str) -> Proposal | None:
    """Return the most recent proposal for this cluster, or None."""
    proposals = list_proposals(dazzle_root, cluster_id=cluster_id)
    if not proposals:
        return None
    return proposals[-1]


async def _drive_mission(mission: Any, tool_state: Any, llm_client: Any) -> None:
    """Drive the mission with a stub LLM or real DazzleAgent.

    For stub clients (tests), walk the scripted tool calls directly
    without going through DazzleAgent. For real LLM clients, hand off
    to DazzleAgent.run().

    The discriminator is attribute-based: if llm_client has a `script`
    attribute it's treated as a stub.
    """
    if hasattr(llm_client, "script"):
        await _drive_stub(mission, tool_state, llm_client)
    else:
        await _drive_real(mission, tool_state, llm_client)


async def _drive_stub(mission: Any, tool_state: Any, llm_client: Any) -> None:
    """Execute scripted tool calls directly against the mission's tool list."""
    tools_by_name = {t.name: t for t in mission.tools}
    for entry in llm_client.script:
        llm_client.calls += 1
        tool_name = entry["tool"]
        args = entry.get("args") or {}
        tool = tools_by_name.get(tool_name)
        if tool is None:
            tool_state.terminal_status = "blocked_invalid_proposal"
            return
        result = tool.handler(**args)
        if asyncio.iscoroutine(result):
            result = await result
        if tool_state.terminal_status is not None:
            return
    # Script exhausted without terminal — stagnation
    if tool_state.terminal_status is None:
        tool_state.terminal_status = "blocked_stagnation"


async def _drive_real(mission: Any, tool_state: Any, llm_client: Any) -> None:
    """Production path: use DazzleAgent with NullObserver/NullExecutor."""
    from dazzle.agent.core import DazzleAgent
    from dazzle.fitness.investigator.agent_backends import NullExecutor, NullObserver

    agent = DazzleAgent(
        observer=NullObserver(),
        executor=NullExecutor(),
        model=getattr(llm_client, "model", None),
        api_key=getattr(llm_client, "api_key", None),
    )
    await agent.run(mission)
