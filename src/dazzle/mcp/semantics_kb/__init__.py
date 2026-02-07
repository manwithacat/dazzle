"""
DAZZLE DSL Semantic Knowledge Base.

This package provides structured definitions, syntax examples, and relationships
for all DAZZLE DSL concepts.

Data is authored in TOML files (source of truth) and seeded into the unified
Knowledge Graph at startup.  All runtime queries go through the KG — TOML is
never read at query time.

Usage:
    from dazzle.mcp.semantics_kb import get_semantic_index, lookup_concept

    # Get full index
    index = get_semantic_index()

    # Look up a specific concept
    result = lookup_concept("entity")
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

# MCP Semantic Index version - reads from pyproject.toml
from dazzle._version import get_version as _get_version
from dazzle.mcp._graph_access import get_kg as _get_kg

logger = logging.getLogger(__name__)

MCP_SEMANTICS_VERSION = _get_version()
MCP_SEMANTICS_BUILD = 0

# Cache for loaded data (TOML fallback only used when KG is not initialized)
_semantic_cache: dict[str, Any] | None = None

# TOML files to load (order doesn't matter) — used by seed.py
TOML_FILES = [
    "core.toml",
    "ux.toml",
    "workspace.toml",
    "expressions.toml",
    "types.toml",
    "reference.toml",
    "testing.toml",
    "logic.toml",
    "cognition.toml",
    "extensibility.toml",
    "ejection.toml",
    "misc.toml",
    "patterns.toml",
    "frontend.toml",
]

# Alias mapping for common term variations — used by seed.py
ALIASES = {
    "transitions": "state_machine",
    "transition": "state_machine",
    "access": "access_rules",
    "computed": "computed_field",
    "computed_fields": "computed_field",
    # Type system aliases
    "enums": "enum",
    "enumeration": "enum",
    "reference": "ref",
    "foreign_key": "ref",
    "fk": "ref",
    # Keywords
    "keywords": "reserved_keywords",
    "reserved": "reserved_keywords",
    # Archetypes
    "archetypes": "archetype",
    "mixin": "archetype",
    "mixins": "archetype",
    "template": "archetype",
    # Relationships
    "has_many": "relationships",
    "has_one": "relationships",
    "belongs_to": "relationships",
    "embeds": "relationships",
    # Experience/wizard aliases
    "wizard": "experience",
    "wizards": "experience",
    "multi_step": "experience",
    "multi_step_flow": "experience",
    "multi_step_form": "experience",
    "onboarding": "experience",
    "onboarding_flow": "experience",
    "user_flow": "experience",
    "step_flow": "experience",
    # Site/frontend aliases
    "sections": "section_types",
    "section": "section_types",
    "section_type": "section_types",
    "page_sections": "section_types",
    "directives": "directive_syntax",
    "directive": "directive_syntax",
    "markdown_directives": "directive_syntax",
    "fences": "directive_syntax",
    "hybrid": "hybrid_pages",
    "hybrid_page": "hybrid_pages",
    "markdown_sections": "hybrid_pages",
    "comparison": "section_types",
    "card_grid": "section_types",
    "trust_bar": "section_types",
    "value_highlight": "section_types",
    "split_content": "section_types",
    # DataTable / list surface rendering aliases
    "datatable": "datatable",
    "data_table": "datatable",
    "table": "datatable",
    "list_table": "datatable",
    "sortable_table": "datatable",
    "filterable_table": "datatable",
    "sort": "datatable",
    "sorting": "datatable",
    "filter": "datatable",
    "filtering": "datatable",
    "search": "datatable",
    "column_visibility": "datatable",
    "empty_message": "datatable",
    "empty_state": "datatable",
    # Authentication aliases
    "authorization": "authentication",
    "login": "authentication",
    "password": "authentication",
    "auth": "authentication",
    "session": "authentication",
    # Surface action aliases
    "action": "surface_actions",
    "actions": "surface_actions",
    "on_submit": "surface_actions",
    "submit": "surface_actions",
    "outcome": "surface_actions",
    "outcomes": "surface_actions",
    # Surface mode aliases
    "mode": "surface_modes",
    "list_mode": "surface_modes",
    "view_mode": "surface_modes",
    "create_mode": "surface_modes",
    "edit_mode": "surface_modes",
    "form": "surface_modes",
    # Testing & demo aliases
    "scenarios": "scenario",
    "demo_data": "demo_data",
    "seed_data": "demo_data",
    "seed": "demo_data",
    "fixtures": "demo_data",
    # Financial aliases
    "ledger": "ledger",
    "tigerbeetle": "ledger",
    "double_entry": "ledger",
    "transaction": "transaction",
    "transfer": "transaction",
    # LLM aliases
    "llm_intent": "llm_intent",
    "llm_job": "llm_intent",
    "ai_job": "llm_intent",
    "llm_model": "llm_model",
    "ai_model": "llm_model",
    "llm_config": "llm_config",
    # Integration aliases
    "integration": "integration",
    "external_api": "integration",
    "api_connection": "integration",
    "foreign_model": "foreign_model",
    "external_model": "foreign_model",
    # Workspace region aliases
    "region": "workspace",
    "regions": "workspace",
    "dashboard": "workspace",
    "dashboard_layout": "stage",
    "layout": "stage",
    "stage_layout": "stage",
    "grid_layout": "stage",
    "overview": "workspace",
    "hub": "workspace",
    # Workspace aggregates
    "aggregate": "aggregate",
    "aggregates": "aggregate",
    "count": "aggregate",
    "sum": "aggregate",
    "avg": "aggregate",
    "metrics": "aggregate",
    "kpi": "aggregate",
    "metric": "aggregate",
    # Constraint aliases
    "unique": "unique_constraint",
    "unique_constraint": "unique_constraint",
    "constraint": "unique_constraint",
    # Pagination
    "pagination": "pagination",
    "paging": "pagination",
    # UI chrome aliases (point to closest concept)
    "routing": "surface_modes",
    "navigation": "surface_modes",
    "sidebar": "workspace",
    "modal": "surface_actions",
    "dialog": "surface_actions",
    # File handling aliases
    "file_upload": "field_types",
    "image": "field_types",
    "csv": "demo_data",
    "export": "demo_data",
    # API aliases
    "rest": "domain_service",
    "endpoint": "domain_service",
    "api": "domain_service",
    "webhook": "integration",
    # Workflow aliases
    "automation": "process",
    # Source/autocomplete
    "autocomplete": "field_types",
    "source": "field_types",
}


def get_mcp_version() -> dict[str, Any]:
    """Get MCP semantic index version information."""
    return {
        "version": MCP_SEMANTICS_VERSION,
        "build": MCP_SEMANTICS_BUILD,
        "full_version": f"{MCP_SEMANTICS_VERSION}.{MCP_SEMANTICS_BUILD}",
    }


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load a single TOML file. Used by seed.py."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def _load_semantic_data() -> dict[str, Any]:
    """Load and merge all TOML files into unified index (fallback for when KG is not initialized)."""
    global _semantic_cache

    if _semantic_cache is not None:
        return _semantic_cache

    kb_dir = Path(__file__).parent
    concepts: dict[str, Any] = {}
    patterns: dict[str, Any] = {}

    for filename in TOML_FILES:
        filepath = kb_dir / filename
        if not filepath.exists():
            continue

        data = _load_toml_file(filepath)

        # Extract concepts
        if "concepts" in data:
            concepts.update(data["concepts"])

        # Extract patterns
        if "patterns" in data:
            patterns.update(data["patterns"])

    _semantic_cache = {
        "version": MCP_SEMANTICS_VERSION,
        "concepts": concepts,
        "patterns": patterns,
    }

    return _semantic_cache


# ---------------------------------------------------------------------------
# KG helpers
# ---------------------------------------------------------------------------


def _get_semantic_index_from_kg() -> dict[str, Any] | None:
    """Build the semantic index dict from KG data."""
    graph = _get_kg()
    if graph is None:
        return None

    concepts: dict[str, Any] = {}
    for entity in graph.list_entities(entity_type="concept", limit=500):
        meta = entity.metadata
        concepts[entity.name] = {k: v for k, v in meta.items() if k != "source" and v}

    patterns: dict[str, Any] = {}
    for entity in graph.list_entities(entity_type="pattern", limit=500):
        meta = entity.metadata
        patterns[entity.name] = {k: v for k, v in meta.items() if k != "source" and v}

    return {
        "version": MCP_SEMANTICS_VERSION,
        "concepts": concepts,
        "patterns": patterns,
    }


def get_semantic_index() -> dict[str, Any]:
    """
    Get the complete semantic index for DAZZLE DSL.

    Returns a structured dictionary mapping concepts to their definitions,
    syntax, examples, and related concepts.

    Queries the Knowledge Graph. Falls back to TOML if the KG is not
    yet initialized (e.g. during MCP resource serving at startup).
    """
    result = _get_semantic_index_from_kg()
    if result is not None:
        return result
    # Fallback: KG not initialized yet (startup / resource serving)
    return _load_semantic_data()


def lookup_concept(term: str) -> dict[str, Any] | None:
    """
    Look up a DAZZLE concept by name.

    Queries the unified Knowledge Graph.

    Args:
        term: The concept name (e.g., 'persona', 'workspace', 'ux_block')

    Returns:
        Concept definition or None if not found
    """
    graph = _get_kg()
    if graph is None:
        return {"term": term, "found": False, "error": "Knowledge graph not initialized"}

    # Direct concept/alias/pattern lookup via KG
    entity = graph.lookup_concept(term)
    if entity is not None:
        meta = entity.metadata
        result: dict[str, Any] = {
            "term": term,
            "found": True,
            "type": "concept" if entity.entity_type == "concept" else "pattern",
        }
        for key in ("category", "definition", "syntax", "example", "description"):
            if key in meta and meta[key]:
                result[key] = meta[key]
        return result

    # Normalize for special-case and fuzzy search
    term_normalized = term.lower().replace(" ", "_").replace("-", "_")

    # Special case: "pattern" / "patterns" — list all patterns
    if term_normalized in ("pattern", "patterns"):
        pattern_entities = graph.list_entities(entity_type="pattern", limit=500)
        pattern_list = [
            {"name": e.name, "description": e.metadata.get("description")} for e in pattern_entities
        ]
        return {
            "term": term,
            "found": True,
            "type": "pattern_list",
            "patterns": pattern_list,
            "hint": "Use lookup_concept with a specific pattern name (e.g., 'crud', 'dashboard') to get full example code",
        }

    # Fuzzy search: partial matches in concepts and patterns
    matches: list[dict[str, Any]] = []

    for entity in graph.list_entities(entity_type="concept", limit=500):
        if (
            term_normalized in entity.name
            or term_normalized in entity.metadata.get("definition", "").lower()
        ):
            matches.append(
                {
                    "name": entity.name,
                    "category": entity.metadata.get("category"),
                    "definition": entity.metadata.get("definition"),
                }
            )

    for entity in graph.list_entities(entity_type="pattern", limit=500):
        if (
            term_normalized in entity.name
            or term_normalized in entity.metadata.get("description", "").lower()
        ):
            matches.append(
                {
                    "name": entity.name,
                    "type": "pattern",
                    "description": entity.metadata.get("description"),
                }
            )

    if matches:
        return {"term": term, "found": False, "suggestions": matches}

    return {"term": term, "found": False, "error": f"Concept '{term}' not found in semantic index"}


def get_dsl_patterns() -> dict[str, Any]:
    """
    Get all available DSL patterns with examples.

    Returns:
        Dictionary of pattern names to their definitions and examples
    """
    index = get_semantic_index()
    return {
        "patterns": index["patterns"],
        "hint": "Each pattern includes a complete, copy-paste ready example",
    }


def reload_cache() -> None:
    """Re-seed the Knowledge Graph from TOML files.

    Also clears the TOML cache so that if the KG is not initialized the
    next ``get_semantic_index()`` call will re-read from disk.
    """
    global _semantic_cache
    _semantic_cache = None

    graph = _get_kg()
    if graph is not None:
        from dazzle.mcp.knowledge_graph.seed import seed_framework_knowledge

        seed_framework_knowledge(graph)


__all__ = [
    "get_mcp_version",
    "get_semantic_index",
    "lookup_concept",
    "get_dsl_patterns",
    "reload_cache",
    "MCP_SEMANTICS_VERSION",
    "MCP_SEMANTICS_BUILD",
]
