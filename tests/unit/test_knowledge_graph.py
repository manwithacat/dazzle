"""Tests for the Knowledge Graph MCP module."""

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
_handlers_module = _import_knowledge_graph_module("handlers")
KnowledgeGraph = _store_module.KnowledgeGraph
KnowledgeGraphHandlers = _handlers_module.KnowledgeGraphHandlers


class TestKnowledgeGraphStore:
    """Tests for the KnowledgeGraph store."""

    def test_create_and_get_entity(self) -> None:
        """Test creating and retrieving an entity."""
        graph = KnowledgeGraph(":memory:")
        entity = graph.create_entity(
            entity_id="file:src/main.py",
            name="main.py",
            metadata={"lines": 100},
        )

        assert entity.id == "file:src/main.py"
        assert entity.entity_type == "file"  # Inferred from prefix
        assert entity.name == "main.py"
        assert entity.metadata == {"lines": 100}

        # Retrieve
        retrieved = graph.get_entity("file:src/main.py")
        assert retrieved is not None
        assert retrieved.id == entity.id
        assert retrieved.name == entity.name

    def test_entity_type_inference(self) -> None:
        """Test that entity types are inferred from ID prefixes."""
        graph = KnowledgeGraph(":memory:")

        test_cases = [
            ("file:foo.py", "file"),
            ("module:foo.bar", "module"),
            ("class:MyClass", "class"),
            ("function:my_func", "function"),
            ("concept:auth", "concept"),
            ("decision:use_redis", "decision"),
            ("pattern:singleton", "pattern"),
            ("unknown_prefix:foo", "unknown"),
        ]

        for entity_id, expected_type in test_cases:
            entity = graph.create_entity(entity_id=entity_id, name="test")
            assert entity.entity_type == expected_type, f"Failed for {entity_id}"

    def test_delete_entity(self) -> None:
        """Test deleting an entity."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(entity_id="file:test.py", name="test.py")

        assert graph.get_entity("file:test.py") is not None
        deleted = graph.delete_entity("file:test.py")
        assert deleted is True
        assert graph.get_entity("file:test.py") is None

    def test_list_entities_with_filter(self) -> None:
        """Test listing entities with type filter."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(entity_id="file:a.py", name="a.py")
        graph.create_entity(entity_id="file:b.py", name="b.py")
        graph.create_entity(entity_id="class:MyClass", name="MyClass")

        files = graph.list_entities(entity_type="file")
        assert len(files) == 2
        assert all(e.entity_type == "file" for e in files)

        classes = graph.list_entities(entity_type="class")
        assert len(classes) == 1

    def test_create_and_get_relation(self) -> None:
        """Test creating and retrieving relations."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(entity_id="file:a.py", name="a.py")
        graph.create_entity(entity_id="file:b.py", name="b.py")

        relation = graph.create_relation(
            source_id="file:a.py",
            target_id="file:b.py",
            relation_type="imports",
        )

        assert relation.source_id == "file:a.py"
        assert relation.target_id == "file:b.py"
        assert relation.relation_type == "imports"

        # Get outgoing relations
        outgoing = graph.get_relations(entity_id="file:a.py", direction="outgoing")
        assert len(outgoing) == 1
        assert outgoing[0].target_id == "file:b.py"

        # Get incoming relations
        incoming = graph.get_relations(entity_id="file:b.py", direction="incoming")
        assert len(incoming) == 1
        assert incoming[0].source_id == "file:a.py"

    def test_auto_create_missing_entities(self) -> None:
        """Test that relations auto-create missing entities."""
        graph = KnowledgeGraph(":memory:")

        # Create relation without pre-creating entities
        graph.create_relation(
            source_id="file:a.py",
            target_id="file:b.py",
            relation_type="imports",
            create_missing_entities=True,
        )

        # Both entities should exist now
        assert graph.get_entity("file:a.py") is not None
        assert graph.get_entity("file:b.py") is not None

    def test_get_dependencies(self) -> None:
        """Test getting entities that this entity depends on."""
        graph = KnowledgeGraph(":memory:")
        graph.create_relation("file:a.py", "module:os", "imports")
        graph.create_relation("file:a.py", "module:sys", "imports")
        graph.create_relation("file:a.py", "file:b.py", "imports")

        deps = graph.get_dependencies("file:a.py")
        dep_ids = {e.id for e in deps}
        assert dep_ids == {"module:os", "module:sys", "file:b.py"}

    def test_get_dependents(self) -> None:
        """Test getting entities that depend on this entity."""
        graph = KnowledgeGraph(":memory:")
        graph.create_relation("file:a.py", "module:utils", "imports")
        graph.create_relation("file:b.py", "module:utils", "imports")
        graph.create_relation("file:c.py", "module:utils", "imports")

        dependents = graph.get_dependents("module:utils")
        dependent_ids = {e.id for e in dependents}
        assert dependent_ids == {"file:a.py", "file:b.py", "file:c.py"}

    def test_get_neighbourhood(self) -> None:
        """Test getting neighbourhood of an entity."""
        graph = KnowledgeGraph(":memory:")
        # Create a simple graph: a -> b -> c
        graph.create_relation("file:a.py", "file:b.py", "imports")
        graph.create_relation("file:b.py", "file:c.py", "imports")

        # Depth 1 from b should include a and c
        result = graph.get_neighbourhood("file:b.py", depth=1)
        entity_ids = {e.id for e in result["entities"]}
        assert "file:a.py" in entity_ids
        assert "file:b.py" in entity_ids
        assert "file:c.py" in entity_ids

    def test_transitive_dependencies(self) -> None:
        """Test getting transitive dependencies."""
        graph = KnowledgeGraph(":memory:")
        # a -> b -> c -> d
        graph.create_relation("file:a.py", "file:b.py", "imports")
        graph.create_relation("file:b.py", "file:c.py", "imports")
        graph.create_relation("file:c.py", "file:d.py", "imports")

        # Direct dependencies of a
        direct = graph.get_dependencies("file:a.py", transitive=False)
        assert len(direct) == 1
        assert direct[0].id == "file:b.py"

        # Transitive dependencies of a
        transitive = graph.get_dependencies("file:a.py", transitive=True)
        trans_ids = {e.id for e in transitive}
        assert trans_ids == {"file:b.py", "file:c.py", "file:d.py"}

    def test_query_entities(self) -> None:
        """Test searching entities by text."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity("file:parser.py", "parser.py")
        graph.create_entity("file:lexer.py", "lexer.py")
        graph.create_entity("class:ParserImpl", "ParserImpl")

        results = graph.query("parser")
        assert len(results) == 2
        result_ids = {e.id for e in results}
        assert "file:parser.py" in result_ids
        assert "class:ParserImpl" in result_ids

    def test_get_stats(self) -> None:
        """Test getting graph statistics."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity("file:a.py", "a.py")
        graph.create_entity("class:A", "A")
        graph.create_relation("file:a.py", "class:A", "contains")

        stats = graph.get_stats()
        assert stats["entity_count"] == 2
        assert stats["relation_count"] == 1
        assert stats["entity_types"]["file"] == 1
        assert stats["entity_types"]["class"] == 1
        assert stats["relation_types"]["contains"] == 1

    def test_inference_type_prefix(self) -> None:
        """Test that inference: prefix maps to inference type."""
        graph = KnowledgeGraph(":memory:")
        entity = graph.create_entity("inference:test_entry", "test_entry")
        assert entity.entity_type == "inference"

    def test_create_and_resolve_alias(self) -> None:
        """Test alias creation and resolution."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity("concept:state_machine", "state_machine")
        graph.create_alias("transitions", "concept:state_machine")

        resolved = graph.resolve_alias("transitions")
        assert resolved == "concept:state_machine"

        # Non-existent alias
        assert graph.resolve_alias("nonexistent") is None

    def test_clear_aliases(self) -> None:
        """Test clearing all aliases."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity("concept:a", "a")
        graph.create_alias("alias1", "concept:a")
        graph.create_alias("alias2", "concept:a")

        count = graph.clear_aliases()
        assert count == 2
        assert graph.resolve_alias("alias1") is None

    def test_seed_meta(self) -> None:
        """Test seed metadata get/set."""
        graph = KnowledgeGraph(":memory:")

        assert graph.get_seed_meta("seed_version") is None

        graph.set_seed_meta("seed_version", "0.21.0.1")
        assert graph.get_seed_meta("seed_version") == "0.21.0.1"

        # Overwrite
        graph.set_seed_meta("seed_version", "0.22.0.1")
        assert graph.get_seed_meta("seed_version") == "0.22.0.1"

    def test_delete_by_metadata_key(self) -> None:
        """Test bulk deletion by metadata key."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity("concept:a", "a", metadata={"source": "framework"})
        graph.create_entity("concept:b", "b", metadata={"source": "framework"})
        graph.create_entity("entity:Task", "Task", metadata={"source": "project"})

        deleted = graph.delete_by_metadata_key("source", "framework")
        assert deleted == 2
        assert graph.get_entity("concept:a") is None
        assert graph.get_entity("entity:Task") is not None

    def test_lookup_concept_direct(self) -> None:
        """Test concept lookup by direct name."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(
            "concept:entity",
            "entity",
            metadata={"source": "framework", "definition": "A domain model"},
        )

        result = graph.lookup_concept("entity")
        assert result is not None
        assert result.id == "concept:entity"

    def test_lookup_concept_via_alias(self) -> None:
        """Test concept lookup via alias."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity("concept:state_machine", "state_machine")
        graph.create_alias("transitions", "concept:state_machine")

        result = graph.lookup_concept("transitions")
        assert result is not None
        assert result.id == "concept:state_machine"

    def test_lookup_concept_pattern(self) -> None:
        """Test concept lookup falls back to patterns."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity("pattern:crud", "crud", metadata={"source": "framework"})

        result = graph.lookup_concept("crud")
        assert result is not None
        assert result.id == "pattern:crud"

    def test_lookup_concept_not_found(self) -> None:
        """Test concept lookup returns None for unknown terms."""
        graph = KnowledgeGraph(":memory:")
        assert graph.lookup_concept("nonexistent") is None

    def test_lookup_inference_matches(self) -> None:
        """Test inference trigger matching."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(
            "inference:field_patterns.status_resolution",
            "status_resolution",
            entity_type="inference",
            metadata={
                "source": "framework",
                "category": "field_patterns",
                "triggers": ["fixed", "resolved", "closed"],
            },
        )
        graph.create_entity(
            "inference:field_patterns.person_email",
            "person_email",
            entity_type="inference",
            metadata={
                "source": "framework",
                "category": "field_patterns",
                "triggers": ["user", "customer", "person"],
            },
        )

        # Should match "resolved"
        matches = graph.lookup_inference_matches("the ticket is resolved")
        assert len(matches) == 1
        assert matches[0].name == "status_resolution"

        # Should match "user"
        matches = graph.lookup_inference_matches("create a user profile")
        assert len(matches) == 1
        assert matches[0].name == "person_email"

        # Should match nothing
        matches = graph.lookup_inference_matches("something unrelated")
        assert len(matches) == 0


