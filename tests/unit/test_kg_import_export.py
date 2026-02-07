"""Tests for Knowledge Graph import/export functionality."""

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
KnowledgeGraph = _store_module.KnowledgeGraph


def _make_graph_with_data() -> KnowledgeGraph:
    """Create a graph with a mix of framework and project entities."""
    graph = KnowledgeGraph(":memory:")

    # Framework entities (should be excluded from export)
    graph.create_entity(
        "concept:entity",
        "entity",
        entity_type="concept",
        metadata={"source": "framework", "description": "A DSL entity"},
    )
    graph.create_entity(
        "concept:surface",
        "surface",
        entity_type="concept",
        metadata={"source": "framework", "description": "A DSL surface"},
    )

    # Project entities (should be included in export)
    graph.create_entity(
        "entity:Task",
        "Task",
        entity_type="dsl_entity",
        metadata={"module": "todo"},
    )
    graph.create_entity(
        "surface:task_list",
        "task_list",
        entity_type="dsl_surface",
        metadata={"module": "todo"},
    )
    graph.create_entity(
        "persona:admin",
        "admin",
        entity_type="dsl_persona",
        metadata={"label": "Administrator"},
    )

    # Relations between project entities
    graph.create_relation(
        "surface:task_list",
        "entity:Task",
        "uses",
        metadata={"mode": "list"},
        create_missing_entities=False,
    )
    graph.create_relation(
        "persona:admin",
        "surface:task_list",
        "allows_persona",
        create_missing_entities=False,
    )

    # Cross-relation (framework -> project) - should be excluded
    graph.create_relation(
        "concept:entity",
        "entity:Task",
        "exemplifies",
        create_missing_entities=False,
    )

    # Framework-only relation - should be excluded
    graph.create_relation(
        "concept:entity",
        "concept:surface",
        "related_concept",
        create_missing_entities=False,
    )

    return graph


class TestExport:
    """Tests for export_project_data()."""

    def test_export_empty_graph(self) -> None:
        """Empty graph exports empty lists."""
        graph = KnowledgeGraph(":memory:")
        data = graph.export_project_data()
        assert data["entities"] == []
        assert data["relations"] == []

    def test_export_excludes_framework_entities(self) -> None:
        """Framework entities are not included in export."""
        graph = _make_graph_with_data()
        data = graph.export_project_data()
        exported_ids = {e["id"] for e in data["entities"]}
        assert "concept:entity" not in exported_ids
        assert "concept:surface" not in exported_ids

    def test_export_includes_project_entities(self) -> None:
        """Project entities appear in export."""
        graph = _make_graph_with_data()
        data = graph.export_project_data()
        exported_ids = {e["id"] for e in data["entities"]}
        assert "entity:Task" in exported_ids
        assert "surface:task_list" in exported_ids
        assert "persona:admin" in exported_ids

    def test_export_excludes_cross_relations(self) -> None:
        """Relations touching framework entities are excluded."""
        graph = _make_graph_with_data()
        data = graph.export_project_data()
        rel_pairs = {(r["source_id"], r["target_id"]) for r in data["relations"]}
        # Cross-relation (framework -> project)
        assert ("concept:entity", "entity:Task") not in rel_pairs
        # Framework-only relation
        assert ("concept:entity", "concept:surface") not in rel_pairs

    def test_export_includes_project_relations(self) -> None:
        """Relations between project entities are included."""
        graph = _make_graph_with_data()
        data = graph.export_project_data()
        rel_pairs = {(r["source_id"], r["target_id"]) for r in data["relations"]}
        assert ("surface:task_list", "entity:Task") in rel_pairs
        assert ("persona:admin", "surface:task_list") in rel_pairs

    def test_export_format_version(self) -> None:
        """Export contains version, exported_at, and dazzle_version."""
        graph = _make_graph_with_data()
        data = graph.export_project_data()
        assert data["version"] == "1.0"
        assert "exported_at" in data
        assert "dazzle_version" in data


