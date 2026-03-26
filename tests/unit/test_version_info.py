"""Tests for version_info in concept lookup responses."""

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
KnowledgeGraph = _store_module.KnowledgeGraph


class TestVersionInfoInConceptLookup:
    """Tests for version_info extraction from KG concept metadata."""

    def test_concept_with_since_version(self) -> None:
        """Concept with since_version gets version_info.since in response."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(
            entity_id="concept:test_feature",
            name="test_feature",
            entity_type="concept",
            metadata={
                "source": "framework",
                "category": "Test",
                "definition": "A test feature",
                "since_version": "0.48.0",
            },
        )
        entity = graph.get_entity("concept:test_feature")
        meta = entity.metadata
        assert meta["since_version"] == "0.48.0"

    def test_concept_with_changed_in(self) -> None:
        """Concept with changed_in gets version_info.changes in response."""
        graph = KnowledgeGraph(":memory:")
        changed_in = [
            {"version": "0.48.12", "note": "Added declaration headers"},
            {"version": "0.48.5", "note": "Initial support"},
        ]
        graph.create_entity(
            entity_id="concept:test_feature",
            name="test_feature",
            entity_type="concept",
            metadata={
                "source": "framework",
                "category": "Test",
                "definition": "A test feature",
                "changed_in": changed_in,
            },
        )
        entity = graph.get_entity("concept:test_feature")
        meta = entity.metadata
        assert meta["changed_in"] == changed_in

    def test_concept_without_version_info(self) -> None:
        """Concept without version fields has no version info in metadata."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(
            entity_id="concept:old_feature",
            name="old_feature",
            entity_type="concept",
            metadata={
                "source": "framework",
                "category": "Test",
                "definition": "An old feature",
            },
        )
        entity = graph.get_entity("concept:old_feature")
        meta = entity.metadata
        assert "since_version" not in meta
        assert "changed_in" not in meta


class TestVersionFieldsInSeed:
    """Tests that seed pipeline passes through since_version and changed_in."""

    def test_seed_passes_through_since_version(self) -> None:
        """Concepts with since_version in TOML have it in KG metadata after seeding."""
        _seed_module = _import_knowledge_graph_module("seed")
        graph = KnowledgeGraph(":memory:")
        _seed_module.seed_framework_knowledge(graph)

        entity = graph.get_entity("concept:feedback_widget")
        assert entity is not None
        meta = entity.metadata
        assert meta.get("since_version") == "0.48.0"

    def test_seed_passes_through_changed_in(self) -> None:
        """Concepts with changed_in in TOML have it in KG metadata after seeding."""
        _seed_module = _import_knowledge_graph_module("seed")
        graph = KnowledgeGraph(":memory:")
        _seed_module.seed_framework_knowledge(graph)

        entity = graph.get_entity("concept:feedback_widget")
        assert entity is not None
        meta = entity.metadata
        changed_in = meta.get("changed_in")
        assert isinstance(changed_in, list)
        assert len(changed_in) >= 1
        assert changed_in[0]["version"]
        assert changed_in[0]["note"]