class TestKnowledgeGraphHandlers:
    """Tests for the KnowledgeGraphHandlers MCP tool handlers."""

    def test_handler_create_entity(self) -> None:
        """Test create_entity handler."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        result = handlers.handle_create_entity(
            entity_id="concept:authentication",
            name="Authentication",
            metadata={"description": "User auth"},
        )

        assert result["id"] == "concept:authentication"
        assert result["name"] == "Authentication"
        assert result["type"] == "concept"

    def test_handler_get_relations(self) -> None:
        """Test get_relations handler."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        handlers.handle_create_relation(
            source_id="file:a.py",
            target_id="module:os",
            relation_type="imports",
        )

        result = handlers.handle_get_relations(entity_id="file:a.py")
        assert result["count"] == 1
        assert result["relations"][0]["target_id"] == "module:os"

    def test_handler_dispatch(self) -> None:
        """Test the dispatch method routes to correct handlers."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        # Test dispatching to create_entity
        result = handlers.dispatch(
            "kg_create_entity",
            {"entity_id": "file:test.py", "name": "test.py"},
        )
        assert result["id"] == "file:test.py"

        # Test dispatching to get_entity
        result = handlers.dispatch("kg_get_entity", {"entity_id": "file:test.py"})
        assert result["name"] == "test.py"

        # Test unknown tool
        result = handlers.dispatch("kg_unknown", {})
        assert "error" in result

    def test_handler_tool_definitions(self) -> None:
        """Test that tool definitions are properly structured."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        tools = handlers.get_tool_definitions()

        # Check we have the expected tools
        tool_names = {t["name"] for t in tools}
        expected_tools = {
            "kg_create_entity",
            "kg_get_entity",
            "kg_delete_entity",
            "kg_list_entities",
            "kg_create_relation",
            "kg_delete_relation",
            "kg_get_relations",
            "kg_find_paths",
            "kg_get_neighbourhood",
            "kg_get_dependents",
            "kg_get_dependencies",
            "kg_query",
            "kg_query_sql",
            "kg_auto_populate",
            "kg_stats",
            "kg_populate_appspec",
            "kg_populate_mcp_tools",
            "kg_populate_test_coverage",
            "kg_compute_adjacency",
            "kg_persona_capability_map",
        }
        assert tool_names == expected_tools

        # Check each tool has required fields
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    def test_handler_get_stats(self) -> None:
        """Test stats handler returns proper format."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        # Add some data
        handlers.handle_create_entity(entity_id="file:a.py", name="a.py")
        handlers.handle_create_entity(entity_id="class:Foo", name="Foo")
        handlers.handle_create_relation(
            source_id="file:a.py",
            target_id="class:Foo",
            relation_type="contains",
        )

        result = handlers.handle_get_stats()
        assert result["entity_count"] == 2
        assert result["relation_count"] == 1

    def test_handler_populate_from_appspec(self) -> None:
        """Test populating graph from DAZZLE DSL project."""

        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        # Use the simple_task example project
        project_path = Path(__file__).parent.parent.parent / "examples" / "simple_task"

        if not (project_path / "dazzle.toml").exists():
            # Skip if example project not available
            return

        result = handlers.handle_populate_from_appspec(str(project_path))

        # Should have created entities and surfaces
        assert "error" not in result or result.get("entities_created", 0) > 0
        if "entities_created" in result:
            assert result["entities_created"] > 0

            # Query for the Task entity
            entities = graph.query("Task", entity_types=["dsl_entity"])
            assert len(entities) > 0

    def test_handler_populate_from_appspec_invalid_path(self) -> None:
        """Test populate from appspec with invalid path."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        result = handlers.handle_populate_from_appspec("/nonexistent/path")
        assert "error" in result

    def test_handler_populate_from_appspec_no_manifest(self, tmp_path) -> None:
        """Test populate from appspec with no dazzle.toml."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        result = handlers.handle_populate_from_appspec(str(tmp_path))
        assert "error" in result
        assert "dazzle.toml" in result["error"]

    def test_handler_populate_mcp_tools(self) -> None:
        """Test populating graph with MCP tool definitions."""
        from unittest.mock import MagicMock, patch

        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        # Create mock tools with the structure expected from mcp.types.Tool
        mock_tool_1 = MagicMock()
        mock_tool_1.name = "user_management"
        mock_tool_1.description = "List, create, update, and delete users"
        mock_tool_1.inputSchema = {
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["operation"],
        }

        mock_tool_2 = MagicMock()
        mock_tool_2.name = "dsl"
        mock_tool_2.description = "Validate and inspect DSL files"
        mock_tool_2.inputSchema = {
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
            },
            "required": ["operation"],
        }

        # Mock the module that get_all_tools is imported from
        mock_tools_module = MagicMock()
        mock_tools_module.get_all_tools = MagicMock(return_value=[mock_tool_1, mock_tool_2])

        with patch.dict(sys.modules, {"dazzle.mcp.server.tools": mock_tools_module}):
            result = handlers.handle_populate_mcp_tools()

        assert "error" not in result or result.get("tools_created", 0) > 0
        if "tools_created" in result:
            assert result["tools_created"] == 2

            # Query for the user_management tool
            entities = graph.query("user_management", entity_types=["mcp_tool"])
            assert len(entities) > 0
            assert entities[0].id == "tool:user_management"

    def test_handler_populate_mcp_tools_extracts_operations(self) -> None:
        """Test that operations are extracted from tool descriptions."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        # Test the operation extraction helper directly
        description = "List, create, update, and delete users. Also supports search and query."
        operations = handlers._extract_operations_from_description(description)

        assert "list" in operations
        assert "create" in operations
        assert "update" in operations
        assert "delete" in operations
        assert "search" in operations
        assert "query" in operations

    def test_handler_populate_test_coverage(self, tmp_path) -> None:
        """Test populating graph with test coverage information."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        # Create a test file in the temp directory
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        test_content = '''"""Tests for auth module."""

class TestAuthStore:
    """Test auth store operations."""

    def test_create_user(self):
        pass

    def test_login(self):
        pass


class TestSessionManager:
    """Test session management."""

    def test_create_session(self):
        pass
'''
        (tests_dir / "test_auth.py").write_text(test_content)

        # Run the handler
        result = handlers.handle_populate_test_coverage(str(tests_dir))

        # Check stats
        assert result["test_files_created"] == 1
        assert result["test_classes_found"] == 2
        assert result["coverage_relations_created"] >= 1

        # Verify the test file entity was created
        entities = graph.query("auth", entity_types=["test_file"])
        assert len(entities) >= 1

    def test_handler_populate_test_coverage_invalid_path(self) -> None:
        """Test populate test coverage with invalid path."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        result = handlers.handle_populate_test_coverage("/nonexistent/path")
        assert "error" in result

    def test_camel_to_snake_conversion(self) -> None:
        """Test CamelCase to snake_case conversion."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        assert handlers._camel_to_snake("AuthStore") == "auth_store"
        assert handlers._camel_to_snake("HTTPClient") == "http_client"
        assert handlers._camel_to_snake("MyClass") == "my_class"
        assert handlers._camel_to_snake("A") == "a"

    def test_infer_covered_modules(self) -> None:
        """Test inferring covered modules from test names."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        # From test file name
        modules = handlers._infer_covered_modules("test_auth", [])
        assert "auth" in modules

        # From test class names
        modules = handlers._infer_covered_modules(
            "test_something", ["TestAuthStore", "TestUserManager"]
        )
        assert "auth_store" in modules
        assert "user_manager" in modules
