"""Tests for the Knowledge Graph MCP module."""

from __future__ import annotations

from dazzle.mcp.knowledge_graph import KnowledgeGraph, KnowledgeGraphHandlers


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
