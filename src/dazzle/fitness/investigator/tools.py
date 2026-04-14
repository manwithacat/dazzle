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
    metadata. Tasks 10-14 will append more tools to this list.
    """
    return [
        _read_file_tool(case_file, dazzle_root, state),
        _query_dsl_tool(case_file, dazzle_root, state),
        _get_cluster_findings_tool(case_file, dazzle_root, state),
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


def _query_dsl_tool(case_file: CaseFile, dazzle_root: Path, state: ToolState) -> AgentTool:
    """Build the query_dsl tool.

    Fetches the parsed DSL node for an entity, surface, workspace, service,
    process, persona, or enum by name. On unknown names returns a
    did_you_mean list with fuzzy suggestions.
    """

    def handler(name: str) -> dict[str, Any]:
        state.tool_calls_summary.append(f"query_dsl({name})")
        scope_root = case_file.example_root or dazzle_root

        try:
            from dazzle.core.appspec_loader import load_project_appspec
        except ImportError:
            return {
                "error": "DSL parser unavailable",
                "hint": "install dazzle[dev]",
            }

        try:
            appspec = load_project_appspec(scope_root)
        except Exception as e:
            return {"error": f"DSL parse failed: {e}"}

        node, kind = _lookup_ir_node(appspec, name)
        if node is None:
            all_names = _collect_ir_names(appspec)
            suggestions = difflib.get_close_matches(name, all_names, n=3, cutoff=0.5)
            return {
                "error": f"no DSL node named {name!r}",
                "did_you_mean": suggestions,
            }

        serialised = _serialise_ir_node(node, kind)
        source_file = serialised.get("source_file")
        if source_file and isinstance(source_file, str):
            state.evidence_paths.add(source_file)
        return serialised

    return AgentTool(
        name="query_dsl",
        description="Look up a parsed DSL node (entity/surface/workspace/etc.) by name.",
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The IR node name."},
            },
            "required": ["name"],
        },
        handler=handler,
    )


def _resolve_path(appspec: Any, path: tuple[str, ...]) -> Any:
    """Walk a dotted attribute path (e.g. ('domain', 'entities'))."""
    obj: Any = appspec
    for part in path:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _lookup_ir_node(appspec: Any, name: str) -> tuple[Any, str]:
    """Try each IR collection in turn; return (node, kind) or (None, '')."""
    for kind_name, path in [
        ("entity", ("domain", "entities")),  # nested under domain
        ("surface", ("surfaces",)),
        ("workspace", ("workspaces",)),
        ("experience", ("experiences",)),
        ("island", ("islands",)),
        ("service", ("domain_services",)),
        ("process", ("processes",)),
        ("persona", ("personas",)),
        ("enum", ("enums",)),
    ]:
        nodes = _resolve_path(appspec, path)
        if not nodes:
            continue
        for node in nodes:
            node_name = getattr(node, "name", None) or getattr(node, "id", None)
            if node_name == name:
                return node, kind_name
    return None, ""


def _collect_ir_names(appspec: Any) -> list[str]:
    names: list[str] = []
    for path in (
        ("domain", "entities"),
        ("surfaces",),
        ("workspaces",),
        ("experiences",),
        ("islands",),
        ("domain_services",),
        ("processes",),
        ("personas",),
        ("enums",),
    ):
        for node in _resolve_path(appspec, path) or []:
            node_name = getattr(node, "name", None) or getattr(node, "id", None)
            if node_name:
                names.append(str(node_name))
    return names


def _serialise_ir_node(node: Any, kind: str) -> dict[str, Any]:
    """Best-effort dict serialisation for an IR node."""
    name = getattr(node, "name", None) or getattr(node, "id", None)
    result: dict[str, Any] = {"kind": kind, "name": name}
    for attr in ("title", "mode", "uses_entity", "personas", "fields", "scope_rules", "sections"):
        value = getattr(node, attr, None)
        if value is None:
            continue
        if isinstance(value, list):
            result[attr] = [
                _field_to_dict(v) if hasattr(v, "model_dump") or hasattr(v, "__dict__") else v
                for v in value
            ]
        else:
            result[attr] = value if isinstance(value, (str, int, float, bool)) else str(value)

    # Source location — read from node.source (SourceLocation) if present
    source = getattr(node, "source", None)
    if source is not None:
        source_file = getattr(source, "file", None)
        if source_file:
            result["source_file"] = str(source_file)
        source_line = getattr(source, "line", None)
        if source_line is not None:
            result["source_line"] = int(source_line)
    return result


def _field_to_dict(obj: Any) -> dict[str, Any]:
    """Convert an IR spec element to a plain dict.

    Prefers Pydantic v2's `model_dump()` for recursive serialisation of
    nested models. Falls back to `__dict__` for non-Pydantic objects
    (e.g., StrEnum). Final fallback is `str(obj)`.
    """
    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump()
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {"value": str(obj)}


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


def _get_cluster_findings_tool(
    case_file: CaseFile,
    dazzle_root: Path,
    state: ToolState,
) -> AgentTool:
    """Build the get_cluster_findings tool.

    Fetches more sibling findings beyond the case file's initial set.
    Capped at CLUSTER_FINDING_MISSION_CAP (30) per cluster per mission.
    """
    from dazzle.fitness.backlog import read_backlog_findings
    from dazzle.fitness.triage import read_queue_file

    def handler(cluster_id: str, limit: int = 10) -> dict[str, Any]:
        state.tool_calls_summary.append(f"get_cluster_findings({cluster_id}, limit={limit})")
        # Clamp limit
        limit = max(1, min(20, limit))

        # Resolve the backlog source — same precedence as the case file
        if case_file.example_root is not None:
            backlog_path = case_file.example_root / "dev_docs" / "fitness-backlog.md"
            if not backlog_path.exists():
                backlog_path = dazzle_root / "dev_docs" / "fitness-backlog.md"
        else:
            backlog_path = dazzle_root / "dev_docs" / "fitness-backlog.md"

        result: dict[str, Any] = {}

        # Resolve the cluster to filter against. By default use the case file's
        # own cluster; if the LLM queries a different cluster, look it up in
        # the queue file and use that cluster's attributes as the filter.
        cluster_filter = case_file.cluster
        if cluster_id != case_file.cluster.cluster_id:
            queue_dir = case_file.example_root or dazzle_root
            queue_path = queue_dir / "dev_docs" / "fitness-queue.md"
            if not queue_path.exists():
                queue_path = dazzle_root / "dev_docs" / "fitness-queue.md"
            known_clusters: list[Any] = []
            if queue_path.exists():
                try:
                    known_clusters = read_queue_file(queue_path)
                except Exception:
                    known_clusters = []
            matched = next(
                (c for c in known_clusters if c.cluster_id == cluster_id),
                None,
            )
            if matched is None:
                return {
                    "error": "cluster not found",
                    "did_you_mean": [case_file.cluster.cluster_id],
                }
            cluster_filter = matched
            result["warning"] = (
                f"querying cluster {cluster_id} while investigating {case_file.cluster.cluster_id}"
            )

        # Check mission cap
        seen = state.findings_seen.get(cluster_id, 0)
        if seen >= CLUSTER_FINDING_MISSION_CAP:
            return {
                "findings": [],
                "note": (
                    f"{seen} findings already fetched for this cluster. "
                    "Remaining findings have equivalent canonical summaries "
                    "(that's how they got clustered). For variation try "
                    "get_related_clusters(locus=...) or read_file on the "
                    "locus; for evidence depth re-read the existing samples."
                ),
            }

        # Load all findings from the backlog, filter to this cluster,
        # exclude those already in the case file AND those returned by
        # prior calls in this mission
        all_findings = read_backlog_findings(backlog_path)
        excluded_ids = {case_file.sample_finding.id}
        excluded_ids.update(s.id for s in case_file.siblings)
        excluded_ids.update(state.findings_returned_ids)

        candidates = [
            f
            for f in all_findings
            if f.id not in excluded_ids
            and f.locus == cluster_filter.locus
            and f.axis == cluster_filter.axis
            and f.persona == cluster_filter.persona
        ]

        remaining_budget = max(0, CLUSTER_FINDING_MISSION_CAP - seen)
        to_return = candidates[: min(limit, remaining_budget)]
        state.findings_seen[cluster_id] = seen + len(to_return)
        state.findings_returned_ids.update(f.id for f in to_return)

        result["findings"] = [_finding_to_dict(f) for f in to_return]
        return result

    return AgentTool(
        name="get_cluster_findings",
        description=(
            "Fetch more sibling findings beyond the case file's initial set. "
            "Capped at 30 per cluster per mission."
        ),
        schema={
            "type": "object",
            "properties": {
                "cluster_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["cluster_id"],
        },
        handler=handler,
    )


def _finding_to_dict(f: Any) -> dict[str, Any]:
    """Minimal JSON-safe projection of a Finding for LLM consumption."""
    return {
        "id": f.id,
        "persona": f.persona,
        "axis": f.axis,
        "severity": f.severity,
        "locus": f.locus,
        "expected": f.expected,
        "observed": f.observed,
        "evidence_excerpt": list(f.evidence_embedded.transcript_excerpt[:3]),
    }
