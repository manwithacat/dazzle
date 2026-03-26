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


class TestVersionInfoInHandler:
    """Tests for version_info block in knowledge handler concept response."""

    def test_handler_includes_version_info_when_present(self) -> None:
        """lookup_concept returns version_info for annotated concepts."""
        from unittest.mock import MagicMock, patch

        mock_entity = MagicMock()
        mock_entity.entity_type = "concept"
        mock_entity.metadata = {
            "source": "framework",
            "category": "Framework Feature",
            "definition": "A feature",
            "since_version": "0.48.0",
            "changed_in": [{"version": "0.48.12", "note": "Added stuff"}],
        }

        mock_graph = MagicMock()
        mock_graph.lookup_concept.return_value = mock_entity

        with patch("dazzle.mcp.semantics_kb._get_kg", return_value=mock_graph):
            from dazzle.mcp.semantics_kb import lookup_concept

            result = lookup_concept("test_feature")

        assert result["found"] is True
        assert "version_info" in result
        assert result["version_info"]["since"] == "0.48.0"
        assert len(result["version_info"]["changes"]) == 1
        assert result["version_info"]["changes"][0]["version"] == "0.48.12"

    def test_handler_omits_version_info_when_absent(self) -> None:
        """lookup_concept omits version_info for unannotated concepts."""
        from unittest.mock import MagicMock, patch

        mock_entity = MagicMock()
        mock_entity.entity_type = "concept"
        mock_entity.metadata = {
            "source": "framework",
            "category": "Core",
            "definition": "Old concept",
        }

        mock_graph = MagicMock()
        mock_graph.lookup_concept.return_value = mock_entity

        with patch("dazzle.mcp.semantics_kb._get_kg", return_value=mock_graph):
            from dazzle.mcp.semantics_kb import lookup_concept

            result = lookup_concept("old_concept")

        assert result["found"] is True
        assert "version_info" not in result


import json  # noqa: E402


class TestChangelogHandler:
    """Tests for the knowledge changelog handler operation."""

    def test_changelog_handler_returns_entries(self) -> None:
        """changelog handler returns structured entries."""
        from unittest.mock import MagicMock, patch

        mock_entities = []
        for version, guidance in [
            ("0.48.12", ["Rule A", "Rule B"]),
            ("0.48.8", ["Rule C"]),
        ]:
            entity = MagicMock()
            entity.entity_id = f"changelog:v{version}"
            entity.name = f"v{version}"
            entity.entity_type = "changelog"
            entity.metadata = {
                "source": "framework",
                "version": version,
                "guidance": guidance,
            }
            mock_entities.append(entity)

        mock_graph = MagicMock()
        mock_graph.list_entities.return_value = mock_entities

        with patch("dazzle.mcp.server.handlers.knowledge._get_kg", return_value=mock_graph):
            from dazzle.mcp.server.handlers.knowledge import get_changelog_handler

            result_str = get_changelog_handler({"_progress": MagicMock()})
            result = json.loads(result_str)

        assert "current_version" in result
        assert "entries" in result
        assert len(result["entries"]) == 2
        assert result["entries"][0]["version"] == "0.48.12"
        assert result["total_entries"] == 2

    def test_changelog_handler_respects_since(self) -> None:
        """changelog handler filters by since parameter."""
        from unittest.mock import MagicMock, patch

        mock_entities = []
        for version, guidance in [
            ("0.48.12", ["Rule A"]),
            ("0.48.8", ["Rule B"]),
            ("0.48.0", ["Rule C"]),
        ]:
            entity = MagicMock()
            entity.entity_id = f"changelog:v{version}"
            entity.name = f"v{version}"
            entity.entity_type = "changelog"
            entity.metadata = {
                "source": "framework",
                "version": version,
                "guidance": guidance,
            }
            mock_entities.append(entity)

        mock_graph = MagicMock()
        mock_graph.list_entities.return_value = mock_entities

        with patch("dazzle.mcp.server.handlers.knowledge._get_kg", return_value=mock_graph):
            from dazzle.mcp.server.handlers.knowledge import get_changelog_handler

            result_str = get_changelog_handler(
                {
                    "since": "0.48.8",
                    "_progress": MagicMock(),
                }
            )
            result = json.loads(result_str)

        versions = [e["version"] for e in result["entries"]]
        assert "0.48.0" not in versions
        assert "0.48.8" in versions
        assert "0.48.12" in versions
