"""
Inference knowledge base for DAZZLE DSL generation.

Provides pattern matching and suggestions to help LLMs generate
more complete DSL from natural language specifications.

IMPORTANT: This KB provides SUGGESTIONS, not mandates. The patterns here are
common conventions that may help, but the LLM should:
1. Use these as starting points, not gospel
2. Override suggestions when context warrants it
3. Trust its own reasoning over static patterns
4. Adapt examples to the specific problem domain

Think of this as a "cheap RAG layer" - it surfaces relevant patterns that the
LLM might not think of, but the LLM's judgment takes precedence.

Token-efficient design:
- Minimal responses by default (just suggestions)
- Full examples only when detail="full"
- Limited to top 3 matches per category

Data is authored in ``inference_kb.toml`` (source of truth) and seeded into
the unified Knowledge Graph at startup.  All runtime queries go through the
KG — TOML is never read at query time (except by ``seed.py``).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from dazzle.mcp._graph_access import get_kg as _get_kg

logger = logging.getLogger(__name__)

# Maximum matches per category to keep responses small
MAX_MATCHES_PER_CATEGORY = 3

# ---------------------------------------------------------------------------
# Suggestion formatting — table-driven
# ---------------------------------------------------------------------------

# Each entry: (type_name, metadata_keys, full_detail_keys)
# metadata_keys  → always included in the suggestion dict
# full_detail_keys → only included when detail == "full"
_SUGGESTION_SCHEMA: dict[str, tuple[str, dict[str, str], dict[str, str]]] = {
    # category → (type, {result_key: meta_key}, {result_key: meta_key})
    "field_patterns": (
        "field",
        {"add": "suggests", "why": "rationale"},
        {"example": "example"},
    ),
    "entity_archetypes": (
        "archetype",
        {"pattern": "name", "add_fields": "common_fields", "add_features": "common_features"},
        {"example": "example"},
    ),
    "relationship_patterns": (
        "relationship",
        {"add": "suggests", "why": "rationale"},
        {"example": "example"},
    ),
    "spec_language": (
        "syntax",
        {"phrase": "phrase", "use": "maps_to"},
        {},
    ),
    "domain_entities": (
        "domain_entity",
        {
            "domain": "domain",
            "entity": "name",
            "description": "description",
            "fields": "fields",
            "features": "features",
        },
        {"example": "example"},
    ),
    "workflow_templates": (
        "workflow",
        {
            "name": "name",
            "description": "description",
            "states": "states",
            "initial_state": "initial_state",
        },
        {"transitions": "transitions"},
    ),
    "sitespec_section_inference": (
        "sitespec_section",
        {"add": "suggests", "why": "rationale"},
        {"example": "example"},
    ),
    "surface_inference": (
        "surface",
        {"pattern": "name", "add": "suggests", "why": "rationale"},
        {"example": "example"},
    ),
    "workspace_inference": (
        "workspace",
        {"pattern": "name", "add": "suggests", "why": "rationale"},
        {"example": "example"},
    ),
    "tool_suggestions": (
        "tool_suggestion",
        {"tool": "tool", "operation": "operation", "suggestion": "suggestion", "mode": "mode"},
        {},
    ),
}


def _inference_entity_to_suggestion(
    meta: dict[str, Any],
    category: str,
    detail: Literal["minimal", "full"],
) -> dict[str, Any] | None:
    """Convert an inference entity's metadata to a suggestion dict."""
    schema = _SUGGESTION_SCHEMA.get(category)
    if schema is None:
        return None

    type_name, keys, full_keys = schema
    s: dict[str, Any] = {"type": type_name}
    for result_key, meta_key in keys.items():
        val = meta.get(meta_key)
        if val is not None:
            s[result_key] = val
    if detail == "full":
        for result_key, meta_key in full_keys.items():
            val = meta.get(meta_key)
            if val is not None:
                s[result_key] = val
    return s


# ---------------------------------------------------------------------------
# Guidance string (shared across responses)
# ---------------------------------------------------------------------------

