"""
DAZZLE MCP Server implementation.

Implements the Model Context Protocol for DAZZLE using the official MCP SDK,
exposing tools for DSL validation, inspection, and code generation.

Supports two modes:
- Normal Mode: When running in a directory with dazzle.toml
- Dev Mode: When running in the Dazzle development environment (has examples/, src/dazzle/)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.patterns import detect_crud_patterns, detect_integration_patterns
from dazzle.mcp.examples import get_example_metadata, search_examples
from dazzle.mcp.prompts import create_prompts
from dazzle.mcp.resources import create_resources
from dazzle.mcp.semantics import get_semantic_index, lookup_concept

# Configure logging to stderr only (stdout is reserved for JSON-RPC protocol)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("dazzle.mcp")

# Create the MCP server instance
server = Server("dazzle")

# ============================================================================
# Server State
# ============================================================================

# Store project root (set during initialization)
_project_root: Path = Path.cwd()

# Dev mode state
_is_dev_mode: bool = False
_active_project: str | None = None  # Name of the active example project
_available_projects: dict[str, Path] = {}  # project_name -> project_path


def set_project_root(path: Path) -> None:
    """Set the project root for the server."""
    global _project_root
    _project_root = path


def get_project_root() -> Path:
    """Get the current project root."""
    return _project_root


def is_dev_mode() -> bool:
    """Check if server is in dev mode."""
    return _is_dev_mode


def get_active_project_path() -> Path | None:
    """Get the path to the active project, or None if not set."""
    if not _is_dev_mode:
        return _project_root
    if _active_project and _active_project in _available_projects:
        return _available_projects[_active_project]
    return None


# ============================================================================
# Dev Mode Detection
# ============================================================================


def _detect_dev_environment(root: Path) -> bool:
    """
    Detect if we're running in the Dazzle development environment.

    Markers:
    - No dazzle.toml in root
    - Has src/dazzle/ directory (source code)
    - Has examples/ directory with projects
    - Has pyproject.toml with name containing "dazzle"
    """
    # If there's a dazzle.toml, it's a normal project
    if (root / "dazzle.toml").exists():
        return False

    # Check for dev environment markers
    has_src = (root / "src" / "dazzle").is_dir()
    has_examples = (root / "examples").is_dir()

    # Check pyproject.toml for dazzle package
    has_pyproject = False
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            import tomllib
            data = tomllib.loads(pyproject_path.read_text())
            project_name = data.get("project", {}).get("name", "")
            has_pyproject = "dazzle" in project_name.lower()
        except Exception:
            pass

    return has_src and has_examples and has_pyproject


def _discover_example_projects(root: Path) -> dict[str, Path]:
    """Discover all example projects in the examples/ directory."""
    projects: dict[str, Path] = {}
    examples_dir = root / "examples"

    if not examples_dir.is_dir():
        return projects

    for item in examples_dir.iterdir():
        if item.is_dir():
            manifest_path = item / "dazzle.toml"
            if manifest_path.exists():
                projects[item.name] = item

    return projects


def _init_dev_mode(root: Path) -> None:
    """Initialize dev mode state."""
    global _is_dev_mode, _available_projects, _active_project

    _is_dev_mode = _detect_dev_environment(root)

    if _is_dev_mode:
        _available_projects = _discover_example_projects(root)
        # Auto-select first project if available
        if _available_projects:
            _active_project = sorted(_available_projects.keys())[0]
            logger.info(f"Dev mode: auto-selected project '{_active_project}'")
        logger.info(f"Dev mode enabled with {len(_available_projects)} example projects")
    else:
        _available_projects = {}
        _active_project = None


# ============================================================================
# Tools
# ============================================================================


def _get_dev_mode_tools() -> list[Tool]:
    """Get tools specific to dev mode."""
    return [
        Tool(
            name="list_projects",
            description="List all available example projects in the Dazzle dev environment",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="select_project",
            description="Select an example project to work with",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Name of the example project to select",
                    }
                },
                "required": ["project_name"],
            },
        ),
        Tool(
            name="get_active_project",
            description="Get the currently selected project",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="validate_all_projects",
            description="Validate all example projects at once",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


def _get_project_tools() -> list[Tool]:
    """Get tools that operate on a project."""
    return [
        Tool(
            name="validate_dsl",
            description="Validate all DSL files in the DAZZLE project",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="list_modules",
            description="List all modules in the DAZZLE project",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="inspect_entity",
            description="Inspect a specific entity definition",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to inspect",
                    }
                },
                "required": ["entity_name"],
            },
        ),
        Tool(
            name="inspect_surface",
            description="Inspect a specific surface definition",
            inputSchema={
                "type": "object",
                "properties": {
                    "surface_name": {
                        "type": "string",
                        "description": "Name of the surface to inspect",
                    }
                },
                "required": ["surface_name"],
            },
        ),
        Tool(
            name="build",
            description="Build artifacts for specified stacks",
            inputSchema={
                "type": "object",
                "properties": {
                    "stacks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Stack names to build (default: django_micro_modular)",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="analyze_patterns",
            description="Analyze the project for CRUD and integration patterns",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="lint_project",
            description="Run linting on the DAZZLE project",
            inputSchema={
                "type": "object",
                "properties": {
                    "extended": {
                        "type": "boolean",
                        "description": "Run extended checks",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="lookup_concept",
            description="Look up DAZZLE DSL v0.2 concepts by name. Returns definition, syntax, examples, and related concepts. Use this when Dazzle-specific terminology is mentioned (persona, workspace, attention signal, ux block, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "DSL concept to look up (e.g., 'persona', 'workspace', 'attention signal')",
                    }
                },
                "required": ["term"],
            },
        ),
        Tool(
            name="find_examples",
            description="Find example projects demonstrating specific DSL features. Useful for learning how to use v0.2 features like personas, workspaces, attention signals, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of features to search for (e.g., ['persona', 'workspace'])",
                    },
                    "complexity": {
                        "type": "string",
                        "description": "Complexity level: 'beginner', 'intermediate', or 'advanced'",
                    }
                },
                "required": [],
            },
        ),
    ]


@server.list_tools()  # type: ignore[no-untyped-call]
async def list_tools() -> list[Tool]:
    """List available DAZZLE tools."""
    tools = []

    # Add dev mode tools if in dev mode
    if is_dev_mode():
        tools.extend(_get_dev_mode_tools())

    # Add project tools (always available)
    tools.extend(_get_project_tools())

    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a DAZZLE tool."""

    # Dev mode tools
    if name == "list_projects":
        result = _list_projects()
    elif name == "select_project":
        result = _select_project(arguments)
    elif name == "get_active_project":
        result = _get_active_project()
    elif name == "validate_all_projects":
        result = _validate_all_projects()

    # Semantic lookup tools (always available)
    elif name == "lookup_concept":
        result = _lookup_concept(arguments)
    elif name == "find_examples":
        result = _find_examples(arguments)

    # Project tools - require active project in dev mode
    elif name in ("validate_dsl", "list_modules", "inspect_entity", "inspect_surface",
                  "build", "analyze_patterns", "lint_project"):
        project_path = get_active_project_path()

        if project_path is None:
            if is_dev_mode():
                result = json.dumps({
                    "error": "No project selected. Use 'list_projects' to see available projects and 'select_project' to choose one.",
                    "available_projects": list(_available_projects.keys()),
                })
            else:
                result = json.dumps({
                    "error": "No dazzle.toml found in project root",
                    "project_root": str(get_project_root()),
                })
        else:
            if name == "validate_dsl":
                result = _validate_dsl(project_path)
            elif name == "list_modules":
                result = _list_modules(project_path)
            elif name == "inspect_entity":
                result = _inspect_entity(project_path, arguments)
            elif name == "inspect_surface":
                result = _inspect_surface(project_path, arguments)
            elif name == "build":
                result = _build(project_path, arguments)
            elif name == "analyze_patterns":
                result = _analyze_patterns(project_path)
            elif name == "lint_project":
                result = _lint_project(project_path, arguments)
            else:
                result = json.dumps({"error": f"Unknown tool: {name}"})
    else:
        result = json.dumps({"error": f"Unknown tool: {name}"})

    return [TextContent(type="text", text=result)]


