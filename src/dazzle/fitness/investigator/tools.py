"""Investigator tool layer.

Six tools wrap the read-only observations the LLM uses to build proposals.
All tools return structured dicts — no opaque exceptions for
LLM-caller-fault failures. Only propose_fix is terminal, and it signals
termination by setting state.terminal_status rather than raising.

Tasks 9-14 fill in the 6 tools incrementally:
- Task 9: ToolState + read_file
- Task 10: query_dsl
- Task 11: get_cluster_findings
- Task 12: get_related_clusters
- Task 13: search_spec
- Task 14: propose_fix (terminal)

Module layout (post-Task-12 split):
- tools.py          — this file: ToolState, constants, build_investigator_tools
- tools_read.py     — 4 read-tool builders and their private helpers
- tools_write.py    — stub; propose_fix (Task 14) lands here
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dazzle.agent.core import AgentTool
from dazzle.fitness.investigator.case_file import CaseFile

BINARY_SNIFF_BYTES = 1024
FILE_MAX_BYTES = 2 * 1024 * 1024
CLUSTER_FINDING_MISSION_CAP = 30


@dataclass
class ToolState:
    """Per-mission mutable state shared across all tool invocations."""

    evidence_paths: set[str] = field(default_factory=set)
    tool_calls_summary: list[str] = field(default_factory=list)
    findings_seen: dict[str, int] = field(default_factory=dict)
    findings_returned_ids: set[str] = field(default_factory=set)
    terminal_status: str | None = None  # set by propose_fix; None until terminal call
    terminal_proposal_id: str | None = None


def build_investigator_tools(
    *,
    case_file: CaseFile,
    dazzle_root: Path,
    llm_run_id: str,
    state: ToolState,
) -> list[AgentTool]:
    """Assemble all investigator tools with a shared ToolState.

    All builders receive the same (case_file, dazzle_root, state) triple so
    tools can close over consistent context. `llm_run_id` is forwarded only
    to `_propose_fix_tool` (Task 14) where it's embedded in the Proposal
    metadata. Tasks 13-14 will append more tools to this list.

    Imports from tools_read / tools_write are deferred to here to avoid the
    circular import that would arise if those modules were imported at module
    level (they import ToolState + constants from this module).
    """
    from dazzle.fitness.investigator.tools_read import (
        _get_cluster_findings_tool,
        _get_related_clusters_tool,
        _query_dsl_tool,
        _read_file_tool,
        _search_spec_tool,
    )

    return [
        _read_file_tool(case_file, dazzle_root, state),
        _query_dsl_tool(case_file, dazzle_root, state),
        _get_cluster_findings_tool(case_file, dazzle_root, state),
        _get_related_clusters_tool(case_file, dazzle_root, state),
        _search_spec_tool(case_file, dazzle_root, state),
        # Task 14: _propose_fix_tool(case_file, dazzle_root, llm_run_id, state)
    ]
