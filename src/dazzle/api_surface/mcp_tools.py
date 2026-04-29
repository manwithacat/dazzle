"""
MCP-tools API surface snapshot — cycle 3 of #961.

Walks the consolidated MCP tool registry and emits a deterministic snapshot
of every tool's name, input schema, and a description hash. Schema shape is
the load-bearing API surface; description is pinned by hash so wording
changes are visible without bloating the diff.
"""

import hashlib
import json
import os

from .dsl_constructs import REPO_ROOT

BASELINE_PATH = REPO_ROOT / "docs" / "api-surface" / "mcp-tools.txt"


def _description_hash(description: str) -> str:
    return hashlib.sha256(description.encode("utf-8")).hexdigest()[:12]


def _normalize_schema(schema: object) -> object:
    """Recursively sort dict keys for stable JSON output."""
    if isinstance(schema, dict):
        return {k: _normalize_schema(schema[k]) for k in sorted(schema)}
    if isinstance(schema, list):
        return [_normalize_schema(item) for item in schema]
    return schema


def snapshot_mcp_tools() -> str:
    """Render the deterministic MCP-tools API-surface snapshot."""
    # Force dev-mode so dev-only tools (list_projects, select_project, etc.)
    # are part of the snapshot. The runtime gate in `tools_consolidated.py`
    # only filters at request time; the public surface includes them.
    os.environ.setdefault("DAZZLE_DEV_MODE", "true")
    from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools

    tools = sorted(get_all_consolidated_tools(), key=lambda t: t.name)

    lines: list[str] = []
    lines.append("# DAZZLE MCP Tools — API Surface (cycle 3 of #961)")
    lines.append("#")
    lines.append(
        "# Source of truth: dazzle.mcp.server.tools_consolidated.get_all_consolidated_tools()"
    )
    lines.append("# Regenerate: dazzle inspect-api mcp-tools --write")
    lines.append("# Drift gate: tests/unit/test_api_surface_drift.py")
    lines.append("#")
    lines.append("# Each tool's input schema is the load-bearing public API. The description")
    lines.append("# is pinned by SHA-256 hash (12 hex chars) — wording changes are visible")
    lines.append("# in the diff without bloating it. Adding/removing an operation enum value,")
    lines.append("# changing a property type, or renaming a tool are all breaking changes.")
    lines.append("")
    lines.append(f"# Count: {len(tools)} tools")
    lines.append("")

    for tool in tools:
        lines.append(f"tool: {tool.name}")
        lines.append(f"  description_hash: {_description_hash(tool.description or '')}")
        lines.append(f"  description_len: {len(tool.description or '')}")
        normalized = _normalize_schema(tool.inputSchema)
        schema_text = json.dumps(normalized, indent=2, sort_keys=False)
        for schema_line in schema_text.splitlines():
            lines.append(f"  {schema_line}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def diff_against_baseline(snapshot: str | None = None) -> str:
    """Unified diff between baseline and live snapshot. Empty = no drift."""
    import difflib

    if snapshot is None:
        snapshot = snapshot_mcp_tools()
    if not BASELINE_PATH.exists():
        return f"(no baseline at {BASELINE_PATH} — run `dazzle inspect-api mcp-tools --write`)\n"
    baseline = BASELINE_PATH.read_text()
    if baseline == snapshot:
        return ""
    diff = difflib.unified_diff(
        baseline.splitlines(keepends=True),
        snapshot.splitlines(keepends=True),
        fromfile=str(BASELINE_PATH.relative_to(REPO_ROOT)),
        tofile="(live)",
        n=3,
    )
    return "".join(diff)


__all__ = [
    "BASELINE_PATH",
    "diff_against_baseline",
    "snapshot_mcp_tools",
]
