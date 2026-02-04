"""
MCP Tool Handlers for Knowledge Graph.

Provides handlers for:
- Entity CRUD: create_entity, get_entity, delete_entity, list_entities
- Relation CRUD: create_relation, delete_relation, get_relations
- Graph traversal: find_paths, get_neighbourhood, get_dependents, get_dependencies
- Query: query, query_sql
- Auto-population: auto_populate (bootstraps from code files)
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from .store import Entity, KnowledgeGraph, Relation

logger = logging.getLogger(__name__)


class KnowledgeGraphHandlers:
    """
    MCP tool handlers for knowledge graph operations.

    Designed to be low-overhead: most operations complete in single calls,
    reducing back-and-forth prompting overhead.
    """

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    # =========================================================================
    # Entity Handlers
    # =========================================================================

    def handle_create_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or update an entity."""
        entity = self._graph.create_entity(
            entity_id=entity_id,
            name=name,
            entity_type=entity_type,
            metadata=metadata,
        )
        return self._entity_to_dict(entity)

    def handle_get_entity(self, entity_id: str) -> dict[str, Any]:
        """Get an entity by ID."""
        entity = self._graph.get_entity(entity_id)
        if not entity:
            return {"error": f"Entity not found: {entity_id}"}
        return self._entity_to_dict(entity)

    def handle_delete_entity(self, entity_id: str) -> dict[str, Any]:
        """Delete an entity."""
        deleted = self._graph.delete_entity(entity_id)
        return {"deleted": deleted, "entity_id": entity_id}

    def handle_list_entities(
        self,
        entity_type: str | None = None,
        name_pattern: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List entities with filtering."""
        entities = self._graph.list_entities(
            entity_type=entity_type,
            name_pattern=name_pattern,
            limit=limit,
            offset=offset,
        )
        return {
            "entities": [self._entity_to_dict(e) for e in entities],
            "count": len(entities),
        }

    # =========================================================================
    # Relation Handlers
    # =========================================================================

    def handle_create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a relation between entities."""
        relation = self._graph.create_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata,
        )
        return self._relation_to_dict(relation)

    def handle_delete_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> dict[str, Any]:
        """Delete a relation."""
        deleted = self._graph.delete_relation(source_id, target_id, relation_type)
        return {
            "deleted": deleted,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
        }

    def handle_get_relations(
        self,
        entity_id: str | None = None,
        relation_type: str | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get relations for an entity."""
        relations = self._graph.get_relations(
            entity_id=entity_id,
            relation_type=relation_type,
            direction=direction,
        )
        return {
            "relations": [self._relation_to_dict(r) for r in relations],
            "count": len(relations),
        }

    # =========================================================================
    # Graph Traversal Handlers
    # =========================================================================

    def handle_find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        relation_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Find paths between two entities."""
        paths = self._graph.find_paths(
            source_id=source_id,
            target_id=target_id,
            max_depth=max_depth,
            relation_types=relation_types,
        )
        return {
            "source": source_id,
            "target": target_id,
            "paths": [
                {
                    "path": p.path,
                    "relations": p.relations,
                    "length": p.length,
                }
                for p in paths
            ],
            "count": len(paths),
        }

    def handle_get_neighbourhood(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get neighborhood of an entity."""
        result = self._graph.get_neighbourhood(
            entity_id=entity_id,
            depth=depth,
            relation_types=relation_types,
            direction=direction,
        )
        return {
            "center": result["center"],
            "entities": [self._entity_to_dict(e) for e in result["entities"]],
            "relations": [self._relation_to_dict(r) for r in result["relations"]],
            "entity_count": len(result["entities"]),
            "relation_count": len(result["relations"]),
        }

    def handle_get_dependents(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        transitive: bool = False,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Get entities that depend on this entity."""
        entities = self._graph.get_dependents(
            entity_id=entity_id,
            relation_types=relation_types,
            transitive=transitive,
            max_depth=max_depth,
        )
        return {
            "entity_id": entity_id,
            "dependents": [self._entity_to_dict(e) for e in entities],
            "count": len(entities),
            "transitive": transitive,
        }

    def handle_get_dependencies(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        transitive: bool = False,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Get entities this entity depends on."""
        entities = self._graph.get_dependencies(
            entity_id=entity_id,
            relation_types=relation_types,
            transitive=transitive,
            max_depth=max_depth,
        )
        return {
            "entity_id": entity_id,
            "dependencies": [self._entity_to_dict(e) for e in entities],
            "count": len(entities),
            "transitive": transitive,
        }

    # =========================================================================
    # Query Handlers
    # =========================================================================

    def handle_query(
        self,
        text: str,
        entity_types: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search entities by text."""
        entities = self._graph.query(
            text=text,
            entity_types=entity_types,
            limit=limit,
        )
        return {
            "query": text,
            "entities": [self._entity_to_dict(e) for e in entities],
            "count": len(entities),
        }

    def handle_query_sql(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute raw SQL query."""
        try:
            results = self._graph.query_sql(sql, params)
            return {"results": results, "count": len(results)}
        except ValueError as e:
            return {"error": str(e)}

    def handle_get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        return self._graph.get_stats()

    # =========================================================================
    # Auto-Population (Critical for adoption)
    # =========================================================================

    def handle_auto_populate(
        self,
        root_path: str,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        max_files: int = 500,
    ) -> dict[str, Any]:
        """
        Auto-populate the knowledge graph from code files.

        Scans Python files to extract:
        - Modules (file: entities)
        - Classes (class: entities)
        - Functions (function: entities)
        - Import relationships
        - Inheritance relationships
        - Function call relationships (basic)

        Args:
            root_path: Root directory to scan
            include_patterns: Glob patterns to include (default: ["**/*.py"])
            exclude_patterns: Glob patterns to exclude (default: common excludes)
            max_files: Maximum files to process

        Returns:
            Stats about what was populated
        """
        root = Path(root_path)
        if not root.exists():
            return {"error": f"Path does not exist: {root_path}"}

        include = include_patterns or ["**/*.py"]
        exclude = exclude_patterns or [
            "**/.*",
            "**/__pycache__/**",
            "**/venv/**",
            "**/node_modules/**",
            "**/.git/**",
            "**/dist/**",
            "**/build/**",
        ]

        # Collect files
        files: list[Path] = []
        for pattern in include:
            for f in root.glob(pattern):
                if f.is_file() and not self._matches_exclude(f, exclude, root):
                    files.append(f)
                    if len(files) >= max_files:
                        break
            if len(files) >= max_files:
                break

        stats: dict[str, Any] = {
            "files_scanned": 0,
            "modules_created": 0,
            "classes_created": 0,
            "functions_created": 0,
            "imports_created": 0,
            "inheritance_created": 0,
            "errors": [],
        }

        for file_path in files:
            try:
                self._populate_from_file(file_path, root, stats)
                stats["files_scanned"] = int(stats["files_scanned"]) + 1
            except Exception as e:
                errors_list: list[str] = stats["errors"]
                errors_list.append(f"{file_path}: {e}")
                logger.warning(f"Error processing {file_path}: {e}")

        return stats

    def _matches_exclude(self, path: Path, patterns: list[str], root: Path) -> bool:
        """Check if path matches any exclude pattern."""
        rel_path = path.relative_to(root)
        parts = rel_path.parts

        for pattern in patterns:
            # Handle common patterns explicitly
            if pattern == "**/.*":
                # Match any path component starting with a dot
                if any(p.startswith(".") for p in parts):
                    return True
            elif pattern.endswith("/**"):
                # Match any file under a directory
                dir_name = pattern[3:-3] if pattern.startswith("**/") else pattern[:-3]
                if dir_name in parts:
                    return True
            elif path.match(pattern):
                return True
        return False

    def _populate_from_file(self, file_path: Path, root: Path, stats: dict[str, Any]) -> None:
        """Extract entities and relations from a Python file."""
        rel_path = file_path.relative_to(root)
        module_id = f"file:{rel_path}"
        module_name = str(rel_path).replace("/", ".").replace(".py", "")

        # Create module entity
        self._graph.create_entity(
            entity_id=module_id,
            name=module_name,
            entity_type="module",
            metadata={"path": str(file_path), "relative_path": str(rel_path)},
        )
        stats["modules_created"] += 1

        # Parse AST
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError) as e:
            stats["errors"].append(f"{file_path}: Parse error - {e}")
            return

        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target_id = f"module:{alias.name}"
                    self._graph.create_relation(
                        source_id=module_id,
                        target_id=target_id,
                        relation_type="imports",
                    )
                    stats["imports_created"] += 1

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    target_id = f"module:{node.module}"
                    self._graph.create_relation(
                        source_id=module_id,
                        target_id=target_id,
                        relation_type="imports",
                    )
                    stats["imports_created"] += 1

            elif isinstance(node, ast.ClassDef):
                class_id = f"class:{module_name}.{node.name}"
                self._graph.create_entity(
                    entity_id=class_id,
                    name=node.name,
                    entity_type="class",
                    metadata={
                        "module": module_name,
                        "lineno": node.lineno,
                        "docstring": ast.get_docstring(node) or "",
                    },
                )
                stats["classes_created"] += 1

                # Module contains class
                self._graph.create_relation(
                    source_id=module_id,
                    target_id=class_id,
                    relation_type="contains",
                )

                # Inheritance
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        # Simple base class name - may be local or imported
                        base_id = f"class:{base.id}"
                        self._graph.create_relation(
                            source_id=class_id,
                            target_id=base_id,
                            relation_type="inherits",
                        )
                        stats["inheritance_created"] += 1
                    elif isinstance(base, ast.Attribute):
                        # module.ClassName style
                        if isinstance(base.value, ast.Name):
                            base_id = f"class:{base.value.id}.{base.attr}"
                            self._graph.create_relation(
                                source_id=class_id,
                                target_id=base_id,
                                relation_type="inherits",
                            )
                            stats["inheritance_created"] += 1

            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                # Only top-level functions (not methods inside classes)
                # Check if parent is Module
                func_id = f"function:{module_name}.{node.name}"
                self._graph.create_entity(
                    entity_id=func_id,
                    name=node.name,
                    entity_type="function",
                    metadata={
                        "module": module_name,
                        "lineno": node.lineno,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "docstring": ast.get_docstring(node) or "",
                    },
                )
                stats["functions_created"] += 1

                # Module contains function
                self._graph.create_relation(
                    source_id=module_id,
                    target_id=func_id,
                    relation_type="contains",
                )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _entity_to_dict(self, entity: Entity) -> dict[str, Any]:
        """Convert entity to dict for JSON response."""
        return {
            "id": entity.id,
            "type": entity.entity_type,
            "name": entity.name,
            "metadata": entity.metadata,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

    def _relation_to_dict(self, relation: Relation) -> dict[str, Any]:
        """Convert relation to dict for JSON response."""
        return {
            "source_id": relation.source_id,
            "target_id": relation.target_id,
            "relation_type": relation.relation_type,
            "metadata": relation.metadata,
            "created_at": relation.created_at,
        }

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
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        # Handler signatures vary by tool, but all return dict[str, Any]
        result: dict[str, Any] = handler(**arguments)  # type: ignore[operator]
        return result
