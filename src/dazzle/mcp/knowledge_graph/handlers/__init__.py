"""
MCP Tool Handlers for Knowledge Graph.

Provides handlers for:
- Entity CRUD: create_entity, get_entity, delete_entity, list_entities
- Relation CRUD: create_relation, delete_relation, get_relations
- Graph traversal: find_paths, get_neighbourhood, get_dependents, get_dependencies
- Query: query, query_sql
- Auto-population: auto_populate (bootstraps from code files)

The handlers are split into focused sub-classes and composed here
for backward compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .entity_handlers import EntityHandlers
from .population_handlers import PopulationHandlers
from .query_handlers import QueryHandlers
from .relation_handlers import RelationHandlers

if TYPE_CHECKING:
    from ..store import KnowledgeGraph

__all__ = ["KnowledgeGraphHandlers"]


class KnowledgeGraphHandlers:
    """
    MCP tool handlers for knowledge graph operations.

    Designed to be low-overhead: most operations complete in single calls,
    reducing back-and-forth prompting overhead.

    Delegates to focused sub-handler classes:
    - EntityHandlers: entity CRUD
    - RelationHandlers: relation management
    - QueryHandlers: graph traversal, search, adjacency, capability maps
    - PopulationHandlers: auto-populate from code, DSL, MCP tools, tests
    """

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph
        self._entities = EntityHandlers(graph)
        self._relations = RelationHandlers(graph)
        self._queries = QueryHandlers(graph)
        self._population = PopulationHandlers(graph)

    # =========================================================================
    # Entity Handlers (delegated)
    # =========================================================================

    def handle_create_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or update an entity."""
        return self._entities.handle_create_entity(entity_id, name, entity_type, metadata)

    def handle_get_entity(self, entity_id: str) -> dict[str, Any]:
        """Get an entity by ID."""
        return self._entities.handle_get_entity(entity_id)

    def handle_delete_entity(self, entity_id: str) -> dict[str, Any]:
        """Delete an entity."""
        return self._entities.handle_delete_entity(entity_id)

    def handle_list_entities(
        self,
        entity_type: str | None = None,
        name_pattern: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List entities with filtering."""
        return self._entities.handle_list_entities(entity_type, name_pattern, limit, offset)

    # =========================================================================
    # Relation Handlers (delegated)
    # =========================================================================

    def handle_create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a relation between entities."""
        return self._relations.handle_create_relation(source_id, target_id, relation_type, metadata)

    def handle_delete_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> dict[str, Any]:
        """Delete a relation."""
        return self._relations.handle_delete_relation(source_id, target_id, relation_type)

    def handle_get_relations(
        self,
        entity_id: str | None = None,
        relation_type: str | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get relations for an entity."""
        return self._relations.handle_get_relations(entity_id, relation_type, direction)

    # =========================================================================
    # Query / Traversal Handlers (delegated)
    # =========================================================================

    def handle_find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        relation_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Find paths between two entities."""
        return self._queries.handle_find_paths(source_id, target_id, max_depth, relation_types)

    def handle_get_neighbourhood(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get neighborhood of an entity."""
        return self._queries.handle_get_neighbourhood(entity_id, depth, relation_types, direction)

    def handle_get_dependents(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        transitive: bool = False,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Get entities that depend on this entity."""
        return self._queries.handle_get_dependents(entity_id, relation_types, transitive, max_depth)

    def handle_get_dependencies(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        transitive: bool = False,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Get entities this entity depends on."""
        return self._queries.handle_get_dependencies(
            entity_id, relation_types, transitive, max_depth
        )

    def handle_query(
        self,
        text: str,
        entity_types: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search entities by text."""
        return self._queries.handle_query(text, entity_types, limit)

    def handle_query_sql(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute raw SQL query."""
        return self._queries.handle_query_sql(sql, params)

    def handle_get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        return self._queries.handle_get_stats()

    def handle_compute_adjacency(
        self,
        node_a: str,
        node_b: str,
        max_distance: int = 2,
    ) -> dict[str, Any]:
        """Compute shortest distance between two graph nodes."""
        return self._queries.handle_compute_adjacency(node_a, node_b, max_distance)

    def handle_persona_capability_map(
        self,
        persona_id: str,
    ) -> dict[str, Any]:
        """Get capability map for a persona."""
        return self._queries.handle_persona_capability_map(persona_id)

    # =========================================================================
    # Population Handlers (delegated)
    # =========================================================================

    def handle_auto_populate(
        self,
        root_path: str,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        max_files: int = 500,
    ) -> dict[str, Any]:
        """Auto-populate the knowledge graph from code files."""
        return self._population.handle_auto_populate(
            root_path, include_patterns, exclude_patterns, max_files
        )

    def handle_populate_from_appspec(
        self,
        project_path: str,
    ) -> dict[str, Any]:
        """Populate the knowledge graph from DSL entities and surfaces."""
        return self._population.handle_populate_from_appspec(project_path)

    def handle_populate_mcp_tools(self) -> dict[str, Any]:
        """Populate the knowledge graph with MCP tool definitions."""
        return self._population.handle_populate_mcp_tools()

    def handle_populate_test_coverage(
        self,
        tests_path: str,
        source_path: str | None = None,
    ) -> dict[str, Any]:
        """Populate the knowledge graph with test coverage information."""
        return self._population.handle_populate_test_coverage(tests_path, source_path)

    # =========================================================================
    # Tool Registry (for MCP server integration)
    # =========================================================================

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get MCP tool definitions for this handler."""
        return [
            {
                "name": "kg_create_entity",
                "description": "Create or update an entity in the knowledge graph",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Unique ID with prefix (file:, module:, class:, function:, concept:, decision:)",
                        },
                        "name": {"type": "string", "description": "Human-readable name"},
                        "entity_type": {
                            "type": "string",
                            "description": "Type (inferred from prefix if omitted)",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Additional metadata",
                        },
                    },
                    "required": ["entity_id", "name"],
                },
            },
            {
                "name": "kg_get_entity",
                "description": "Get an entity by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity ID"},
                    },
                    "required": ["entity_id"],
                },
            },
            {
                "name": "kg_delete_entity",
                "description": "Delete an entity and its relations",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity ID"},
                    },
                    "required": ["entity_id"],
                },
            },
            {
                "name": "kg_list_entities",
                "description": "List entities with optional filtering",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_type": {"type": "string", "description": "Filter by type"},
                        "name_pattern": {
                            "type": "string",
                            "description": "SQL LIKE pattern for name",
                        },
                        "limit": {"type": "integer", "default": 100},
                        "offset": {"type": "integer", "default": 0},
                    },
                },
            },
            {
                "name": "kg_create_relation",
                "description": "Create a relation between two entities",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string", "description": "Source entity ID"},
                        "target_id": {"type": "string", "description": "Target entity ID"},
                        "relation_type": {
                            "type": "string",
                            "description": "Type: imports, defines, calls, inherits, depends_on, etc.",
                        },
                        "metadata": {"type": "object"},
                    },
                    "required": ["source_id", "target_id", "relation_type"],
                },
            },
            {
                "name": "kg_delete_relation",
                "description": "Delete a relation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "target_id": {"type": "string"},
                        "relation_type": {"type": "string"},
                    },
                    "required": ["source_id", "target_id", "relation_type"],
                },
            },
            {
                "name": "kg_get_relations",
                "description": "Get relations for an entity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity ID (optional)"},
                        "relation_type": {"type": "string", "description": "Filter by type"},
                        "direction": {
                            "type": "string",
                            "enum": ["outgoing", "incoming", "both"],
                            "default": "both",
                        },
                    },
                },
            },
            {
                "name": "kg_find_paths",
                "description": "Find paths between two entities in the graph",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string", "description": "Starting entity"},
                        "target_id": {"type": "string", "description": "Target entity"},
                        "max_depth": {"type": "integer", "default": 5},
                        "relation_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by relation types",
                        },
                    },
                    "required": ["source_id", "target_id"],
                },
            },
            {
                "name": "kg_get_neighbourhood",
                "description": "Get entities within N hops of an entity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Center entity"},
                        "depth": {"type": "integer", "default": 1},
                        "relation_types": {"type": "array", "items": {"type": "string"}},
                        "direction": {
                            "type": "string",
                            "enum": ["outgoing", "incoming", "both"],
                            "default": "both",
                        },
                    },
                    "required": ["entity_id"],
                },
            },
            {
                "name": "kg_get_dependents",
                "description": "Get entities that depend on this entity (what uses this?)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string"},
                        "relation_types": {"type": "array", "items": {"type": "string"}},
                        "transitive": {"type": "boolean", "default": False},
                        "max_depth": {"type": "integer", "default": 5},
                    },
                    "required": ["entity_id"],
                },
            },
            {
                "name": "kg_get_dependencies",
                "description": "Get entities this entity depends on (what does this use?)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string"},
                        "relation_types": {"type": "array", "items": {"type": "string"}},
                        "transitive": {"type": "boolean", "default": False},
                        "max_depth": {"type": "integer", "default": 5},
                    },
                    "required": ["entity_id"],
                },
            },
            {
                "name": "kg_query",
                "description": "Search entities by text",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Search text"},
                        "entity_types": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "kg_query_sql",
                "description": "Execute raw SQL query (SELECT only)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "SQL SELECT query"},
                        "params": {"type": "array", "description": "Query parameters"},
                    },
                    "required": ["sql"],
                },
            },
            {
                "name": "kg_auto_populate",
                "description": "Auto-populate graph from Python codebase (extracts modules, classes, functions, imports, inheritance)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "root_path": {
                            "type": "string",
                            "description": "Root directory to scan",
                        },
                        "include_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Glob patterns to include (default: ['**/*.py'])",
                        },
                        "exclude_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Glob patterns to exclude",
                        },
                        "max_files": {"type": "integer", "default": 500},
                    },
                    "required": ["root_path"],
                },
            },
            {
                "name": "kg_stats",
                "description": "Get knowledge graph statistics",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "kg_populate_appspec",
                "description": "Populate graph from DAZZLE DSL (indexes entities, surfaces, relationships). Use this to answer questions like 'which surfaces use Entity X?'",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "Path to DAZZLE project (must contain dazzle.toml)",
                        },
                    },
                    "required": ["project_path"],
                },
            },
            {
                "name": "kg_populate_mcp_tools",
                "description": "Index MCP tool definitions into the knowledge graph. Enables queries like 'which tool handles user management?' or 'what operations does dsl tool support?'",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "kg_populate_test_coverage",
                "description": "Index test files to understand test coverage. Creates relations between test files and the modules they test. Enables queries like 'which modules have tests?' or 'what tests cover auth.py?'",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tests_path": {
                            "type": "string",
                            "description": "Path to tests directory",
                        },
                        "source_path": {
                            "type": "string",
                            "description": "Optional source directory to match against",
                        },
                    },
                    "required": ["tests_path"],
                },
            },
            {
                "name": "kg_compute_adjacency",
                "description": "Compute shortest distance between two DSL artefact nodes. Used for the two-step adjacency rule in capability discovery.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_a": {
                            "type": "string",
                            "description": "First node ID (e.g., 'entity:Task', 'surface:task_list')",
                        },
                        "node_b": {
                            "type": "string",
                            "description": "Second node ID",
                        },
                        "max_distance": {
                            "type": "integer",
                            "default": 2,
                            "description": "Maximum hops to search",
                        },
                    },
                    "required": ["node_a", "node_b"],
                },
            },
            {
                "name": "kg_persona_capability_map",
                "description": "Get what a persona can access: reachable workspaces, surfaces, entities, and stories within 2 hops.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "persona_id": {
                            "type": "string",
                            "description": "Persona ID (e.g., 'teacher' or 'persona:teacher')",
                        },
                    },
                    "required": ["persona_id"],
                },
            },
        ]

    def dispatch(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call to the appropriate handler."""
        handlers = {
            "kg_create_entity": self.handle_create_entity,
            "kg_get_entity": self.handle_get_entity,
            "kg_delete_entity": self.handle_delete_entity,
            "kg_list_entities": self.handle_list_entities,
            "kg_create_relation": self.handle_create_relation,
            "kg_delete_relation": self.handle_delete_relation,
            "kg_get_relations": self.handle_get_relations,
            "kg_find_paths": self.handle_find_paths,
            "kg_get_neighbourhood": self.handle_get_neighbourhood,
            "kg_get_dependents": self.handle_get_dependents,
            "kg_get_dependencies": self.handle_get_dependencies,
            "kg_query": self.handle_query,
            "kg_query_sql": self.handle_query_sql,
            "kg_auto_populate": self.handle_auto_populate,
            "kg_stats": self.handle_get_stats,
            "kg_populate_appspec": self.handle_populate_from_appspec,
            "kg_populate_mcp_tools": self.handle_populate_mcp_tools,
            "kg_populate_test_coverage": self.handle_populate_test_coverage,
            "kg_compute_adjacency": self.handle_compute_adjacency,
            "kg_persona_capability_map": self.handle_persona_capability_map,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        # Handler signatures vary by tool, but all return dict[str, Any]
        result: dict[str, Any] = handler(**arguments)  # type: ignore[operator]
        return result
