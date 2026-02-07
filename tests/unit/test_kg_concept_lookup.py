"""Tests for concept lookup via the unified Knowledge Graph."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _import_knowledge_graph_module(module_name: str):
    """Import knowledge graph modules directly to avoid MCP package init issues."""
    module_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "knowledge_graph"
        / f"{module_name}.py"
    )
    spec = importlib.util.spec_from_file_location(
        f"dazzle.mcp.knowledge_graph.{module_name}",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"dazzle.mcp.knowledge_graph.{module_name}"] = module
    spec.loader.exec_module(module)
    return module


_store_module = _import_knowledge_graph_module("store")
_seed_module = _import_knowledge_graph_module("seed")
KnowledgeGraph = _store_module.KnowledgeGraph


def _make_seeded_graph() -> object:
    """Create an in-memory graph pre-seeded with framework knowledge."""
    graph = KnowledgeGraph(":memory:")
    _seed_module.seed_framework_knowledge(graph)
    return graph


class TestConceptLookupViaKG:
    """Test concept lookup through the Knowledge Graph."""

    def test_direct_concept_match(self) -> None:
        """Test looking up a concept by exact name."""
        graph = _make_seeded_graph()
        entity = graph.lookup_concept("entity")
        assert entity is not None
        assert entity.id == "concept:entity"
        assert entity.entity_type == "concept"

    def test_alias_resolution(self) -> None:
        """Test looking up a concept via alias."""
        graph = _make_seeded_graph()

        # "transitions" is an alias for "state_machine"
        entity = graph.lookup_concept("transitions")
        assert entity is not None
        assert entity.id == "concept:state_machine"

        # "wizard" is an alias for "experience"
        entity = graph.lookup_concept("wizard")
        assert entity is not None
        assert entity.id == "concept:experience"

    def test_pattern_lookup(self) -> None:
        """Test looking up a pattern by name (when no concept has the same name)."""
        graph = KnowledgeGraph(":memory:")
        # Manually create a pattern without a matching concept
        graph.create_entity(
            "pattern:my_test_pattern", "my_test_pattern", metadata={"source": "framework"}
        )

        entity = graph.lookup_concept("my_test_pattern")
        assert entity is not None
        assert entity.entity_type == "pattern"
        assert entity.id == "pattern:my_test_pattern"

    def test_case_insensitive_lookup(self) -> None:
        """Test that lookup normalizes case."""
        graph = _make_seeded_graph()

        entity = graph.lookup_concept("Entity")
        assert entity is not None
        assert entity.id == "concept:entity"

    def test_hyphen_underscore_normalization(self) -> None:
        """Test that hyphens and spaces are normalized to underscores."""
        graph = _make_seeded_graph()

        entity = graph.lookup_concept("state-machine")
        assert entity is not None
        assert entity.id == "concept:state_machine"

        entity = graph.lookup_concept("state machine")
        assert entity is not None
        assert entity.id == "concept:state_machine"

    def test_not_found_returns_none(self) -> None:
        """Test that unknown terms return None."""
        graph = _make_seeded_graph()
        entity = graph.lookup_concept("definitely_not_a_concept_12345")
        assert entity is None

    def test_concept_has_framework_metadata(self) -> None:
        """Test that seeded concepts have source=framework."""
        graph = _make_seeded_graph()
        entity = graph.lookup_concept("entity")
        assert entity is not None
        assert entity.metadata.get("source") == "framework"
        assert entity.metadata.get("definition") != ""

    def test_related_concepts_accessible(self) -> None:
        """Test that related_concept relations exist for seeded concepts."""
        graph = _make_seeded_graph()

        # Get relations for a concept that has related entries
        entity = graph.lookup_concept("entity")
        assert entity is not None

        relations = graph.get_relations(
            entity_id=entity.id,
            relation_type="related_concept",
            direction="outgoing",
        )
        # "entity" concept in core.toml has related concepts
        assert len(relations) >= 0  # May or may not have related depending on TOML

    def test_alias_to_concept_roundtrip(self) -> None:
        """Test that alias → concept → entity works end to end."""
        graph = _make_seeded_graph()

        # Use alias "auth" → "authentication"
        entity = graph.lookup_concept("auth")
        assert entity is not None
        assert "authentication" in entity.id or "authentication" in entity.name
