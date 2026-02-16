"""Auto-population handlers for the Knowledge Graph.

Handles populating the KG from code files, DSL AppSpec, MCP tools,
and test coverage information.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..store import KnowledgeGraph

logger = logging.getLogger(__name__)


class PopulationHandlers:
    """Handles auto-populate, appspec indexing, MCP tool indexing, and test coverage."""

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    # =========================================================================
    # Code Auto-Population
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

    # =========================================================================
    # AppSpec Population
    # =========================================================================

    def handle_populate_from_appspec(
        self,
        project_path: str,
    ) -> dict[str, Any]:
        """
        Populate the knowledge graph from DSL entities and surfaces.

        Parses the DAZZLE project at the given path and indexes:
        - Entities (entity:{name} nodes with fields as metadata)
        - Surfaces (surface:{name} nodes with entity reference)
        - Entity relationships (foreign keys)
        - Surface-to-entity "uses" relations

        This enables queries like:
        - "Which surfaces use Entity X?" via graph(operation="dependents", entity_id="entity:Task")
        - "What fields does Entity Y have?" via graph(operation="query", text="Order")

        Args:
            project_path: Path to the DAZZLE project directory

        Returns:
            Stats about what was populated
        """
        root = Path(project_path)
        if not root.exists():
            return {"error": f"Path does not exist: {project_path}"}

        manifest_path = root / "dazzle.toml"
        if not manifest_path.exists():
            return {"error": f"No dazzle.toml found in {project_path}"}

        stats: dict[str, Any] = {
            "entities_created": 0,
            "surfaces_created": 0,
            "stories_created": 0,
            "processes_created": 0,
            "personas_created": 0,
            "workspaces_created": 0,
            "experiences_created": 0,
            "services_created": 0,
            "relations_created": 0,
            "fields_indexed": 0,
            "errors": [],
        }

        try:
            # Load AppSpec using the standard DAZZLE toolchain
            from dazzle.core.errors import ParseError
            from dazzle.core.fileset import discover_dsl_files
            from dazzle.core.linker import build_appspec
            from dazzle.core.manifest import load_manifest
            from dazzle.core.parser import parse_modules

            manifest = load_manifest(manifest_path)
            dsl_files = discover_dsl_files(root, manifest)

            if not dsl_files:
                return {"error": "No DSL files found", **stats}

            modules = parse_modules(dsl_files)
            appspec = build_appspec(modules, manifest.project_root)

            self._populate_entities(appspec, stats)
            self._populate_surfaces(appspec, stats)
            self._populate_stories(appspec, stats)
            self._populate_processes(appspec, stats)
            self._populate_personas(appspec, stats)
            self._populate_workspaces(appspec, stats)
            self._populate_experiences(appspec, stats)
            self._populate_services(appspec, stats)

        except ParseError as e:
            errors_list: list[str] = stats["errors"]
            errors_list.append(f"Parse error: {e}")
            logger.warning(f"Parse error indexing {project_path}: {e}")
        except Exception as e:
            errors_list = stats["errors"]
            errors_list.append(f"Error: {e}")
            logger.warning(f"Error indexing {project_path}: {e}")

        return stats

    # =========================================================================
    # MCP Tool Population
    # =========================================================================

    def handle_populate_mcp_tools(self) -> dict[str, Any]:
        """
        Populate the knowledge graph with MCP tool definitions.

        Indexes all registered MCP tools to enable queries like:
        - "which tool handles user creation?"
        - "what operations does the story tool support?"

        Creates nodes:
        - tool:{name} for each MCP tool with description and schema
        - Extracts operation keywords from descriptions

        Returns:
            Stats about what was indexed
        """
        stats: dict[str, Any] = {
            "tools_created": 0,
            "operations_indexed": 0,
            "errors": [],
        }

        try:
            # Import tools from the MCP server
            from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools

            tools = get_all_consolidated_tools()

            for tool in tools:
                tool_id = f"tool:{tool.name}"
                tool_name = tool.name

                # Extract operation keywords from description
                description = tool.description or ""
                operations = self._extract_operations_from_description(description)

                # Extract input parameters
                input_schema = tool.inputSchema or {}
                properties = input_schema.get("properties", {})
                param_names = list(properties.keys())

                self._graph.create_entity(
                    entity_id=tool_id,
                    name=tool_name,
                    entity_type="mcp_tool",
                    metadata={
                        "description": description,
                        "operations": operations,
                        "parameters": param_names,
                        "required": input_schema.get("required", []),
                    },
                )
                stats["tools_created"] += 1
                stats["operations_indexed"] += len(operations)

        except ImportError as e:
            error_msg = f"Could not import MCP tools: {e}"
            errors_list: list[str] = stats["errors"]
            errors_list.append(error_msg)
            logger.warning(error_msg)
        except Exception as e:
            error_msg = f"Error indexing MCP tools: {e}"
            errors_list = stats["errors"]
            errors_list.append(error_msg)
            logger.warning(error_msg)

        return stats

    # =========================================================================
    # Test Coverage Population
    # =========================================================================

    def handle_populate_test_coverage(
        self,
        tests_path: str,
        source_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Populate the knowledge graph with test coverage information.

        Scans test files to understand what modules are tested and creates
        coverage relations between test files and source modules.

        Enables queries like:
        - "which modules have tests?"
        - "what tests cover auth.py?"
        - "which modules lack test coverage?"

        Args:
            tests_path: Path to tests directory
            source_path: Optional source directory to match against

        Returns:
            Stats about what was indexed
        """
        tests_root = Path(tests_path)
        if not tests_root.exists():
            return {"error": f"Tests path does not exist: {tests_path}"}

        stats: dict[str, Any] = {
            "test_files_created": 0,
            "test_classes_found": 0,
            "coverage_relations_created": 0,
            "errors": [],
        }

        # Find all test files
        test_patterns = ["**/test_*.py", "**/*_test.py"]
        test_files: list[Path] = []
        for pattern in test_patterns:
            test_files.extend(tests_root.glob(pattern))

        for test_file in test_files:
            try:
                self._index_test_file(test_file, tests_root, source_path, stats)
            except Exception as e:
                stats["errors"].append(f"{test_file}: {e}")
                logger.warning(f"Error indexing test file {test_file}: {e}")

        return stats

    # =========================================================================
    # Private Helpers — AppSpec Population
    # =========================================================================

    def _create_relation_counted(
        self,
        stats: dict[str, Any],
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create a relation and increment the stats counter."""
        self._graph.create_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata,
        )
        stats["relations_created"] += 1

    def _populate_entities(self, appspec: Any, stats: dict[str, Any]) -> None:
        """Index entities and their FK relationships."""
        for entity in appspec.domain.entities:
            entity_id = f"entity:{entity.name}"
            field_names = [f.name for f in entity.fields]
            self._graph.create_entity(
                entity_id=entity_id,
                name=entity.name,
                entity_type="dsl_entity",
                metadata={
                    "title": entity.title,
                    "intent": entity.intent,
                    "fields": field_names,
                    "field_count": len(entity.fields),
                },
            )
            stats["entities_created"] += 1
            stats["fields_indexed"] += len(entity.fields)

            # Foreign key references
            for field in entity.fields:
                if field.type.ref_entity:
                    self._create_relation_counted(
                        stats,
                        source_id=entity_id,
                        target_id=f"entity:{field.type.ref_entity}",
                        relation_type="references",
                        metadata={
                            "via_field": field.name,
                            "ref_kind": field.type.kind.value,
                        },
                    )

    def _populate_surfaces(self, appspec: Any, stats: dict[str, Any]) -> None:
        """Index surfaces and their relationships to entities and personas."""
        for surface in appspec.surfaces:
            surface_id = f"surface:{surface.name}"
            self._graph.create_entity(
                entity_id=surface_id,
                name=surface.name,
                entity_type="dsl_surface",
                metadata={
                    "title": surface.title,
                    "mode": surface.mode.value if surface.mode else None,
                    "entity_ref": surface.entity_ref,
                },
            )
            stats["surfaces_created"] += 1

            # Surface -> Entity
            if surface.entity_ref:
                self._create_relation_counted(
                    stats,
                    source_id=surface_id,
                    target_id=f"entity:{surface.entity_ref}",
                    relation_type="uses",
                    metadata={"mode": surface.mode.value if surface.mode else None},
                )

            # Surface -> Persona (access control)
            if surface.access:
                for persona_name in surface.access.allow_personas:
                    self._create_relation_counted(
                        stats,
                        source_id=surface_id,
                        target_id=f"persona:{persona_name}",
                        relation_type="allows_persona",
                    )
                for persona_name in surface.access.deny_personas:
                    self._create_relation_counted(
                        stats,
                        source_id=surface_id,
                        target_id=f"persona:{persona_name}",
                        relation_type="denies_persona",
                    )

    def _populate_stories(self, appspec: Any, stats: dict[str, Any]) -> None:
        """Index stories with actor->persona and scope->entity edges."""
        for story in appspec.stories:
            story_id = f"story:{story.story_id}"
            self._graph.create_entity(
                entity_id=story_id,
                name=story.story_id,
                entity_type="dsl_story",
                metadata={
                    "title": story.title,
                    "actor": story.actor,
                    "scope": story.scope,
                    "status": story.status.value
                    if hasattr(story.status, "value")
                    else str(story.status),
                },
            )
            stats["stories_created"] += 1

            # Story -> Persona (actor)
            if story.actor:
                self._create_relation_counted(
                    stats,
                    source_id=story_id,
                    target_id=f"persona:{story.actor}",
                    relation_type="acts_as",
                    metadata={"role": "actor"},
                )

            # Story -> Entities (scope)
            for entity_name in story.scope:
                self._create_relation_counted(
                    stats,
                    source_id=story_id,
                    target_id=f"entity:{entity_name}",
                    relation_type="scopes",
                )

    def _populate_processes(self, appspec: Any, stats: dict[str, Any]) -> None:
        """Index processes with edges to stories, services, and surfaces."""
        for process in appspec.processes:
            process_id = f"process:{process.name}"
            self._graph.create_entity(
                entity_id=process_id,
                name=process.name,
                entity_type="dsl_process",
                metadata={
                    "title": process.title,
                    "implements": process.implements,
                    "step_count": len(process.steps),
                },
            )
            stats["processes_created"] += 1

            # Process -> Stories (implements)
            for story_ref in process.implements:
                self._create_relation_counted(
                    stats,
                    source_id=process_id,
                    target_id=f"story:{story_ref}",
                    relation_type="process_implements",
                )

            # Process steps -> services, subprocesses, surfaces
            for step in process.steps:
                if step.service:
                    self._create_relation_counted(
                        stats,
                        source_id=process_id,
                        target_id=f"service:{step.service}",
                        relation_type="invokes",
                        metadata={"step": step.name},
                    )
                if step.subprocess:
                    self._create_relation_counted(
                        stats,
                        source_id=process_id,
                        target_id=f"process:{step.subprocess}",
                        relation_type="has_subprocess",
                        metadata={"step": step.name},
                    )
                if step.human_task and step.human_task.surface:
                    self._create_relation_counted(
                        stats,
                        source_id=process_id,
                        target_id=f"surface:{step.human_task.surface}",
                        relation_type="human_task_on",
                        metadata={"step": step.name},
                    )

    def _populate_personas(self, appspec: Any, stats: dict[str, Any]) -> None:
        """Index personas with default workspace edges."""
        for persona in appspec.personas:
            persona_id = f"persona:{persona.id}"
            self._graph.create_entity(
                entity_id=persona_id,
                name=persona.id,
                entity_type="dsl_persona",
                metadata={
                    "label": persona.label,
                    "description": persona.description,
                    "goals": persona.goals,
                    "proficiency": persona.proficiency_level,
                    "default_workspace": persona.default_workspace,
                },
            )
            stats["personas_created"] += 1

            # Persona -> Workspace (default)
            if persona.default_workspace:
                self._create_relation_counted(
                    stats,
                    source_id=persona_id,
                    target_id=f"workspace:{persona.default_workspace}",
                    relation_type="default_workspace",
                )

    def _populate_workspaces(self, appspec: Any, stats: dict[str, Any]) -> None:
        """Index workspaces with region->entity and access->persona edges."""
        for workspace in appspec.workspaces:
            workspace_id = f"workspace:{workspace.name}"
            self._graph.create_entity(
                entity_id=workspace_id,
                name=workspace.name,
                entity_type="dsl_workspace",
                metadata={
                    "title": workspace.title,
                    "region_count": len(workspace.regions),
                },
            )
            stats["workspaces_created"] += 1

            # Workspace -> Entity (region sources)
            for region in workspace.regions:
                if region.source:
                    self._create_relation_counted(
                        stats,
                        source_id=workspace_id,
                        target_id=f"entity:{region.source}",
                        relation_type="region_source",
                        metadata={"region": region.name},
                    )

            # Workspace -> Persona (access control)
            if workspace.access:
                for persona_name in workspace.access.allow_personas:
                    self._create_relation_counted(
                        stats,
                        source_id=workspace_id,
                        target_id=f"persona:{persona_name}",
                        relation_type="allows_persona",
                    )
                for persona_name in workspace.access.deny_personas:
                    self._create_relation_counted(
                        stats,
                        source_id=workspace_id,
                        target_id=f"persona:{persona_name}",
                        relation_type="denies_persona",
                    )

    def _populate_experiences(self, appspec: Any, stats: dict[str, Any]) -> None:
        """Index experiences with step->surface edges."""
        for experience in appspec.experiences:
            experience_id = f"experience:{experience.name}"
            self._graph.create_entity(
                entity_id=experience_id,
                name=experience.name,
                entity_type="dsl_experience",
                metadata={
                    "title": experience.title,
                    "step_count": len(experience.steps),
                },
            )
            stats["experiences_created"] += 1

            # Experience steps -> surfaces
            for step in experience.steps:
                if step.surface:
                    self._create_relation_counted(
                        stats,
                        source_id=experience_id,
                        target_id=f"surface:{step.surface}",
                        relation_type="navigates_to",
                        metadata={"step": step.name},
                    )

    def _populate_services(self, appspec: Any, stats: dict[str, Any]) -> None:
        """Index domain services (leaf nodes, no outgoing edges)."""
        for service in appspec.domain_services:
            service_id = f"service:{service.name}"
            self._graph.create_entity(
                entity_id=service_id,
                name=service.name,
                entity_type="dsl_service",
                metadata={
                    "title": service.title,
                    "kind": service.kind.value
                    if hasattr(service.kind, "value")
                    else str(service.kind),
                },
            )
            stats["services_created"] += 1

    # =========================================================================
    # Private Helpers — MCP Tools
    # =========================================================================

    def _extract_operations_from_description(self, description: str) -> list[str]:
        """Extract operation keywords from a tool description."""
        operation_keywords = [
            "list",
            "get",
            "create",
            "update",
            "delete",
            "search",
            "query",
            "validate",
            "inspect",
            "generate",
            "run",
            "execute",
            "propose",
            "save",
            "fetch",
            "analyze",
            "coverage",
            "scaffold",
            "review",
            "test",
            "check",
        ]

        description_lower = description.lower()
        found_operations = []
        for op in operation_keywords:
            if op in description_lower:
                found_operations.append(op)

        return found_operations

    # =========================================================================
    # Private Helpers — Test Coverage
    # =========================================================================

    def _index_test_file(
        self,
        test_file: Path,
        tests_root: Path,
        source_path: str | None,
        stats: dict[str, Any],
    ) -> None:
        """Index a single test file into the knowledge graph."""
        rel_path = test_file.relative_to(tests_root)
        test_id = f"test:{rel_path}"
        test_name = test_file.stem

        # Parse the test file to extract test classes
        try:
            source = test_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(test_file))
        except (SyntaxError, UnicodeDecodeError) as e:
            stats["errors"].append(f"{test_file}: Parse error - {e}")
            return

        # Find test classes and functions
        test_classes: list[str] = []
        test_functions: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                test_classes.append(node.name)
            elif isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                # Only count top-level test functions (not methods)
                if isinstance(node, ast.FunctionDef):
                    test_functions.append(node.name)

        stats["test_classes_found"] += len(test_classes)

        # Infer what module this test file covers
        covered_modules = self._infer_covered_modules(test_name, test_classes)

        # Create test file entity
        self._graph.create_entity(
            entity_id=test_id,
            name=test_name,
            entity_type="test_file",
            metadata={
                "path": str(rel_path),
                "test_classes": test_classes,
                "test_function_count": len(test_functions),
                "covered_modules": covered_modules,
            },
        )
        stats["test_files_created"] += 1

        # Create coverage relations to inferred modules
        for module_name in covered_modules:
            module_id = f"file:{module_name}.py"
            self._graph.create_relation(
                source_id=test_id,
                target_id=module_id,
                relation_type="tests",
                create_missing_entities=True,
            )
            stats["coverage_relations_created"] += 1

    def _infer_covered_modules(self, test_name: str, test_classes: list[str]) -> list[str]:
        """Infer which modules a test file covers based on naming conventions."""
        covered: set[str] = set()

        # From test file name: test_auth.py -> auth
        if test_name.startswith("test_"):
            module_name = test_name[5:]  # Remove "test_" prefix
            if module_name:
                covered.add(module_name)
        elif test_name.endswith("_test"):
            module_name = test_name[:-5]  # Remove "_test" suffix
            if module_name:
                covered.add(module_name)

        # From test class names: TestAuthStore -> auth_store or auth
        for class_name in test_classes:
            if class_name.startswith("Test"):
                # Convert TestAuthStore -> auth_store
                name = class_name[4:]  # Remove "Test"
                # Convert CamelCase to snake_case
                snake_name = self._camel_to_snake(name)
                if snake_name:
                    covered.add(snake_name)

        return list(covered)

    def _camel_to_snake(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        import re

        # Insert underscore before uppercase letters and lowercase everything
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    # =========================================================================
    # Private Helpers — Code File Population
    # =========================================================================

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
                        base_id = f"class:{base.id}"
                        self._graph.create_relation(
                            source_id=class_id,
                            target_id=base_id,
                            relation_type="inherits",
                        )
                        stats["inheritance_created"] += 1
                    elif isinstance(base, ast.Attribute):
                        if isinstance(base.value, ast.Name):
                            base_id = f"class:{base.value.id}.{base.attr}"
                            self._graph.create_relation(
                                source_id=class_id,
                                target_id=base_id,
                                relation_type="inherits",
                            )
                            stats["inheritance_created"] += 1

            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
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