_GUIDANCE = (
    "These are SUGGESTIONS based on common patterns. "
    "Use your judgment - override when context warrants. "
    "Adapt examples to the specific domain."
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_inference_kb_version() -> str:
    """Get the version of the inference knowledge base."""
    graph = _get_kg()
    if graph is not None:
        version: str | None = graph.get_seed_meta("seed_version")
        if version:
            return version
    return "unknown"


def lookup_inference(
    query: str,
    detail: Literal["minimal", "full"] = "minimal",
    max_per_category: int = MAX_MATCHES_PER_CATEGORY,
) -> dict[str, Any]:
    """
    Search the inference knowledge base for patterns matching the query.

    Queries the unified Knowledge Graph.

    Args:
        query: Natural language query or keywords to search for
        detail: "minimal" returns only suggestions, "full" includes examples
        max_per_category: Maximum matches to return per category (default 3)

    Returns:
        Dictionary with matching patterns and suggestions
    """
    graph = _get_kg()
    if graph is None:
        return {
            "query": query,
            "suggestions": [],
            "count": 0,
            "hint": "Knowledge graph not initialized — inference patterns unavailable",
        }

    matches = graph.lookup_inference_matches(query, limit=50)
    if matches:
        all_suggestions: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {}

        for entity in matches:
            meta = entity.metadata
            category = meta.get("category", "")
            count = category_counts.get(category, 0)
            if count >= max_per_category:
                continue
            category_counts[category] = count + 1

            suggestion = _inference_entity_to_suggestion(meta, category, detail)
            if suggestion:
                all_suggestions.append(suggestion)

        if all_suggestions:
            return {
                "query": query,
                "suggestions": all_suggestions,
                "count": len(all_suggestions),
                "_guidance": _GUIDANCE,
            }

    return {
        "query": query,
        "suggestions": [],
        "count": 0,
        "_guidance": _GUIDANCE,
        "hint": (
            "No patterns matched. Try keywords like: upload, person, status, assigned, "
            "created by, sort, filter, search, datatable, dashboard, overview"
        ),
    }


def list_all_patterns() -> dict[str, Any]:
    """
    List all available patterns in the knowledge base.

    Returns a compact summary for LLM reference.
    """
    graph = _get_kg()
    if graph is None:
        return {
            "kb_version": "unknown",
            "usage": "Knowledge graph not initialized",
            "counts": {},
        }

    inference_entities = graph.list_entities(entity_type="inference", limit=500)

    # Group by category and collect triggers
    category_triggers: dict[str, list[str]] = {}
    category_counts: dict[str, int] = {}
    domains: dict[str, list[str]] = {}
    spec_phrases: list[str] = []

    for entity in inference_entities:
        meta = entity.metadata
        category = meta.get("category", "unknown")
        triggers = meta.get("triggers", [])

        category_counts[category] = category_counts.get(category, 0) + 1
        category_triggers.setdefault(category, []).extend(triggers)

        if category == "domain_entities":
            domain = meta.get("domain", "other")
            domains.setdefault(domain, []).append(meta.get("name", ""))

        if category == "spec_language":
            phrase = meta.get("phrase")
            if phrase:
                spec_phrases.append(phrase)

    version = graph.get_seed_meta("seed_version") or "unknown"

    result: dict[str, Any] = {
        "kb_version": version,
        "usage": "Call lookup_inference(query) with keywords from your SPEC",
        "counts": category_counts,
    }

    trigger_key_map = {
        "field_patterns": "field_triggers",
        "entity_archetypes": "archetype_indicators",
        "domain_entities": "domain_triggers",
        "workflow_templates": "workflow_triggers",
        "surface_inference": "surface_triggers",
        "workspace_inference": "workspace_triggers",
        "sitespec_section_inference": "sitespec_section_triggers",
        "tool_suggestions": "tool_suggestion_triggers",
    }
    for category, key in trigger_key_map.items():
        if category in category_triggers:
            result[key] = sorted(set(category_triggers[category]))

    if spec_phrases:
        result["spec_phrases"] = spec_phrases
    if domains:
        result["domains"] = domains

    return result


def get_pattern_by_id(pattern_id: str) -> dict[str, Any] | None:
    """Get a specific pattern by its ID (full detail)."""
    graph = _get_kg()
    if graph is None:
        return None

    # Search inference entities for matching ID in metadata
    inference_entities = graph.list_entities(entity_type="inference", limit=500)
    for entity in inference_entities:
        meta = entity.metadata
        if meta.get("id") == pattern_id:
            return {
                "category": meta.get("category", "unknown"),
                **{k: v for k, v in meta.items() if k != "source"},
            }

    return None


def reload_inference_kb() -> dict[str, Any]:
    """Re-seed the inference knowledge from TOML into the KG."""
    graph = _get_kg()
    if graph is not None:
        from dazzle.mcp.knowledge_graph.seed import seed_framework_knowledge

        seed_framework_knowledge(graph)

    return {
        "status": "reloaded",
        "version": get_inference_kb_version(),
    }