# ============================================================================
# Resource Handlers
# ============================================================================


@server.list_resources()  # type: ignore[no-untyped-call]
async def list_resources() -> list[Resource]:
    """List available DAZZLE resources."""
    resources = []

    # Add documentation resources (always available)
    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/glossary"),
            name="DAZZLE Glossary (v0.2)",
            description="Definitions of DAZZLE v0.2 terms (surface, persona, workspace, attention signals, etc.)",
            mimeType="text/markdown",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/quick-reference"),
            name="DAZZLE Quick Reference",
            description="DSL syntax quick reference with examples",
            mimeType="text/markdown",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/dsl-reference"),
            name="DAZZLE DSL Reference (v0.2)",
            description="Complete DSL v0.2 reference documentation with UX semantic layer",
            mimeType="text/markdown",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://semantics/index"),
            name="DAZZLE Semantic Concept Index (v0.2)",
            description="Structured index of all DSL v0.2 concepts with definitions, syntax, and examples",
            mimeType="application/json",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://examples/catalog"),
            name="Example Projects Catalog",
            description="Catalog of example projects with metadata about features they demonstrate",
            mimeType="application/json",
        )
    )

    # Add project-specific resources if we have an active project
    project_path = get_active_project_path()
    if project_path and (project_path / "dazzle.toml").exists():
        project_resources = create_resources(project_path)
        resources.extend([
            Resource(
                uri=r["uri"],
                name=r["name"],
                description=r["description"],
                mimeType=r.get("mimeType", "text/plain"),
            )
            for r in project_resources
        ])

    return resources


