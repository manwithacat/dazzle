"""Investigator write-side tools.

This module holds tools that mutate state outside the repo (writing
proposal files, blocked artefacts, etc.) or perform terminal operations
that end the mission. propose_fix is the only tool here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dazzle.agent.core import AgentTool
from dazzle.fitness.investigator.case_file import CaseFile
from dazzle.fitness.investigator.proposal import (
    Proposal,
    ProposalValidationError,
    ProposalWriteError,
    ProposedFix,
    save_proposal,
    write_blocked_artefact,
)
from dazzle.fitness.investigator.tools import ToolState

# Tightened JSON Schema for Anthropic tool use (see propose_fix below).
# The `fixes` array items are fully constrained so Anthropic's API-side
# validation catches malformed proposals before they reach the handler.
# When this schema is used with tool use (DazzleAgent(use_tool_calls=True)),
# the model literally cannot emit a fix missing file_path, diff, rationale,
# or confidence — the API rejects it at the content-block level.
PROPOSE_FIX_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "fixes",
        "rationale",
        "overall_confidence",
        "verification_plan",
        "alternatives_considered",
        "investigation_log",
    ],
    "properties": {
        "fixes": {
            "type": "array",
            "description": "Concrete file-level changes to apply.",
            "items": {
                "type": "object",
                "required": ["file_path", "diff", "rationale", "confidence"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to modify, relative to repo root.",
                    },
                    "line_range": {
                        "type": "array",
                        "description": "Optional [start_line, end_line] for the target region.",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "diff": {
                        "type": "string",
                        "description": "Unified diff or replacement text for this fix.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this specific change is correct.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Per-fix confidence in [0.0, 1.0].",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
            },
        },
        "rationale": {
            "type": "string",
            "description": "Overall explanation of the proposed fix.",
        },
        "overall_confidence": {
            "type": "number",
            "description": "Overall confidence in the proposal in [0.0, 1.0].",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "verification_plan": {
            "type": "string",
            "description": "How to verify the fix works (test command, manual check, etc.).",
        },
        "alternatives_considered": {
            "type": "array",
            "description": "Other fixes that were considered and rejected.",
            "items": {"type": "string"},
        },
        "investigation_log": {
            "type": "string",
            "description": "Raw transcript of the investigation steps.",
        },
    },
}


def _propose_fix_tool(
    case_file: CaseFile,
    dazzle_root: Path,
    llm_run_id: str,
    state: ToolState,
) -> AgentTool:
    """Build the terminal propose_fix tool.

    This is the only tool that mutates anything. Calling it ends the mission:
    - On success: writes a Proposal to .dazzle/fitness-proposals/, sets
      state.terminal_status = "proposed", state.terminal_proposal_id = <uuid>.
    - On validation failure: writes a blocked artefact to
      .dazzle/fitness-proposals/_blocked/, sets terminal_status =
      "blocked_invalid_proposal".
    - On write failure (disk error, collision): sets terminal_status =
      "blocked_write_error". No blocked artefact (if proposal write failed,
      blocked-artefact write will probably also fail).
    """

    def handler(
        fixes: list[dict[str, Any]],
        rationale: str,
        overall_confidence: float,
        verification_plan: str,
        alternatives_considered: list[str],
        investigation_log: str,
    ) -> dict[str, Any]:
        state.tool_calls_summary.append(f"propose_fix({len(fixes)} fixes)")

        # Convert LLM args to ProposedFix instances
        try:
            proposed_fixes = tuple(
                ProposedFix(
                    file_path=str(f["file_path"]),
                    line_range=(
                        (int(f["line_range"][0]), int(f["line_range"][1]))
                        if f.get("line_range")
                        else None
                    ),
                    diff=str(f["diff"]),
                    rationale=str(f["rationale"]),
                    confidence=float(f["confidence"]),
                )
                for f in fixes
            )
        except (KeyError, TypeError, ValueError) as e:
            _block_and_record(
                case_file,
                dazzle_root,
                state,
                reason=f"propose_fix args malformed: {e}",
                raw=repr(
                    {
                        "fixes": fixes,
                        "rationale": rationale,
                        "overall_confidence": overall_confidence,
                        "verification_plan": verification_plan,
                        "alternatives_considered": alternatives_considered,
                        "investigation_log": investigation_log,
                    }
                ),
            )
            return {
                "error": f"propose_fix args malformed: {e}",
                "status": "blocked_invalid_proposal",
            }

        proposal_id = uuid4().hex
        proposal = Proposal(
            proposal_id=proposal_id,
            cluster_id=case_file.cluster.cluster_id,
            created=datetime.now(UTC),
            investigator_run_id=llm_run_id,
            fixes=proposed_fixes,
            overall_confidence=float(overall_confidence),
            rationale=str(rationale),
            alternatives_considered=tuple(alternatives_considered or ()),
            verification_plan=str(verification_plan),
            evidence_paths=tuple(sorted(state.evidence_paths)),
            tool_calls_summary=tuple(state.tool_calls_summary),
            status="proposed",
        )

        try:
            save_proposal(
                proposal,
                dazzle_root,
                case_file_text=case_file.to_prompt_text(),
                investigation_log=investigation_log,
            )
        except ProposalValidationError as e:
            _block_and_record(
                case_file,
                dazzle_root,
                state,
                reason=f"validation: {e}",
                raw=repr(proposal),
            )
            return {
                "error": f"validation: {e}",
                "status": "blocked_invalid_proposal",
            }
        except ProposalWriteError as e:
            state.terminal_status = "blocked_write_error"
            return {
                "error": f"write failed: {e}",
                "status": "blocked_write_error",
            }

        state.terminal_status = "proposed"
        state.terminal_proposal_id = proposal_id
        return {"status": "proposed", "proposal_id": proposal_id}

    return AgentTool(
        name="propose_fix",
        description=(
            "Terminal: write a structured Proposal to disk and end the mission. "
            "Call this only when you have a concrete fix to propose."
        ),
        schema=PROPOSE_FIX_SCHEMA,
        handler=handler,
    )


def _block_and_record(
    case_file: CaseFile,
    dazzle_root: Path,
    state: ToolState,
    *,
    reason: str,
    raw: str,
) -> None:
    """Write a blocked artefact and set terminal_status.

    Used when propose_fix is called with args that don't produce a valid
    Proposal — either malformed at parse time or rejected at save time.

    If the blocked-artefact write itself fails (e.g., same disk-full
    condition that triggered the original failure), swallow the OSError
    and still set terminal_status so the mission state machine completes
    cleanly. The caller's returned error dict already carries the
    original failure reason.
    """
    try:
        write_blocked_artefact(
            case_file.cluster.cluster_id,
            dazzle_root,
            reason=reason,
            case_file_text=case_file.to_prompt_text(),
            transcript=raw,
        )
    except OSError:
        pass
    state.terminal_status = "blocked_invalid_proposal"
