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
from dazzle.mcp.semantics_kb import MCP_SEMANTICS_VERSION, lookup_concept
from dazzle.mcp.semantics_kb.counter_priors import (
    load_all_counter_priors,
    match_code_triggers,
    match_text_triggers,
)

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


def _summarise_entry(entry: Any, *, include_body: bool) -> dict[str, Any]:
    """Render a CounterPrior for MCP output.

    Default shape keeps the response small (id + name + layer + summary +
    triggers + file_path); the agent can `Read` the file for the full body
    when needed. include_body=True returns the markdown body inline.
    """
    out = {
        "id": entry.id,
        "name": entry.name,
        "layer": entry.layer,
        "status": entry.status,
        "summary": entry.summary,
        "triggers_text": entry.triggers_text,
        "triggers_code": entry.triggers_code,
        "refs": entry.refs.model_dump(),
        "file_path": entry.file_path,
    }
    if include_body:
        out["body"] = entry.body
    return out


@wrap_handler_errors
def counter_prior_handler(args: dict[str, Any]) -> str:
    """Query the counter-prior catalogue.

    Modes:
      - id="<id>"            — fetch one entry (returns full body)
      - query="<sentence>"   — match against triggers_text (returns summaries)
      - code_shape="<text>"  — match triggers_code regexes, falling back to
                               triggers_text (a "description of code about to
                               be written" is prose, so both channels apply)
      - list_all=true        — return the full index (summaries only)
      - layer="<layer>"      — narrow list_all to one layer

    Agents reading a result use the returned `file_path` with the Read tool
    to get the full markdown body when query/code_shape didn't already
    include it.
    """
    progress = extract_progress(args)
    progress.log_sync("Querying counter-prior catalogue...")

    entries = load_all_counter_priors()  # wrap_handler_errors formats CounterPriorParseError

    entry_id = args.get("id")
    if entry_id:
        for e in entries:
            if e.id == entry_id:
                return json.dumps(_summarise_entry(e, include_body=True), indent=2)
        return error_response(f"no counter-prior with id={entry_id!r}")

    query = args.get("query")
    code_shape = args.get("code_shape")
    layer = args.get("layer")
    list_all = args.get("list_all", False)

    if query:
        hits = match_text_triggers(entries, query)
        return json.dumps(
            {
                "query": query,
                "match_count": len(hits),
                "matches": [_summarise_entry(e, include_body=False) for e in hits],
            },
            indent=2,
        )

    if code_shape:
        # Code regexes hit pasted source; text triggers hit prose descriptions
        # of the code about to be written (#1351 — the documented call shape).
        # Union both so the caller never needs to know the trigger taxonomy.
        code_hits = match_code_triggers(entries, code_shape)
        matched_ids = {e.id for e in code_hits}
        text_hits = [e for e in match_text_triggers(entries, code_shape) if e.id not in matched_ids]
        hits = code_hits + text_hits
        return json.dumps(
            {
                "code_shape": code_shape,
                "match_count": len(hits),
                "matches": [_summarise_entry(e, include_body=False) for e in hits],
            },
            indent=2,
        )

    if list_all:
        if layer:
            entries = [e for e in entries if e.layer == layer]
        return json.dumps(
            {
                "count": len(entries),
                "layer_filter": layer,
                "entries": [_summarise_entry(e, include_body=False) for e in entries],
            },
            indent=2,
        )

    return error_response("counter_prior requires one of: id, query, code_shape, list_all")
