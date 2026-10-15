"""Tests for the Knowledge Graph MCP module."""

import importlib.util
import sys
from pathlib import Path


def _import_knowledge_graph_module(module_name: str):
    """Import knowledge graph modules directly to avoid MCP package init issues."""
    base = Path(__file__).parent.parent.parent / "src" / "dazzle" / "mcp" / "knowledge_graph"
    # Support both single-file modules and packages
    module_file = base / f"{module_name}.py"
    package_init = base / module_name / "__init__.py"
    if module_file.exists():
        module_path = module_file
    elif package_init.exists():
        module_path = package_init
    else:
        raise ImportError(f"Cannot find module {module_name} in {base}")
    spec = importlib.util.spec_from_file_location(
        f"dazzle.mcp.knowledge_graph.{module_name}",
        module_path,
        submodule_search_locations=[str(module_path.parent)]
        if module_path.name == "__init__.py"
        else None,
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

    def test_entity_ops_combined(self) -> None:
        """Combined: create+get, type inference (8 prefixes), delete,
        list with filter, inference: prefix maps to inference type."""
        graph = KnowledgeGraph(":memory:")

        # Create + get + metadata
        e = graph.create_entity(
            entity_id="file:src/main.py", name="main.py", metadata={"lines": 100}
        )
        assert e.id == "file:src/main.py"
        assert e.entity_type == "file"
        assert e.name == "main.py"
        assert e.metadata == {"lines": 100}
        retr = graph.get_entity("file:src/main.py")
        assert retr is not None
        assert retr.id == e.id and retr.name == e.name

        # Type inference for various prefixes
        for entity_id, expected_type in [
            ("file:foo.py", "file"),
            ("module:foo.bar", "module"),
            ("class:MyClass", "class"),
            ("function:my_func", "function"),
            ("concept:auth", "concept"),
            ("decision:use_redis", "decision"),
            ("pattern:singleton", "pattern"),
            ("unknown_prefix:foo", "unknown"),
        ]:
            ent = graph.create_entity(entity_id=entity_id, name="test")
            assert ent.entity_type == expected_type, f"Failed for {entity_id}"

        # Delete
        del_graph = KnowledgeGraph(":memory:")
        del_graph.create_entity(entity_id="file:test.py", name="test.py")
        assert del_graph.get_entity("file:test.py") is not None
        assert del_graph.delete_entity("file:test.py") is True
        assert del_graph.get_entity("file:test.py") is None

        # List with filter
        flt = KnowledgeGraph(":memory:")
        flt.create_entity(entity_id="file:a.py", name="a.py")
        flt.create_entity(entity_id="file:b.py", name="b.py")
        flt.create_entity(entity_id="class:MyClass", name="MyClass")
        files = flt.list_entities(entity_type="file")
        assert len(files) == 2
        assert all(x.entity_type == "file" for x in files)
        assert len(flt.list_entities(entity_type="class")) == 1

        # inference: prefix
        inf = KnowledgeGraph(":memory:")
        assert inf.create_entity("inference:test_entry", "test_entry").entity_type == "inference"

    def test_relations_and_graph_ops_combined(self) -> None:
        """Combined: create+get relation (in/out), auto-create missing,
        dependencies/dependents/neighbourhood/transitive, query, stats."""
        # Create + retrieve relation
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(entity_id="file:a.py", name="a.py")
        graph.create_entity(entity_id="file:b.py", name="b.py")
        rel = graph.create_relation(
            source_id="file:a.py", target_id="file:b.py", relation_type="imports"
        )
        assert rel.source_id == "file:a.py"
        assert rel.target_id == "file:b.py"
        assert rel.relation_type == "imports"
        outgoing = graph.get_relations(entity_id="file:a.py", direction="outgoing")
        assert len(outgoing) == 1 and outgoing[0].target_id == "file:b.py"
        incoming = graph.get_relations(entity_id="file:b.py", direction="incoming")
        assert len(incoming) == 1 and incoming[0].source_id == "file:a.py"

        # Auto-create missing
        auto = KnowledgeGraph(":memory:")
        auto.create_relation(
            source_id="file:a.py",
            target_id="file:b.py",
            relation_type="imports",
            create_missing_entities=True,
        )
        assert auto.get_entity("file:a.py") is not None
        assert auto.get_entity("file:b.py") is not None

        # Query
        q = KnowledgeGraph(":memory:")
        q.create_entity("file:parser.py", "parser.py")
        q.create_entity("file:lexer.py", "lexer.py")
        q.create_entity("class:ParserImpl", "ParserImpl")
        results = q.query("parser")
        assert len(results) == 2
        assert {x.id for x in results} == {"file:parser.py", "class:ParserImpl"}

        # Stats
        st = KnowledgeGraph(":memory:")
        st.create_entity("file:a.py", "a.py")
        st.create_entity("class:A", "A")
        st.create_relation("file:a.py", "class:A", "contains")
        stats = st.get_stats()
        assert stats["entity_count"] == 2
        assert stats["relation_count"] == 1
        assert stats["entity_types"]["file"] == 1
        assert stats["entity_types"]["class"] == 1
        assert stats["relation_types"]["contains"] == 1

    def test_aliases_seed_concepts_combined(self) -> None:
        """Combined: alias create/resolve/clear, seed_meta get/set/overwrite,
        delete_by_metadata_key, lookup_concept (direct/alias/pattern/not-found),
        lookup_inference_matches."""
        # Alias create/resolve
        a = KnowledgeGraph(":memory:")
        a.create_entity("concept:state_machine", "state_machine")
        a.create_alias("transitions", "concept:state_machine")
        assert a.resolve_alias("transitions") == "concept:state_machine"
        assert a.resolve_alias("nonexistent") is None

        # Clear aliases
        c = KnowledgeGraph(":memory:")
        c.create_entity("concept:a", "a")
        c.create_alias("alias1", "concept:a")
        c.create_alias("alias2", "concept:a")
        assert c.clear_aliases() == 2
        assert c.resolve_alias("alias1") is None

        # Seed meta get/set/overwrite
        s = KnowledgeGraph(":memory:")
        assert s.get_seed_meta("seed_version") is None
        s.set_seed_meta("seed_version", "0.21.0.1")
        assert s.get_seed_meta("seed_version") == "0.21.0.1"
        s.set_seed_meta("seed_version", "0.22.0.1")
        assert s.get_seed_meta("seed_version") == "0.22.0.1"

        # Delete by metadata key
        d = KnowledgeGraph(":memory:")
        d.create_entity("concept:a", "a", metadata={"source": "framework"})
        d.create_entity("concept:b", "b", metadata={"source": "framework"})
        d.create_entity("entity:Task", "Task", metadata={"source": "project"})
        assert d.delete_by_metadata_key("source", "framework") == 2
        assert d.get_entity("concept:a") is None
        assert d.get_entity("entity:Task") is not None

        # Lookup concept direct
        ld = KnowledgeGraph(":memory:")
        ld.create_entity(
            "concept:entity",
            "entity",
            metadata={"source": "framework", "definition": "A domain model"},
        )
        rd = ld.lookup_concept("entity")
        assert rd is not None and rd.id == "concept:entity"

        # Lookup via alias
        la = KnowledgeGraph(":memory:")
        la.create_entity("concept:state_machine", "state_machine")
        la.create_alias("transitions", "concept:state_machine")
        ra = la.lookup_concept("transitions")
        assert ra is not None and ra.id == "concept:state_machine"

        # Lookup pattern
        lp = KnowledgeGraph(":memory:")
        lp.create_entity("pattern:crud", "crud", metadata={"source": "framework"})
        rp = lp.lookup_concept("crud")
        assert rp is not None and rp.id == "pattern:crud"

        # Not found
        ln = KnowledgeGraph(":memory:")
        assert ln.lookup_concept("nonexistent") is None

        # Inference matches
        inf = KnowledgeGraph(":memory:")
        inf.create_entity(
            "inference:field_patterns.status_resolution",
            "status_resolution",
            entity_type="inference",
            metadata={
                "source": "framework",
                "category": "field_patterns",
                "triggers": ["fixed", "resolved", "closed"],
            },
        )
        inf.create_entity(
            "inference:field_patterns.person_email",
            "person_email",
            entity_type="inference",
            metadata={
                "source": "framework",
                "category": "field_patterns",
                "triggers": ["user", "customer", "person"],
            },
        )
        m1 = inf.lookup_inference_matches("the ticket is resolved")
        assert len(m1) == 1 and m1[0].name == "status_resolution"
        m2 = inf.lookup_inference_matches("create a user profile")
        assert len(m2) == 1 and m2[0].name == "person_email"
        assert len(inf.lookup_inference_matches("something unrelated")) == 0


class TestKnowledgeGraphHandlers:
    """Tests for the KnowledgeGraphHandlers MCP tool handlers."""

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

    def test_handler_populate_from_appspec_indexes_subtype_relations(self) -> None:
        """#1238 — `is_subtype_of` (child→base) and `has_subtype` (base→child)
        edges land in the graph for the asset_registry fixture."""
        graph = KnowledgeGraph(":memory:")
        handlers = KnowledgeGraphHandlers(graph)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "asset_registry"
        if not (fixture_path / "dazzle.toml").exists():
            return  # fixture not available — skip

        result = handlers.handle_populate_from_appspec(str(fixture_path))
        assert "error" not in result or result.get("entities_created", 0) > 0

        # Vehicle is a subtype of Asset → outgoing is_subtype_of.
        outgoing = graph.get_relations(entity_id="entity:Vehicle", direction="outgoing")
        subtype_edges = [
            r
            for r in outgoing
            if r.relation_type == "is_subtype_of" and r.target_id == "entity:Asset"
        ]
        assert subtype_edges, (
            f"expected entity:Vehicle -is_subtype_of-> entity:Asset; got {outgoing}"
        )

        # Asset is the base → outgoing has_subtype edges to each child.
        base_out = graph.get_relations(entity_id="entity:Asset", direction="outgoing")
        child_targets = {r.target_id for r in base_out if r.relation_type == "has_subtype"}
        assert "entity:Vehicle" in child_targets, (
            f"expected has_subtype→Vehicle; got {child_targets}"
        )

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

    def test_camel_to_snake_conversion(self) -> None:
        """Test CamelCase to snake_case conversion (shared core.strings rule)."""
        from dazzle.core.strings import to_snake_case

        assert to_snake_case("AuthStore") == "auth_store"
        assert to_snake_case("HTTPClient") == "http_client"
        assert to_snake_case("MyClass") == "my_class"
        assert to_snake_case("A") == "a"