@server.read_resource()  # type: ignore[no-untyped-call]
async def read_resource(uri: str) -> str:
    """Read a DAZZLE resource by URI."""

    # Documentation resources
    if uri == "dazzle://docs/glossary":
        return _get_glossary()

    elif uri == "dazzle://docs/quick-reference":
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        quick_ref = docs_dir / "DAZZLE_DSL_QUICK_REFERENCE.md"
        if quick_ref.exists():
            return quick_ref.read_text()
        return "Quick reference not found"

    elif uri == "dazzle://docs/dsl-reference":
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        dsl_ref = docs_dir / "v0.2" / "DAZZLE_DSL_REFERENCE.md"
        if dsl_ref.exists():
            return dsl_ref.read_text()
        return "DSL reference not found"

    # Semantic resources
    elif uri == "dazzle://semantics/index":
        return json.dumps(get_semantic_index(), indent=2)

    # Example resources
    elif uri == "dazzle://examples/catalog":
        return json.dumps(get_example_metadata(), indent=2)

    # Project resources
    elif uri.startswith("dazzle://project/"):
        project_path = get_active_project_path()
        if not project_path:
            return json.dumps({"error": "No active project"})

        if uri == "dazzle://project/manifest":
            manifest_path = project_path / "dazzle.toml"
            if manifest_path.exists():
                return manifest_path.read_text()
            return "Manifest not found"

        elif uri == "dazzle://modules":
            return _list_modules(project_path)

        elif uri == "dazzle://entities":
            return _get_entities(project_path)

        elif uri == "dazzle://surfaces":
            return _get_surfaces(project_path)

    elif uri.startswith("dazzle://dsl/"):
        project_path = get_active_project_path()
        if not project_path:
            return json.dumps({"error": "No active project"})

        # Extract file path from URI
        file_path = uri.replace("dazzle://dsl/", "")
        dsl_file = project_path / file_path
        if dsl_file.exists():
            return dsl_file.read_text()
        return f"DSL file not found: {file_path}"

    return f"Unknown resource: {uri}"


