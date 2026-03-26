"""
Knowledge base tool handlers.

Handles concept lookup, example search, CLI help, workflow guides,
and inference pattern lookup.
"""

import json
from typing import Any

from dazzle.mcp._graph_access import get_kg as _get_kg
from dazzle.mcp.cli_help import get_cli_help, get_workflow_guide
from dazzle.mcp.examples import search_examples
from dazzle.mcp.inference import list_all_patterns, lookup_inference
from dazzle.mcp.semantics import lookup_concept
from dazzle.mcp.semantics_kb import MCP_SEMANTICS_VERSION

from .common import error_response, extract_progress, wrap_handler_errors


@wrap_handler_errors
def lookup_concept_handler(args: dict[str, Any]) -> str:
    """Look up a DAZZLE DSL concept."""
    progress = extract_progress(args)
    term = args.get("term")
    if not term:
        return error_response("term parameter required")

    progress.log_sync(f"Looking up concept '{term}'...")
    result = lookup_concept(term)
    return json.dumps(result, indent=2)


@wrap_handler_errors
def find_examples_handler(args: dict[str, Any]) -> str:
    """Find example projects by features or complexity."""
    progress = extract_progress(args)
    progress.log_sync("Searching examples...")
    features = args.get("features")
    complexity = args.get("complexity")

    results = search_examples(features=features, complexity=complexity)

    return json.dumps(
        {
            "query": {
                "features": features,
                "complexity": complexity,
            },
            "count": len(results),
            "examples": results,
        },
        indent=2,
    )


@wrap_handler_errors
def get_cli_help_handler(args: dict[str, Any]) -> str:
    """Get CLI help for a command."""
    progress = extract_progress(args)
    progress.log_sync("Loading CLI help...")
    command = args.get("command")
    result = get_cli_help(command)
    return json.dumps(result, indent=2)


@wrap_handler_errors
def get_workflow_guide_handler(args: dict[str, Any]) -> str:
    """Get workflow guide."""
    progress = extract_progress(args)
    progress.log_sync("Loading workflow guide...")
    workflow = args.get("workflow")
    if not workflow:
        return error_response("workflow parameter required")

    result = get_workflow_guide(workflow)
    return json.dumps(result, indent=2)


@wrap_handler_errors
def lookup_inference_handler(args: dict[str, Any]) -> str:
    """Search the inference knowledge base for DSL generation patterns."""
    progress = extract_progress(args)
    progress.log_sync("Querying inference KB...")
    list_all = args.get("list_all", False)

    if list_all:
        result = list_all_patterns()
        return json.dumps(result, indent=2)

    query = args.get("query")
    if not query:
        return json.dumps(
            {
                "error": "Either 'query' parameter or 'list_all: true' is required",
                "hint": "Use 'query' with keywords from your SPEC, or 'list_all: true' to see trigger keywords",
            }
        )

    detail = args.get("detail", "minimal")
    if detail not in ("minimal", "full"):
        detail = "minimal"

    result = lookup_inference(query, detail=detail)
    return json.dumps(result, indent=2)


@wrap_handler_errors
def get_changelog_handler(args: dict[str, Any]) -> str:
    """Get Agent Guidance entries from recent releases."""
    progress = extract_progress(args)
    progress.log_sync("Loading changelog guidance...")

    since = args.get("since")
    limit = 5

    graph = _get_kg()
    if graph is not None:
        from packaging.version import Version

        entities = graph.list_entities(entity_type="changelog", limit=50)
        entries = []
        for e in entities:
            version = e.metadata.get("version", "")
            guidance = e.metadata.get("guidance", [])
            if guidance:
                entries.append({"version": version, "guidance": guidance})

        entries.sort(key=lambda e: Version(e["version"]), reverse=True)

        if since:
            since_ver = Version(since)
            entries = [e for e in entries if Version(e["version"]) >= since_ver]

        entries = entries[:limit]
    else:
        from dazzle.mcp.semantics_kb.changelog import parse_changelog_guidance

        entries = parse_changelog_guidance(since=since, limit=limit)

    return json.dumps(
        {
            "current_version": MCP_SEMANTICS_VERSION,
            "entries": entries,
            "total_entries": len(entries),
        },
        indent=2,
    )
