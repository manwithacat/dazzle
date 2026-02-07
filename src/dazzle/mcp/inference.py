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
import tomllib
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Cache for loaded knowledge base — kept only for seed.py
_inference_kb: dict[str, Any] | None = None

# Maximum matches per category to keep responses small
MAX_MATCHES_PER_CATEGORY = 3


def _load_inference_kb() -> dict[str, Any]:
    """Load the inference knowledge base from TOML file.

    This is used by ``seed.py`` to read the authoritative TOML data.
    Runtime queries should NOT call this — they go through the KG.
    """
    global _inference_kb
    if _inference_kb is not None:
        return _inference_kb

    kb_path = Path(__file__).parent / "inference_kb.toml"
    if not kb_path.exists():
        return {"meta": {"version": "0.0.0"}, "field_patterns": []}

    with open(kb_path, "rb") as f:
        _inference_kb = tomllib.load(f)

    return _inference_kb


# ---------------------------------------------------------------------------
# KG helpers
# ---------------------------------------------------------------------------


def _get_kg() -> Any:
    """Return the knowledge graph or None."""
    try:
        from dazzle.mcp.server.state import get_knowledge_graph

        return get_knowledge_graph()
    except Exception:
        return None


def get_inference_kb_version() -> str:
    """Get the version of the inference knowledge base."""
    graph = _get_kg()
    if graph is not None:
        version: str | None = graph.get_seed_meta("seed_version")
        if version:
            return version
    # Fallback
    kb = _load_inference_kb()
    version_str: str = kb.get("meta", {}).get("version", "unknown")
    return version_str


def _inference_entity_to_suggestion(
    meta: dict[str, Any],
    category: str,
    detail: Literal["minimal", "full"],
) -> dict[str, Any] | None:
    """Convert an inference entity's metadata to a suggestion dict."""
    if category == "field_patterns":
        s: dict[str, Any] = {
            "type": "field",
            "add": meta.get("suggests"),
            "why": meta.get("rationale"),
        }
        if detail == "full":
            s["example"] = meta.get("example")
        return s
    elif category == "entity_archetypes":
        s = {
            "type": "archetype",
            "pattern": meta.get("name"),
            "add_fields": meta.get("common_fields"),
            "add_features": meta.get("common_features"),
        }
        if detail == "full":
            s["example"] = meta.get("example")
        return s
    elif category == "relationship_patterns":
        s = {"type": "relationship", "add": meta.get("suggests"), "why": meta.get("rationale")}
        if detail == "full":
            s["example"] = meta.get("example")
        return s
    elif category == "spec_language":
        return {"type": "syntax", "phrase": meta.get("phrase"), "use": meta.get("maps_to")}
    elif category == "domain_entities":
        s = {
            "type": "domain_entity",
            "domain": meta.get("domain"),
            "entity": meta.get("name"),
            "description": meta.get("description"),
            "fields": meta.get("fields"),
            "features": meta.get("features"),
        }
        if detail == "full":
            s["example"] = meta.get("example")
        return s
    elif category == "workflow_templates":
        s = {
            "type": "workflow",
            "name": meta.get("name"),
            "description": meta.get("description"),
            "states": meta.get("states"),
            "initial_state": meta.get("initial_state"),
        }
        if detail == "full":
            s["transitions"] = meta.get("transitions")
        return s
    elif category == "sitespec_section_inference":
        s = {"type": "sitespec_section", "add": meta.get("suggests"), "why": meta.get("rationale")}
        if detail == "full":
            s["example"] = meta.get("example")
        return s
    elif category == "surface_inference":
        s = {
            "type": "surface",
            "pattern": meta.get("name"),
            "add": meta.get("suggests"),
            "why": meta.get("rationale"),
        }
        if detail == "full":
            s["example"] = meta.get("example")
        return s
    elif category == "workspace_inference":
        s = {
            "type": "workspace",
            "pattern": meta.get("name"),
            "add": meta.get("suggests"),
            "why": meta.get("rationale"),
        }
        if detail == "full":
            s["example"] = meta.get("example")
        return s
    elif category == "tool_suggestions":
        s = {
            "type": "tool_suggestion",
            "tool": meta.get("tool"),
            "operation": meta.get("operation"),
            "suggestion": meta.get("suggestion"),
        }
        mode = meta.get("mode")
        if mode:
            s["mode"] = mode
        return s
    return None


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
    if graph is not None:
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
                    "_guidance": (
                        "These are SUGGESTIONS based on common patterns. "
                        "Use your judgment - override when context warrants. "
                        "Adapt examples to the specific domain."
                    ),
                }

        # No matches from KG
        return {
            "query": query,
            "suggestions": [],
            "count": 0,
            "_guidance": (
                "These are SUGGESTIONS based on common patterns. "
                "Use your judgment - override when context warrants. "
                "Adapt examples to the specific domain."
            ),
            "hint": (
                "No patterns matched. Try keywords like: upload, person, status, assigned, "
                "created by, sort, filter, search, datatable, dashboard, overview"
            ),
        }

    # KG not initialized — return empty with hint
    return {
        "query": query,
        "suggestions": [],
        "count": 0,
        "hint": "Knowledge graph not initialized — inference patterns unavailable",
    }


def _matches_triggers(query: str, query_words: set[str], triggers: list[str]) -> bool:
    """Check if query matches any of the triggers."""
    for trigger in triggers:
        # Check if trigger phrase is in query
        if trigger in query:
            return True
        # Check if any query word matches trigger
        trigger_words = set(trigger.split())
        if query_words & trigger_words:
            return True
    return False


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

        if category not in category_triggers:
            category_triggers[category] = []
        category_triggers[category].extend(triggers)

        # Build domain summary for domain_entities
        if category == "domain_entities":
            domain = meta.get("domain", "other")
            if domain not in domains:
                domains[domain] = []
            domains[domain].append(meta.get("name", ""))

        # Collect spec_language phrases
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

    # Add trigger lists keyed by well-known category names
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
        # Entity id in the graph is like "inference:field_patterns.file_upload"
        # The original TOML "id" is stored in metadata
        entry_id = meta.get("id")
        if entry_id == pattern_id:
            return {
                "category": meta.get("category", "unknown"),
                **{k: v for k, v in meta.items() if k != "source"},
            }

    return None


def reload_inference_kb() -> dict[str, Any]:
    """Re-seed the inference knowledge from TOML into the KG.

    Also clears the in-memory TOML cache.
    """
    global _inference_kb
    _inference_kb = None

    graph = _get_kg()
    if graph is not None:
        from dazzle.mcp.knowledge_graph.seed import ensure_seeded

        ensure_seeded(graph)

    version = get_inference_kb_version()
    return {
        "status": "reloaded",
        "version": version,
    }