def _get_glossary() -> str:
    """Return DAZZLE v0.2 glossary of terms."""
    return """# DAZZLE Glossary - Terms of Art (v0.2)

**Version**: 0.2.0
**Date**: 2025-11-25

This glossary defines DAZZLE DSL v0.2 concepts including the new UX Semantic Layer.

## Core Concepts

### Entity
A domain model representing a business concept (User, Task, Device, etc.). Similar to a database table but defined at the semantic level. Entities have fields with types, constraints, and relationships.

**Version**: Unchanged from v0.1

**Example:**
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done]=todo
  created_at: datetime auto_add
```

### Surface
A UI or API interface definition for interacting with entities. Surfaces define WHAT data to show and HOW users interact with it, without prescribing visual implementation.

**Version**: Enhanced in v0.2 with optional UX block

**Modes:**
- `list` - Display multiple records (table, grid, cards)
- `view` - Display single record details (read-only)
- `create` - Form for creating new records
- `edit` - Form for modifying existing records

**Example (v0.2 with UX block):**
```dsl
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"

  ux:
    purpose: "Track team task progress"
    sort: status asc, title asc
    filter: status, assigned_to

    attention warning:
      when: status = blocked
      message: "Needs attention"
```

### Workspace (NEW in v0.2)
A composition of multiple data views into a cohesive dashboard or information hub. Workspaces aggregate related surfaces and data for specific user needs.

**Version**: NEW in v0.2

**Example:**
```dsl
workspace dashboard "Team Dashboard":
  purpose: "Real-time team overview"

  urgent_tasks:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc
    limit: 5
    action: task_edit
    empty: "No urgent tasks!"

  team_metrics:
    aggregate:
      total: count(Task)
      completed: count(Task where status = done)
      completion_rate: count(Task where status = done) * 100 / count(Task)
```

### Persona (NEW in v0.2)
A role-based variant that adapts surfaces or workspaces for different user types (admin, manager, member, etc.). Personas control scope, visibility, and capabilities without code duplication.

**Version**: NEW in v0.2

**Example:**
```dsl
ux:
  for admin:
    scope: all
    purpose: "Full task management"
    action_primary: task_create

  for member:
    scope: assigned_to = current_user
    purpose: "Your personal tasks"
    read_only: true
```

### UX Semantic Layer (NEW in v0.2)
Optional metadata on surfaces and workspaces expressing WHY they exist and WHAT matters to users, without prescribing HOW to implement it.

**Version**: NEW in v0.2

**Components:**
- `purpose` - Single-line explanation of semantic intent
- `show`, `sort`, `filter`, `search` - Information needs
- `attention` - Data-driven alerts (critical, warning, notice, info)
- `for {persona}` - Role-based variants

**Example:**
```dsl
ux:
  purpose: "Manage user accounts and permissions"

  sort: name asc
  filter: role, is_active
  search: name, email

  attention warning:
    when: days_since(last_login) > 90
    message: "Inactive account"

  for admin:
    scope: all
  for member:
    scope: id = current_user.id
    read_only: true
```

### Attention Signal (NEW in v0.2)
Data-driven conditions that require user awareness or action. Signals have severity levels and can trigger actions.

**Version**: NEW in v0.2

**Levels**: critical, warning, notice, info

**Example:**
```dsl
attention critical:
  when: due_date < today and status != done
  message: "Overdue task"
  action: task_edit

attention warning:
  when: priority = high and status = todo
  message: "High priority - needs assignment"
```

### Module
A namespace for organizing DSL definitions across multiple files. Modules can depend on other modules and define entities, surfaces, workspaces, and services.

**Example:**
```dsl
module myapp.core

app MyApp "My Application"

entity User "User":
  # ... fields
```

## Field Types

### Basic Types
- `str(N)` - String with max length N
- `text` - Long text (no length limit)
- `int` - Integer number
- `decimal(P,S)` - Decimal number (precision, scale)
- `bool` - Boolean (true/false)
- `date` - Date only
- `time` - Time only
- `datetime` - Date and time
- `uuid` - UUID identifier

### Special Types
- `email` - Email address (with validation)
- `url` - URL (with validation)
- `enum[V1,V2,V3]` - Enumeration of values

### Modifiers
- `required` - Field must have a value
- `optional` - Field can be null (default)
- `unique` - Value must be unique across records
- `pk` - Primary key
- `auto_add` - Auto-set on creation (datetime)
- `auto_update` - Auto-update on save (datetime)

## Surface Modes

### list
Display multiple records in tabular, grid, or card format. Supports sorting, filtering, searching, and bulk actions.

### view
Display single record details in read-only format. Shows complete information for a specific entity instance.

### create
Form for creating new entity records. Defines which fields to collect and validation rules.

### edit
Form for modifying existing entity records. Can control which fields are editable.

## Common Patterns

### CRUD Pattern
Complete create-read-update-delete interface for an entity:
- `{entity}_list` (list mode)
- `{entity}_detail` (view mode)
- `{entity}_create` (create mode)
- `{entity}_edit` (edit mode)

### Dashboard Pattern
Workspace aggregating multiple data views:
- Metrics/KPIs
- Recent activity
- Alerts/attention items
- Quick actions

### Role-Based Access
Persona variants controlling scope and capabilities:
- Admin: full access, all records
- Manager: department/team scope
- Member: own records only

## Best Practices

1. **Entity names** - Use singular nouns (Task, not Tasks)
2. **Surface names** - Use `{entity}_{mode}` pattern (task_list, user_edit)
3. **Workspace names** - Use `{context}_dashboard` or `{role}_workspace`
4. **Persona names** - Use lowercase role names (admin, manager, member)
5. **Field names** - Use snake_case (first_name, not firstName)
6. **Enum values** - Use lowercase with underscores (in_progress, not InProgress)
7. **Purpose statements** - Single line, explain WHY not WHAT

## See Also

- DAZZLE DSL Quick Reference - Syntax examples
- DAZZLE DSL Reference v0.2 - Complete specification
"""


