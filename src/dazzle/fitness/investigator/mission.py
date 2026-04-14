"""Investigator mission builder."""

from __future__ import annotations

from pathlib import Path

from dazzle.agent.core import Mission
from dazzle.agent.models import ActionType, AgentAction, Step
from dazzle.fitness.investigator.case_file import CaseFile
from dazzle.fitness.investigator.tools import ToolState, build_investigator_tools

MAX_STEPS = 25
STAGNATION_WINDOW = 4


def build_investigator_mission(
    *,
    case_file: CaseFile,
    dazzle_root: Path,
    llm_run_id: str,
) -> tuple[Mission, ToolState]:
    """Assemble a Mission for one cluster investigation.

    Returns (mission, tool_state). The caller keeps the tool_state
    reference to read evidence_paths, tool_calls_summary, and
    terminal_status after the mission completes.
    """
    tool_state = ToolState()
    tools = build_investigator_tools(
        case_file=case_file,
        dazzle_root=dazzle_root,
        llm_run_id=llm_run_id,
        state=tool_state,
    )

    system_prompt = _render_system_prompt(case_file)

    def completion(action: AgentAction, history: list[Step]) -> bool:
        """Terminate on propose_fix success or 4-step stagnation."""
        if tool_state.terminal_status is not None:
            return True
        if len(history) >= STAGNATION_WINDOW:
            last_window = history[-STAGNATION_WINDOW:]
            if all(s.action.type != ActionType.TOOL for s in last_window):
                return True
        return False

    mission = Mission(
        name=f"investigator:{case_file.cluster.cluster_id}",
        system_prompt=system_prompt,
        tools=tools,
        completion_criteria=completion,
        max_steps=MAX_STEPS,
        token_budget=200_000,
        context={
            "cluster_id": case_file.cluster.cluster_id,
            "mode": "investigator",
        },
    )
    return mission, tool_state


def _render_system_prompt(case_file: CaseFile) -> str:
    return _SYSTEM_PROMPT_TEMPLATE.format(case_file_text=case_file.to_prompt_text())


_SYSTEM_PROMPT_TEMPLATE = """You are an investigator in the Dazzle fitness loop. Your job is to examine
one cluster of fitness findings and produce a structured fix proposal that
a later actor subsystem can apply mechanically.

# Case File

{case_file_text}

The case file above is your starting point. It is NOT exhaustive — use your
tools to pull any additional context you need.

# Your goal

Produce a single call to `propose_fix` describing how to resolve this
cluster. The proposal must:

1. Fix the root cause, not the symptom. If the evidence points at a shared
   helper, propose a change to the helper — not a copy-paste in every caller.
2. When the evidence points at a shared helper, a template partial, or a
   repeated pattern, prefer a fix at the shared layer even if the diff is
   larger. A correct refactor is preferable to a narrow patch that leaves
   siblings broken.
3. Explain WHY the fix is correct in its rationale.
4. List at least two alternatives you considered and why you rejected them.
5. Provide a verification plan the actor can execute to confirm the fix works.
6. Use real line numbers from files you have read. Never guess at diffs.

# Tools

You have six tools. Five are read-only observers; the sixth ends the mission.

**read_file(path, line_range?)** — read any repo file. Line numbers are
prepended to every line; use those line numbers in your diffs.

**query_dsl(name)** — fetch the parsed DSL node for an entity, surface,
workspace, service, process, persona, or enum. If the name is wrong
you'll get a `did_you_mean` list.

**get_cluster_findings(cluster_id, limit)** — fetch more sibling findings
beyond those in the case file. Capped at 30 per cluster per mission.

**get_related_clusters(locus)** — find other clusters pointing at the
same file. Use this to decide whether your fix should address one symptom
or a shared root cause.

**search_spec(query)** — grep docs/superpowers/specs/ and docs/reference/
for a literal term. Use when you need to know the design intent.

**propose_fix(fixes, rationale, overall_confidence, verification_plan,
alternatives_considered, investigation_log)** — terminal. Calling this
ends the mission. Only call it when you have:
  - read the locus file (always)
  - verified the diff lines exist at the line numbers you reference
  - considered at least one alternative
  - written a verification plan more specific than "re-run Phase B"

# Termination

You have at most 25 steps. If you cannot produce a proposal within that
budget, end with `propose_fix` anyway and set overall_confidence low
(< 0.4). A low-confidence proposal is better than no proposal.

If the case file is insufficient and your tools cannot help — for example,
the locus points at a missing file — call `propose_fix` with one fix whose
rationale explains the blocker and overall_confidence=0.0. Never get stuck
in a tool-call loop; make progress or explain why you cannot.

# Style

- Keep per-fix rationales brief: two sentences.
- Keep alternatives brief: one line each, explaining WHY rejected.
- The investigation log is free-form markdown; write it as a future-you
  would want to read it.
- Confidence is your honest self-assessment. A 0.7 that turns out correct
  is better than a 0.95 that turns out wrong.
"""
