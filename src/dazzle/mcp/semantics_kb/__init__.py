"""
DAZZLE DSL Semantic Knowledge Base.

This package provides structured definitions, syntax examples, and relationships
for all DAZZLE DSL concepts. Data is stored in TOML files for maintainability.

Usage:
    from dazzle.mcp.semantics_kb import get_semantic_index, lookup_concept

    # Get full index
    index = get_semantic_index()

    # Look up a specific concept
    result = lookup_concept("entity")
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

# MCP Semantic Index version - reads from pyproject.toml
from dazzle._version import get_version as _get_version

MCP_SEMANTICS_VERSION = _get_version()
MCP_SEMANTICS_BUILD = 0

# Cache for loaded data
_semantic_cache: dict[str, Any] | None = None

# TOML files to load (order doesn't matter)
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

# Alias mapping for common term variations
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
}


def get_mcp_version() -> dict[str, Any]:
    """Get MCP semantic index version information."""
    return {
        "version": MCP_SEMANTICS_VERSION,
        "build": MCP_SEMANTICS_BUILD,
        "full_version": f"{MCP_SEMANTICS_VERSION}.{MCP_SEMANTICS_BUILD}",
    }


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load a single TOML file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def _load_semantic_data() -> dict[str, Any]:
    """Load and merge all TOML files into unified index."""
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


def get_semantic_index() -> dict[str, Any]:
    """
    Get the complete semantic index for DAZZLE DSL.

    Returns a structured dictionary mapping concepts to their definitions,
    syntax, examples, and related concepts.
    """
    return _load_semantic_data()


def lookup_concept(term: str) -> dict[str, Any] | None:
    """
    Look up a DAZZLE concept by name.

    Args:
        term: The concept name (e.g., 'persona', 'workspace', 'ux_block')

    Returns:
        Concept definition or None if not found
    """
    index = get_semantic_index()

    # Normalize term
    term_normalized = term.lower().replace(" ", "_").replace("-", "_")

    # Apply aliases
    term_normalized = ALIASES.get(term_normalized, term_normalized)

    # Direct lookup in concepts
    if term_normalized in index["concepts"]:
        return {
            "term": term,
            "found": True,
            "type": "concept",
            **index["concepts"][term_normalized],
        }

    # Check patterns
    if term_normalized in index["patterns"]:
        return {
            "term": term,
            "found": True,
            "type": "pattern",
            **index["patterns"][term_normalized],
        }

    # Check if asking for "pattern" or "patterns" - return all patterns
    if term_normalized in ("pattern", "patterns"):
        pattern_list = [
            {"name": name, "description": data.get("description")}
            for name, data in index["patterns"].items()
        ]
        return {
            "term": term,
            "found": True,
            "type": "pattern_list",
            "patterns": pattern_list,
            "hint": "Use lookup_concept with a specific pattern name (e.g., 'crud', 'dashboard') to get full example code",
        }

    # Search in all concepts for partial matches
    matches = []
    for concept_name, concept_data in index["concepts"].items():
        if (
            term_normalized in concept_name
            or term_normalized in concept_data.get("definition", "").lower()
        ):
            matches.append(
                {
                    "name": concept_name,
                    "category": concept_data.get("category"),
                    "definition": concept_data.get("definition"),
                }
            )

    # Also search patterns
    for pattern_name, pattern_data in index["patterns"].items():
        if (
            term_normalized in pattern_name
            or term_normalized in pattern_data.get("description", "").lower()
        ):
            matches.append(
                {
                    "name": pattern_name,
                    "type": "pattern",
                    "description": pattern_data.get("description"),
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
    """Clear the semantic cache to force reload from TOML files."""
    global _semantic_cache
    _semantic_cache = None


__all__ = [
    "get_mcp_version",
    "get_semantic_index",
    "lookup_concept",
    "get_dsl_patterns",
    "reload_cache",
    "MCP_SEMANTICS_VERSION",
    "MCP_SEMANTICS_BUILD",
]