def _get_entities(project_path: Path) -> str:
    """Get all entity definitions from project."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        entities = {}
        for entity in app_spec.domain.entities:
            entities[entity.name] = {
                "name": entity.name,
                "title": entity.title,
                "fields": [
                    {
                        "name": f.name,
                        "type": str(f.type),
                        "required": f.is_required,
                        "unique": f.is_unique,
                        "is_pk": f.is_primary_key,
                    }
                    for f in entity.fields
                ],
            }

        return json.dumps(entities, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _get_surfaces(project_path: Path) -> str:
    """Get all surface definitions from project."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        surfaces = {}
        for surface in app_spec.surfaces:
            surfaces[surface.name] = {
                "name": surface.name,
                "title": surface.title,
                "mode": surface.mode,
                "entity": surface.entity_ref,
                "has_ux": surface.ux is not None,
            }

        return json.dumps(surfaces, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ============================================================================
# Prompt Handlers
# ============================================================================


@server.list_prompts()  # type: ignore[no-untyped-call]
async def list_prompts() -> list[dict[str, Any]]:
    """List available DAZZLE prompts."""
    return create_prompts()


@server.get_prompt()  # type: ignore[no-untyped-call]
async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> str:
    """Get a DAZZLE prompt by name."""
    args = arguments or {}

    if name == "validate":
        return """Please validate the DAZZLE project:

1. Use the validate_dsl tool to check for syntax errors
2. Report any validation errors found
3. If valid, summarize the project structure (modules, entities, surfaces)"""

    elif name == "review_dsl":
        aspect = args.get("aspect", "all")
        return f"""Please review the DAZZLE DSL focusing on: {aspect}

1. Read the DSL files using the dazzle://dsl/* resources
2. Analyze the design based on DAZZLE best practices
3. Check for:
   - Proper entity/surface naming conventions
   - CRUD pattern completeness
   - Appropriate use of personas and UX semantics
   - Security considerations (if aspect=security or all)
   - Performance implications (if aspect=performance or all)
4. Suggest specific improvements with examples"""

    elif name == "code_review":
        stack = args.get("stack", "django_micro_modular")
        return f"""Please review the generated code for stack: {stack}

1. Use the build tool to generate code if not already built
2. Examine the generated code in build/{stack}/
3. Check for:
   - Code quality and best practices
   - Security vulnerabilities
   - Performance issues
   - Proper error handling
4. Suggest improvements"""

    elif name == "suggest_surfaces":
        entity_name = args.get("entity_name", "")
        if not entity_name:
            return "Error: entity_name argument required"

        return f"""Please suggest surface definitions for the {entity_name} entity:

1. Use inspect_entity to examine the {entity_name} entity
2. Determine appropriate CRUD surfaces needed
3. Suggest UX semantics for each surface:
   - Purpose statement
   - Information needs (show, sort, filter, search)
   - Attention signals if applicable
   - Persona variants if needed
4. Provide complete DSL code for the suggested surfaces"""

    elif name == "optimize_dsl":
        return """Please analyze the DSL and suggest optimizations:

1. Use analyze_patterns to detect CRUD and integration patterns
2. Look for:
   - Incomplete CRUD patterns
   - Redundant surface definitions
   - Missing persona variants
   - Opportunities for workspaces
   - Better use of UX semantics
3. Suggest specific DSL improvements with before/after examples"""

    return f"Unknown prompt: {name}"


# ============================================================================
# Dev Mode Tool Implementations
# ============================================================================


def _list_projects() -> str:
    """List all available example projects."""
    if not is_dev_mode():
        return json.dumps({
            "error": "Not in dev mode. This tool is only available in the Dazzle development environment."
        })

    projects = []
    for name, path in sorted(_available_projects.items()):
        is_active = name == _active_project

        # Try to get project info
        try:
            manifest = load_manifest(path / "dazzle.toml")
            project_info = {
                "name": name,
                "path": str(path),
                "active": is_active,
                "manifest_name": manifest.name,
                "version": manifest.version,
            }
        except Exception as e:
            project_info = {
                "name": name,
                "path": str(path),
                "active": is_active,
                "error": str(e),
            }

        projects.append(project_info)

    return json.dumps({
        "mode": "dev",
        "project_count": len(projects),
        "active_project": _active_project,
        "projects": projects,
    }, indent=2)


def _select_project(args: dict[str, Any]) -> str:
    """Select an example project to work with."""
    global _active_project

    if not is_dev_mode():
        return json.dumps({
            "error": "Not in dev mode. This tool is only available in the Dazzle development environment."
        })

    project_name = args.get("project_name")
    if not project_name:
        return json.dumps({"error": "project_name required"})

    if project_name not in _available_projects:
        return json.dumps({
            "error": f"Project '{project_name}' not found",
            "available_projects": list(_available_projects.keys()),
        })

    _active_project = project_name
    project_path = _available_projects[project_name]

    # Return info about the selected project
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        return json.dumps({
            "status": "selected",
            "project": project_name,
            "path": str(project_path),
            "manifest_name": manifest.name,
            "version": manifest.version,
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "selected",
            "project": project_name,
            "path": str(project_path),
            "warning": f"Could not load manifest: {e}",
        }, indent=2)


def _get_active_project() -> str:
    """Get the currently selected project."""
    if not is_dev_mode():
        # In normal mode, return info about the project root
        project_root = get_project_root()
        manifest_path = project_root / "dazzle.toml"

        if manifest_path.exists():
            try:
                manifest = load_manifest(manifest_path)
                return json.dumps({
                    "mode": "normal",
                    "project_root": str(project_root),
                    "manifest_name": manifest.name,
                    "version": manifest.version,
                }, indent=2)
            except Exception as e:
                return json.dumps({
                    "mode": "normal",
                    "project_root": str(project_root),
                    "error": f"Could not load manifest: {e}",
                }, indent=2)
        else:
            return json.dumps({
                "mode": "normal",
                "project_root": str(project_root),
                "error": "No dazzle.toml found",
            }, indent=2)

    if _active_project is None:
        return json.dumps({
            "mode": "dev",
            "active_project": None,
            "message": "No project selected. Use 'select_project' to choose one.",
            "available_projects": list(_available_projects.keys()),
        }, indent=2)

    project_path = _available_projects.get(_active_project)
    if project_path is None:
        return json.dumps({
            "mode": "dev",
            "error": f"Active project '{_active_project}' not found",
        }, indent=2)

    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        return json.dumps({
            "mode": "dev",
            "active_project": _active_project,
            "path": str(project_path),
            "manifest_name": manifest.name,
            "version": manifest.version,
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "mode": "dev",
            "active_project": _active_project,
            "path": str(project_path),
            "error": f"Could not load manifest: {e}",
        }, indent=2)


def _validate_all_projects() -> str:
    """Validate all example projects."""
    if not is_dev_mode():
        return json.dumps({
            "error": "Not in dev mode. This tool is only available in the Dazzle development environment."
        })

    results = {}

    for name, path in sorted(_available_projects.items()):
        try:
            manifest = load_manifest(path / "dazzle.toml")
            dsl_files = discover_dsl_files(path, manifest)
            modules = parse_modules(dsl_files)
            app_spec = build_appspec(modules, manifest.project_root)

            results[name] = {
                "status": "valid",
                "modules": len(modules),
                "entities": len(app_spec.domain.entities),
                "surfaces": len(app_spec.surfaces),
                "services": len(app_spec.services),
            }
        except Exception as e:
            results[name] = {
                "status": "error",
                "error": str(e),
            }

    # Summary
    valid_count = sum(1 for r in results.values() if r["status"] == "valid")
    error_count = sum(1 for r in results.values() if r["status"] == "error")

    return json.dumps({
        "summary": {
            "total": len(results),
            "valid": valid_count,
            "errors": error_count,
        },
        "projects": results,
    }, indent=2)


# ============================================================================
# Project Tool Implementations
# ============================================================================


def _validate_dsl(project_root: Path) -> str:
    """Validate DSL files in the project."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        result = {
            "status": "valid",
            "modules": len(modules),
            "entities": len(app_spec.domain.entities),
            "surfaces": len(app_spec.surfaces),
            "services": len(app_spec.services),
        }

        # Add project context in dev mode
        if is_dev_mode():
            result["project"] = _active_project
            result["path"] = str(project_root)

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


def _list_modules(project_root: Path) -> str:
    """List all modules in the project."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        parsed_modules = parse_modules(dsl_files)

        modules = {}
        for idx, module in enumerate(parsed_modules):
            modules[module.name] = {
                "file": str(dsl_files[idx].relative_to(project_root)),
                "dependencies": module.uses,
            }

        return json.dumps(modules, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _inspect_entity(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect an entity definition."""
    entity_name = args.get("entity_name")
    if not entity_name:
        return json.dumps({"error": "entity_name required"})

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
        if not entity:
            return json.dumps({"error": f"Entity '{entity_name}' not found"})

        return json.dumps(
            {
                "name": entity.name,
                "description": entity.title,
                "fields": [
                    {
                        "name": f.name,
                        "type": str(f.type.kind),
                        "required": f.is_required,
                        "modifiers": [str(m) for m in f.modifiers],
                    }
                    for f in entity.fields
                ],
                "constraints": [str(c) for c in entity.constraints] if entity.constraints else [],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _inspect_surface(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect a surface definition."""
    surface_name = args.get("surface_name")
    if not surface_name:
        return json.dumps({"error": "surface_name required"})

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        surface = next((s for s in app_spec.surfaces if s.name == surface_name), None)
        if not surface:
            return json.dumps({"error": f"Surface '{surface_name}' not found"})

        return json.dumps(
            {
                "name": surface.name,
                "entity": surface.entity_ref,
                "mode": str(surface.mode),
                "description": surface.title,
                "sections": len(surface.sections) if surface.sections else 0,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _build(project_root: Path, args: dict[str, Any]) -> str:
    """Build artifacts for specified stacks."""
    stacks = args.get("stacks", ["django_micro_modular"])

    try:
        from dazzle.stacks import get_backend

        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        results = {}
        output_dir = project_root / "build"
        output_dir.mkdir(exist_ok=True)

        for stack_name in stacks:
            try:
                stack = get_backend(stack_name)
                stack_output = output_dir / stack_name
                stack.generate(app_spec, stack_output)
                results[stack_name] = f"Built successfully in {stack_output}"
            except Exception as e:
                results[stack_name] = f"Error: {str(e)}"

        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _analyze_patterns(project_root: Path) -> str:
    """Analyze the project for patterns."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        crud_patterns = detect_crud_patterns(app_spec)
        integration_patterns = detect_integration_patterns(app_spec)

        return json.dumps(
            {
                "crud_patterns": [
                    {
                        "entity": p.entity_name,
                        "has_create": p.has_create,
                        "has_list": p.has_list,
                        "has_detail": p.has_detail,
                        "has_edit": p.has_edit,
                        "is_complete": p.is_complete,
                        "missing_operations": p.missing_operations,
                    }
                    for p in crud_patterns
                ],
                "integration_patterns": [
                    {
                        "name": p.integration_name,
                        "service": p.service_name,
                        "has_actions": p.has_actions,
                        "has_syncs": p.has_syncs,
                        "action_count": p.action_count,
                        "sync_count": p.sync_count,
                        "connected_entities": list(p.connected_entities or []),
                        "connected_surfaces": list(p.connected_surfaces or []),
                    }
                    for p in integration_patterns
                ],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _lint_project(project_root: Path, args: dict[str, Any]) -> str:
    """Run linting on the project."""
    extended = args.get("extended", False)

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        warnings, _ = lint_appspec(app_spec, extended=extended)

        return json.dumps(
            {"warnings": len(warnings), "issues": [str(w) for w in warnings]},
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ============================================================================
# Semantic Lookup Tool Implementations
# ============================================================================


def _lookup_concept(args: dict[str, Any]) -> str:
    """Look up a DAZZLE DSL concept."""
    term = args.get("term")
    if not term:
        return json.dumps({"error": "term parameter required"})

    result = lookup_concept(term)
    return json.dumps(result, indent=2)


def _find_examples(args: dict[str, Any]) -> str:
    """Find example projects by features or complexity."""
    features = args.get("features")
    complexity = args.get("complexity")

    results = search_examples(features=features, complexity=complexity)

    return json.dumps(
        {
            "query": {
                "features": features,
                "complexity": complexity,
            },
            "count": len(results),
            "examples": results,
        },
        indent=2,
    )


# ============================================================================
# Server Entry Point
# ============================================================================


async def run_server(project_root: Path | None = None) -> None:
    """Run the DAZZLE MCP server."""
    if project_root:
        set_project_root(project_root)
        logger.info(f"Project root set to: {project_root}")
    else:
        logger.info(f"Using default project root: {get_project_root()}")

    # Initialize dev mode detection
    _init_dev_mode(get_project_root())

    if is_dev_mode():
        logger.info(f"Running in DEV MODE with {len(_available_projects)} example projects")
        logger.info(f"Available projects: {list(_available_projects.keys())}")
        logger.info(f"Active project: {_active_project}")
    else:
        logger.info("Running in NORMAL MODE")

    logger.info("Starting DAZZLE MCP server...")
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("stdio transport established, running server...")
            await server.run(read_stream, write_stream, server.create_initialization_options())
    except Exception as e:
        logger.exception(f"Server error: {e}")
        raise


# For backwards compatibility
class DazzleMCPServer:
    """Legacy wrapper for the MCP server."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    async def run(self) -> None:
        await run_server(self.project_root)
