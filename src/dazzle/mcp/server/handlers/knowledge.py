"""
Knowledge base tool handlers.

Handles concept lookup, example search, CLI help, workflow guides,
and inference pattern lookup.
"""

from __future__ import annotations

import json
from typing import Any

from dazzle.mcp.cli_help import get_cli_help, get_workflow_guide
from dazzle.mcp.examples import search_examples
from dazzle.mcp.inference import list_all_patterns, lookup_inference
from dazzle.mcp.semantics import lookup_concept


def lookup_concept_handler(args: dict[str, Any]) -> str:
    """Look up a DAZZLE DSL concept."""
    term = args.get("term")
    if not term:
        return json.dumps({"error": "term parameter required"})

    result = lookup_concept(term)
    return json.dumps(result, indent=2)


def find_examples_handler(args: dict[str, Any]) -> str:
    """Find example projects by features or complexity."""
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


def get_cli_help_handler(args: dict[str, Any]) -> str:
    """Get CLI help for a command."""
    command = args.get("command")
    result = get_cli_help(command)
    return json.dumps(result, indent=2)


def get_workflow_guide_handler(args: dict[str, Any]) -> str:
    """Get workflow guide."""
    workflow = args.get("workflow")
    if not workflow:
        return json.dumps({"error": "workflow parameter required"})

    result = get_workflow_guide(workflow)
    return json.dumps(result, indent=2)


def lookup_inference_handler(args: dict[str, Any]) -> str:
    """Search the inference knowledge base for DSL generation patterns."""
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
