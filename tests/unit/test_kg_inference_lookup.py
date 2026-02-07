"""Tests for inference lookup via the unified Knowledge Graph."""

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


class TestInferenceLookupViaKG:
    """Test inference matching through the Knowledge Graph."""

    def test_trigger_matching_field_pattern(self) -> None:
        """Test that inference entities match on trigger words."""
        graph = _make_seeded_graph()

        # "upload" should match the file upload pattern
        matches = graph.lookup_inference_matches("upload a file")
        assert len(matches) > 0
        categories = {m.metadata.get("category") for m in matches}
        assert "field_patterns" in categories or "domain_entities" in categories

    def test_trigger_matching_person_pattern(self) -> None:
        """Test matching on person-related triggers."""
        graph = _make_seeded_graph()

        # "user" should match person_email pattern
        matches = graph.lookup_inference_matches("create a user profile")
        assert len(matches) > 0

    def test_trigger_matching_workflow(self) -> None:
        """Test matching on workflow triggers."""
        graph = _make_seeded_graph()

        # Should match some workflow or status-related patterns
        matches = graph.lookup_inference_matches("status resolved fixed")
        assert len(matches) > 0

    def test_no_matches_for_unrelated_query(self) -> None:
        """Test that unrelated queries return no matches."""
        graph = _make_seeded_graph()

        matches = graph.lookup_inference_matches("xyzzy_completely_unrelated_term_12345")
        assert len(matches) == 0

    def test_limit_parameter(self) -> None:
        """Test that limit parameter is respected."""
        graph = _make_seeded_graph()

        # A broad query should match many things
        all_matches = graph.lookup_inference_matches("user", limit=100)
        limited_matches = graph.lookup_inference_matches("user", limit=2)

        assert len(limited_matches) <= 2
        if len(all_matches) > 2:
            assert len(limited_matches) < len(all_matches)

    def test_matches_have_category_metadata(self) -> None:
        """Test that all matches have category in metadata."""
        graph = _make_seeded_graph()

        matches = graph.lookup_inference_matches("upload")
        for match in matches:
            assert "category" in match.metadata
            assert match.metadata["category"] != ""

    def test_matches_have_triggers_metadata(self) -> None:
        """Test that all matches have triggers in metadata."""
        graph = _make_seeded_graph()

        matches = graph.lookup_inference_matches("dashboard")
        for match in matches:
            assert "triggers" in match.metadata
            assert isinstance(match.metadata["triggers"], list)

    def test_inference_entities_are_framework_sourced(self) -> None:
        """Test that seeded inference entities are marked as framework."""
        graph = _make_seeded_graph()

        inference_entities = graph.list_entities(entity_type="inference", limit=10)
        for entity in inference_entities:
            assert entity.metadata.get("source") == "framework"

    def test_inference_entity_count(self) -> None:
        """Test that a reasonable number of inference entries were seeded."""
        graph = _make_seeded_graph()

        inference_entities = graph.list_entities(entity_type="inference", limit=500)
        # inference_kb.toml has ~94 entries across 10 categories
        assert len(inference_entities) >= 40, (
            f"Expected >=40 inference entities, got {len(inference_entities)}"
        )