class TestImport:
    """Tests for import_project_data()."""

    def test_import_replace_mode(self) -> None:
        """Replace mode wipes existing project data before loading."""
        graph = _make_graph_with_data()

        new_data = {
            "version": "1.0",
            "entities": [
                {
                    "id": "entity:NewThing",
                    "entity_type": "dsl_entity",
                    "name": "NewThing",
                    "metadata": {"module": "new"},
                },
            ],
            "relations": [],
        }

        stats = graph.import_project_data(new_data, mode="replace")
        assert stats["entities_imported"] == 1

        # Old project entities should be gone
        assert graph.get_entity("entity:Task") is None
        assert graph.get_entity("surface:task_list") is None

        # New entity should exist
        assert graph.get_entity("entity:NewThing") is not None

    def test_import_merge_mode(self) -> None:
        """Merge mode adds new entities and updates existing ones."""
        graph = _make_graph_with_data()

        merge_data = {
            "version": "1.0",
            "entities": [
                {
                    "id": "entity:Task",
                    "entity_type": "dsl_entity",
                    "name": "UpdatedTask",
                    "metadata": {"module": "todo", "updated": True},
                },
                {
                    "id": "entity:Project",
                    "entity_type": "dsl_entity",
                    "name": "Project",
                    "metadata": {"module": "pm"},
                },
            ],
            "relations": [],
        }

        stats = graph.import_project_data(merge_data, mode="merge")
        assert stats["entities_imported"] == 2

        # Existing entity should be updated
        task = graph.get_entity("entity:Task")
        assert task is not None
        assert task.name == "UpdatedTask"
        assert task.metadata.get("updated") is True

        # New entity should exist
        project = graph.get_entity("entity:Project")
        assert project is not None

        # Untouched project entity should still exist
        assert graph.get_entity("surface:task_list") is not None

    def test_import_merge_skips_duplicate_relations(self) -> None:
        """Duplicate relations are skipped in merge mode."""
        graph = _make_graph_with_data()

        merge_data = {
            "version": "1.0",
            "entities": [],
            "relations": [
                {
                    "source_id": "surface:task_list",
                    "target_id": "entity:Task",
                    "relation_type": "uses",
                    "metadata": {"mode": "list"},
                },
            ],
        }

        stats = graph.import_project_data(merge_data, mode="merge")
        assert stats["relations_skipped"] == 1
        assert stats["relations_imported"] == 0

    def test_import_replace_preserves_framework(self) -> None:
        """Framework entities survive a replace import."""
        graph = _make_graph_with_data()

        new_data = {
            "version": "1.0",
            "entities": [],
            "relations": [],
        }

        graph.import_project_data(new_data, mode="replace")

        # Framework entities should still exist
        assert graph.get_entity("concept:entity") is not None
        assert graph.get_entity("concept:surface") is not None

    def test_import_roundtrip(self) -> None:
        """Export → import (replace) → export produces identical entity/relation data."""
        graph = _make_graph_with_data()

        # First export
        export1 = graph.export_project_data()

        # Create a fresh graph with only framework entities
        graph2 = KnowledgeGraph(":memory:")
        graph2.create_entity(
            "concept:entity",
            "entity",
            entity_type="concept",
            metadata={"source": "framework"},
        )

        # Import into fresh graph
        graph2.import_project_data(export1, mode="replace")

        # Second export
        export2 = graph2.export_project_data()

        # Compare entities (ignore timestamps and export metadata)
        ids1 = {e["id"] for e in export1["entities"]}
        ids2 = {e["id"] for e in export2["entities"]}
        assert ids1 == ids2

        names1 = {e["id"]: e["name"] for e in export1["entities"]}
        names2 = {e["id"]: e["name"] for e in export2["entities"]}
        assert names1 == names2

        # Compare relations
        rels1 = {(r["source_id"], r["target_id"], r["relation_type"]) for r in export1["relations"]}
        rels2 = {(r["source_id"], r["target_id"], r["relation_type"]) for r in export2["relations"]}
        assert rels1 == rels2

    def test_import_invalid_version(self) -> None:
        """Rejects unsupported version format."""
        graph = KnowledgeGraph(":memory:")
        import pytest

        with pytest.raises(ValueError, match="Unsupported export version"):
            graph.import_project_data({"version": "99.0", "entities": [], "relations": []})

    def test_import_stats(self) -> None:
        """Returns correct counts."""
        graph = KnowledgeGraph(":memory:")

        data = {
            "version": "1.0",
            "entities": [
                {
                    "id": "entity:A",
                    "entity_type": "dsl_entity",
                    "name": "A",
                    "metadata": {},
                },
                {
                    "id": "entity:B",
                    "entity_type": "dsl_entity",
                    "name": "B",
                    "metadata": {},
                },
            ],
            "relations": [
                {
                    "source_id": "entity:A",
                    "target_id": "entity:B",
                    "relation_type": "depends_on",
                    "metadata": {},
                },
            ],
        }

        stats = graph.import_project_data(data, mode="merge")
        assert stats["entities_imported"] == 2
        assert stats["relations_imported"] == 1
        assert stats["entities_skipped"] == 0
        assert stats["relations_skipped"] == 0
