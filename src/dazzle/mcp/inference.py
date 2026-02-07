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
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

# Cache for loaded knowledge base
_inference_kb: dict[str, Any] | None = None

# Maximum matches per category to keep responses small
MAX_MATCHES_PER_CATEGORY = 3


def _load_inference_kb() -> dict[str, Any]:
    """Load the inference knowledge base from TOML file."""
    global _inference_kb
    if _inference_kb is not None:
        return _inference_kb

    kb_path = Path(__file__).parent / "inference_kb.toml"
    if not kb_path.exists():
        return {"meta": {"version": "0.0.0"}, "field_patterns": []}

    with open(kb_path, "rb") as f:
        _inference_kb = tomllib.load(f)

    return _inference_kb


def get_inference_kb_version() -> str:
    """Get the version of the inference knowledge base."""
    kb = _load_inference_kb()
    version: str = kb.get("meta", {}).get("version", "unknown")
    return version


def lookup_inference(
    query: str,
    detail: Literal["minimal", "full"] = "minimal",
    max_per_category: int = MAX_MATCHES_PER_CATEGORY,
) -> dict[str, Any]:
    """
    Search the inference knowledge base for patterns matching the query.

    Args:
        query: Natural language query or keywords to search for
        detail: "minimal" returns only suggestions, "full" includes examples
        max_per_category: Maximum matches to return per category (default 3)

    Returns:
        Dictionary with matching patterns and suggestions
    """
    kb = _load_inference_kb()
    query_lower = query.lower()
    query_words = set(query_lower.split())

    results: dict[str, Any] = {
        "query": query,
        "suggestions": [],  # Flat list of actionable suggestions
    }

    all_suggestions: list[dict[str, Any]] = []

    # Search field patterns - these are the most actionable
    matches = 0
    for pattern in kb.get("field_patterns", []):
        if matches >= max_per_category:
            break
        triggers = [t.lower() for t in pattern.get("triggers", [])]
        if _matches_triggers(query_lower, query_words, triggers):
            suggestion: dict[str, Any] = {
                "type": "field",
                "add": pattern.get("suggests"),
                "why": pattern.get("rationale"),
            }
            if detail == "full":
                suggestion["example"] = pattern.get("example")
            all_suggestions.append(suggestion)
            matches += 1

    # Search entity archetypes
    matches = 0
    for archetype in kb.get("entity_archetypes", []):
        if matches >= max_per_category:
            break
        indicators = [i.lower() for i in archetype.get("indicators", [])]
        if _matches_triggers(query_lower, query_words, indicators):
            suggestion = {
                "type": "archetype",
                "pattern": archetype.get("name"),
                "add_fields": archetype.get("common_fields"),
                "add_features": archetype.get("common_features"),
            }
            if detail == "full":
                suggestion["example"] = archetype.get("example")
            all_suggestions.append(suggestion)
            matches += 1

    # Search relationship patterns
    matches = 0
    for pattern in kb.get("relationship_patterns", []):
        if matches >= max_per_category:
            break
        triggers = [t.lower() for t in pattern.get("triggers", [])]
        if _matches_triggers(query_lower, query_words, triggers):
            suggestion = {
                "type": "relationship",
                "add": pattern.get("suggests"),
                "why": pattern.get("rationale"),
            }
            if detail == "full":
                suggestion["example"] = pattern.get("example")
            all_suggestions.append(suggestion)
            matches += 1

    # Search spec language mappings - very compact
    matches = 0
    for mapping in kb.get("spec_language", []):
        if matches >= max_per_category:
            break
        phrase = mapping.get("phrase", "").lower()
        if phrase in query_lower or any(w in phrase for w in query_words):
            all_suggestions.append(
                {
                    "type": "syntax",
                    "phrase": mapping.get("phrase"),
                    "use": mapping.get("maps_to"),
                }
            )
            matches += 1

    # Search domain entities - pre-built entity templates
    matches = 0
    for entity in kb.get("domain_entities", []):
        if matches >= max_per_category:
            break
        triggers = [t.lower() for t in entity.get("triggers", [])]
        if _matches_triggers(query_lower, query_words, triggers):
            suggestion = {
                "type": "domain_entity",
                "domain": entity.get("domain"),
                "entity": entity.get("name"),
                "description": entity.get("description"),
                "fields": entity.get("fields"),
                "features": entity.get("features"),
            }
            if detail == "full":
                suggestion["example"] = entity.get("example")
            all_suggestions.append(suggestion)
            matches += 1

    # Search workflow templates - pre-built state machines
    matches = 0
    for workflow in kb.get("workflow_templates", []):
        if matches >= max_per_category:
            break
        triggers = [t.lower() for t in workflow.get("triggers", [])]
        if _matches_triggers(query_lower, query_words, triggers):
            suggestion = {
                "type": "workflow",
                "name": workflow.get("name"),
                "description": workflow.get("description"),
                "states": workflow.get("states"),
                "initial_state": workflow.get("initial_state"),
            }
            if detail == "full":
                suggestion["transitions"] = workflow.get("transitions")
            all_suggestions.append(suggestion)
            matches += 1

    # Search sitespec section inference - section type suggestions
    matches = 0
    for pattern in kb.get("sitespec_section_inference", []):
        if matches >= max_per_category:
            break
        triggers = [t.lower() for t in pattern.get("triggers", [])]
        if _matches_triggers(query_lower, query_words, triggers):
            suggestion = {
                "type": "sitespec_section",
                "add": pattern.get("suggests"),
                "why": pattern.get("rationale"),
            }
            if detail == "full":
                suggestion["example"] = pattern.get("example")
            all_suggestions.append(suggestion)
            matches += 1

    # Search surface inference - UX block and DataTable suggestions
    matches = 0
    for pattern in kb.get("surface_inference", []):
        if matches >= max_per_category:
            break
        triggers = [t.lower() for t in pattern.get("triggers", [])]
        if _matches_triggers(query_lower, query_words, triggers):
            suggestion = {
                "type": "surface",
                "pattern": pattern.get("name"),
                "add": pattern.get("suggests"),
                "why": pattern.get("rationale"),
            }
            if detail == "full":
                suggestion["example"] = pattern.get("example")
            all_suggestions.append(suggestion)
            matches += 1

    # Search workspace inference - dashboard and layout suggestions
    matches = 0
    for pattern in kb.get("workspace_inference", []):
        if matches >= max_per_category:
            break
        triggers = [t.lower() for t in pattern.get("triggers", [])]
        if _matches_triggers(query_lower, query_words, triggers):
            suggestion = {
                "type": "workspace",
                "pattern": pattern.get("name"),
                "add": pattern.get("suggests"),
                "why": pattern.get("rationale"),
            }
            if detail == "full":
                suggestion["example"] = pattern.get("example")
            all_suggestions.append(suggestion)
            matches += 1

    # Search tool suggestions - MCP tool recommendations
    matches = 0
    for pattern in kb.get("tool_suggestions", []):
        if matches >= max_per_category:
            break
        triggers = [t.lower() for t in pattern.get("triggers", [])]
        if _matches_triggers(query_lower, query_words, triggers):
            suggestion = {
                "type": "tool_suggestion",
                "tool": pattern.get("tool"),
                "operation": pattern.get("operation"),
                "suggestion": pattern.get("suggestion"),
            }
            mode = pattern.get("mode")
            if mode:
                suggestion["mode"] = mode
            all_suggestions.append(suggestion)
            matches += 1

    results["suggestions"] = all_suggestions
    results["count"] = len(all_suggestions)

    # Add guidance that these are suggestions, not mandates
    results["_guidance"] = (
        "These are SUGGESTIONS based on common patterns. "
        "Use your judgment - override when context warrants. "
        "Adapt examples to the specific domain."
    )

    # Add hint if no matches
    if not all_suggestions:
        results["hint"] = (
            "No patterns matched. Try keywords like: upload, person, status, assigned, "
            "created by, sort, filter, search, datatable, dashboard, overview"
        )

    return results


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
    kb = _load_inference_kb()

    # Build compact trigger index
    field_triggers: list[str] = []
    for p in kb.get("field_patterns", []):
        field_triggers.extend(p.get("triggers", []))

    archetype_indicators: list[str] = []
    for a in kb.get("entity_archetypes", []):
        archetype_indicators.extend(a.get("indicators", []))

    # Domain entity triggers
    domain_triggers: list[str] = []
    for e in kb.get("domain_entities", []):
        domain_triggers.extend(e.get("triggers", []))

    # Workflow triggers
    workflow_triggers: list[str] = []
    for w in kb.get("workflow_templates", []):
        workflow_triggers.extend(w.get("triggers", []))

    # Sitespec section triggers
    sitespec_section_triggers: list[str] = []
    for s in kb.get("sitespec_section_inference", []):
        sitespec_section_triggers.extend(s.get("triggers", []))

    # Surface inference triggers
    surface_triggers: list[str] = []
    for s in kb.get("surface_inference", []):
        surface_triggers.extend(s.get("triggers", []))

    # Workspace inference triggers
    workspace_triggers: list[str] = []
    for w in kb.get("workspace_inference", []):
        workspace_triggers.extend(w.get("triggers", []))

    # Tool suggestion triggers
    tool_suggestion_triggers: list[str] = []
    for t in kb.get("tool_suggestions", []):
        tool_suggestion_triggers.extend(t.get("triggers", []))

    # Domain summary
    domains: dict[str, list[str]] = {}
    for e in kb.get("domain_entities", []):
        domain = e.get("domain", "other")
        if domain not in domains:
            domains[domain] = []
        domains[domain].append(e.get("name", ""))

    return {
        "kb_version": kb.get("meta", {}).get("version", "unknown"),
        "usage": "Call lookup_inference(query) with keywords from your SPEC",
        "field_triggers": sorted(set(field_triggers)),
        "archetype_indicators": sorted(set(archetype_indicators)),
        "domain_triggers": sorted(set(domain_triggers)),
        "workflow_triggers": sorted(set(workflow_triggers)),
        "surface_triggers": sorted(set(surface_triggers)),
        "workspace_triggers": sorted(set(workspace_triggers)),
        "sitespec_section_triggers": sorted(set(sitespec_section_triggers)),
        "tool_suggestion_triggers": sorted(set(tool_suggestion_triggers)),
        "spec_phrases": [m.get("phrase") for m in kb.get("spec_language", [])],
        "domains": domains,
        "counts": {
            "field_patterns": len(kb.get("field_patterns", [])),
            "entity_archetypes": len(kb.get("entity_archetypes", [])),
            "domain_entities": len(kb.get("domain_entities", [])),
            "workflow_templates": len(kb.get("workflow_templates", [])),
            "relationship_patterns": len(kb.get("relationship_patterns", [])),
            "spec_language": len(kb.get("spec_language", [])),
            "surface_inference": len(kb.get("surface_inference", [])),
            "workspace_inference": len(kb.get("workspace_inference", [])),
            "sitespec_section_inference": len(kb.get("sitespec_section_inference", [])),
            "tool_suggestions": len(kb.get("tool_suggestions", [])),
        },
    }


def get_pattern_by_id(pattern_id: str) -> dict[str, Any] | None:
    """Get a specific pattern by its ID (full detail)."""
    kb = _load_inference_kb()

    # Search all pattern categories
    for category in [
        "field_patterns",
        "entity_archetypes",
        "relationship_patterns",
        "surface_inference",
        "workspace_inference",
        "domain_entities",
        "workflow_templates",
        "sitespec_section_inference",
        "tool_suggestions",
    ]:
        for pattern in kb.get(category, []):
            if pattern.get("id") == pattern_id:
                return {
                    "category": category,
                    **pattern,
                }

    return None


def reload_inference_kb() -> dict[str, Any]:
    """Reload the inference knowledge base from disk."""
    global _inference_kb
    _inference_kb = None
    kb = _load_inference_kb()
    return {
        "status": "reloaded",
        "version": kb.get("meta", {}).get("version", "unknown"),
    }
