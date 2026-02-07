"""Tests for the Knowledge Graph seed pipeline."""

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


class TestSeedPipeline:
    """Tests for the TOML→KG seed pipeline."""

    def test_compute_seed_version(self) -> None:
        """Test that seed version is computed correctly."""
        version = _seed_module.compute_seed_version()
        assert isinstance(version, str)
        # Should contain a dot separating dazzle version and schema version
        assert "." in version
        assert version.endswith(f".{_seed_module.SEED_SCHEMA_VERSION}")

    def test_seed_framework_knowledge_creates_concepts(self) -> None:
        """Test that seeding creates concept entities from TOML."""
        graph = KnowledgeGraph(":memory:")
        stats = _seed_module.seed_framework_knowledge(graph)

        assert stats["concepts"] > 0

        # Check that a well-known concept exists
        entity = graph.get_entity("concept:entity")
        assert entity is not None
        assert entity.entity_type == "concept"
        assert entity.metadata.get("source") == "framework"

    def test_seed_framework_knowledge_creates_patterns(self) -> None:
        """Test that seeding creates pattern entities from TOML."""
        graph = KnowledgeGraph(":memory:")
        stats = _seed_module.seed_framework_knowledge(graph)

        assert stats["patterns"] > 0

        # Check that a well-known pattern exists
        pattern_entities = graph.list_entities(entity_type="pattern", limit=500)
        assert len(pattern_entities) > 0
        assert all(e.metadata.get("source") == "framework" for e in pattern_entities)

    def test_seed_framework_knowledge_creates_inference_entries(self) -> None:
        """Test that seeding creates inference entities from TOML."""
        graph = KnowledgeGraph(":memory:")
        stats = _seed_module.seed_framework_knowledge(graph)

        assert stats["inference_entries"] > 0

        # Check inference entities exist
        inference_entities = graph.list_entities(entity_type="inference", limit=500)
        assert len(inference_entities) > 0
        # Each should have triggers in metadata
        for e in inference_entities[:5]:  # spot-check first 5
            assert e.metadata.get("source") == "framework"
            assert "category" in e.metadata

    def test_seed_framework_knowledge_creates_aliases(self) -> None:
        """Test that seeding populates the aliases table."""
        graph = KnowledgeGraph(":memory:")
        stats = _seed_module.seed_framework_knowledge(graph)

        assert stats["aliases"] > 0

        # Check well-known alias
        resolved = graph.resolve_alias("transitions")
        assert resolved == "concept:state_machine"

        resolved = graph.resolve_alias("wizard")
        assert resolved == "concept:experience"

    def test_seed_framework_knowledge_creates_relations(self) -> None:
        """Test that seeding creates concept relations."""
        graph = KnowledgeGraph(":memory:")
        stats = _seed_module.seed_framework_knowledge(graph)

        assert stats["relations"] > 0

        # Check that some related_concept relations exist
        relations = graph.get_relations(relation_type="related_concept")
        assert len(relations) > 0

    def test_seed_writes_version(self) -> None:
        """Test that seeding writes the seed version to metadata."""
        graph = KnowledgeGraph(":memory:")
        _seed_module.seed_framework_knowledge(graph)

        version = graph.get_seed_meta("seed_version")
        assert version is not None
        assert version == _seed_module.compute_seed_version()

    def test_ensure_seeded_first_time(self) -> None:
        """Test ensure_seeded seeds on first call."""
        graph = KnowledgeGraph(":memory:")

        seeded = _seed_module.ensure_seeded(graph)
        assert seeded is True

        stats = graph.get_stats()
        assert stats["entity_count"] > 0

    def test_ensure_seeded_skips_if_current(self) -> None:
        """Test ensure_seeded skips if version matches."""
        graph = KnowledgeGraph(":memory:")

        # First seed
        _seed_module.ensure_seeded(graph)

        # Second call should skip
        seeded = _seed_module.ensure_seeded(graph)
        assert seeded is False

    def test_ensure_seeded_reseeds_on_version_change(self) -> None:
        """Test ensure_seeded re-seeds when version changes."""
        graph = KnowledgeGraph(":memory:")

        # First seed
        _seed_module.ensure_seeded(graph)

        # Simulate version change by writing old version
        graph.set_seed_meta("seed_version", "old.0")

        # Should re-seed
        seeded = _seed_module.ensure_seeded(graph)
        assert seeded is True

        # Should still have framework data
        stats_after = graph.get_stats()
        assert stats_after["entity_count"] > 0

    def test_reseed_is_idempotent(self) -> None:
        """Test that seeding twice produces the same result."""
        graph = KnowledgeGraph(":memory:")

        stats1 = _seed_module.seed_framework_knowledge(graph)
        count1 = graph.get_stats()["entity_count"]

        stats2 = _seed_module.seed_framework_knowledge(graph)
        count2 = graph.get_stats()["entity_count"]

        # Counts should be identical (old data deleted, new data inserted)
        assert stats1["concepts"] == stats2["concepts"]
        assert stats1["patterns"] == stats2["patterns"]
        assert stats1["inference_entries"] == stats2["inference_entries"]
        assert count1 == count2

    def test_seed_entity_counts_are_reasonable(self) -> None:
        """Test that seed produces expected volumes of data."""
        graph = KnowledgeGraph(":memory:")
        stats = _seed_module.seed_framework_knowledge(graph)

        # Based on plan: ~61 concepts, ~24 patterns, ~94 inference entries
        # Allow some variance since TOML files can change
        assert stats["concepts"] >= 30, f"Expected >=30 concepts, got {stats['concepts']}"
        assert stats["patterns"] >= 10, f"Expected >=10 patterns, got {stats['patterns']}"
        assert stats["inference_entries"] >= 40, (
            f"Expected >=40 inference entries, got {stats['inference_entries']}"
        )
        assert stats["aliases"] >= 100, f"Expected >=100 aliases, got {stats['aliases']}"
        assert stats["relations"] >= 50, f"Expected >=50 relations, got {stats['relations']}"
