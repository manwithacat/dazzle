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
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    metadata. Tasks 10-14 will append more tools to this list.
    """
    return [
        _read_file_tool(case_file, dazzle_root, state),
        # Task 10: _query_dsl_tool(case_file, dazzle_root, state)
        # Task 11: _get_cluster_findings_tool(case_file, dazzle_root, state)
        # Task 12: _get_related_clusters_tool(case_file, dazzle_root, state)
        # Task 13: _search_spec_tool(case_file, dazzle_root, state)
        # Task 14: _propose_fix_tool(case_file, dazzle_root, llm_run_id, state)
    ]


def _read_file_tool(case_file: CaseFile, dazzle_root: Path, state: ToolState) -> AgentTool:
    """Build the read_file tool.

    Takes `case_file` for API consistency with the other tool builders
    (query_dsl uses it for example_root scoping, get_cluster_findings uses
    it for the current cluster's siblings). read_file itself doesn't need
    it — the handler only closes over `dazzle_root` and `state`.
    """

    def handler(path: str, line_range: list[int] | None = None) -> dict[str, Any]:
        suffix = f"[{line_range[0]}:{line_range[1]}]" if line_range else ""
        state.tool_calls_summary.append(f"read_file({path}{suffix})")

        if path.startswith("/"):
            return {"error": "path must be repo-relative", "hint": "drop leading slash"}

        root_resolved = dazzle_root.resolve()
        target = dazzle_root / path
        try:
            target_resolved = target.resolve()
        except (OSError, RuntimeError):
            return {"error": f"path could not be resolved: {path}"}

        try:
            target_resolved.relative_to(root_resolved)
        except ValueError:
            return {"error": f"path escapes repo root: {path}"}

        if not target_resolved.exists() or not target_resolved.is_file():
            return {
                "error": f"file not found: {path}",
                "similar": _find_similar_files(dazzle_root, path),
            }

        try:
            stat = target_resolved.stat()
        except OSError as e:
            return {"error": f"stat failed: {e}"}
        if stat.st_size >= FILE_MAX_BYTES:
            return {
                "error": f"file too large: {stat.st_size} bytes, cap is {FILE_MAX_BYTES}",
                "hint": "use line_range to read a slice",
            }

        try:
            head = target_resolved.read_bytes()[:BINARY_SNIFF_BYTES]
        except OSError as e:
            return {"error": f"read failed: {e}"}
        if b"\x00" in head:
            return {"error": "binary file; not readable"}

        try:
            content = target_resolved.read_text()
        except (OSError, UnicodeDecodeError) as e:
            return {"error": f"decode failed: {e}"}

        lines = content.splitlines()
        total = len(lines)
        width = max(3, len(str(total)))
        if line_range is not None:
            start = max(1, line_range[0])
            end = min(total, line_range[1])
            if start > end:
                return {"error": "line_range outside file bounds", "total_lines": total}
            excerpt_lines = lines[start - 1 : end]
            excerpt = "\n".join(f"{i + start:>{width}}: {t}" for i, t in enumerate(excerpt_lines))
        else:
            excerpt = "\n".join(f"{i + 1:>{width}}: {t}" for i, t in enumerate(lines))

        state.evidence_paths.add(path)
        return {"content": excerpt, "total_lines": total}

    return AgentTool(
        name="read_file",
        description="Read a repo-relative file. Returns content with line numbers prepended.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo-relative path."},
                "line_range": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "Optional inclusive [start, end] range.",
                },
            },
            "required": ["path"],
        },
        handler=handler,
    )


def _find_similar_files(dazzle_root: Path, missing: str) -> list[str]:
    """Return up to 3 files in the repo with filenames closest to `missing`."""
    stem = Path(missing).name
    if not stem:
        return []
    all_files: list[str] = []
    prefix = stem[:4] if len(stem) >= 4 else stem
    root_resolved = dazzle_root.resolve()
    for p in dazzle_root.rglob(prefix + "*"):
        if not p.is_file():
            continue
        try:
            rel = p.resolve().relative_to(root_resolved)
        except ValueError:
            continue
        all_files.append(str(rel))
        if len(all_files) >= 200:
            break
    close = difflib.get_close_matches(missing, all_files, n=3, cutoff=0.4)
    return close
