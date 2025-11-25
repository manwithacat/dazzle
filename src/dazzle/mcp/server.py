"""
DAZZLE MCP Server implementation.

Implements the Model Context Protocol for DAZZLE, exposing tools, resources,
and prompts via JSON-RPC 2.0 over stdio.
"""

import json
import sys
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.patterns import detect_crud_patterns, detect_integration_patterns
from dazzle.mcp.prompts import create_prompts
from dazzle.mcp.resources import create_resources
from dazzle.mcp.tools import create_tools


class DazzleMCPServer:
    """
    MCP server for DAZZLE DSL tooling.

    Implements JSON-RPC 2.0 protocol over stdio for Claude Code integration.
    """

    def __init__(self, project_root: Path | None = None):
        """
        Initialize MCP server.

        Args:
            project_root: Root directory of DAZZLE project (defaults to cwd)
        """
        self.project_root = project_root or Path.cwd()
        self.server_info = {"name": "dazzle", "version": "0.1.0"}

    async def run(self) -> None:
        """Run the MCP server, reading JSON-RPC from stdin and writing to stdout."""
        import asyncio

        while True:
            try:
                # Read JSON-RPC request from stdin
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)

                if not line:
                    break

                request = json.loads(line)
                response = await self._handle_request(request)

                # Write JSON-RPC response to stdout
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            except Exception as e:
                self._log_error(f"Server error: {e}")
                break

    async def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Handle a JSON-RPC request.

        Args:
            request: JSON-RPC request object

        Returns:
            JSON-RPC response object
        """
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "tools/list":
                result = {"tools": create_tools()}
            elif method == "tools/call":
                result = await self._call_tool(params)
            elif method == "resources/list":
                result = {"resources": create_resources(self.project_root)}
            elif method == "resources/read":
                result = self._read_resource(params)
            elif method == "prompts/list":
                result = {"prompts": create_prompts()}
            elif method == "prompts/get":
                result = self._get_prompt(params)
            else:
                raise ValueError(f"Unknown method: {method}")

            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": "0.1.0",
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": self.server_info,
        }

    async def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a tool.

        Args:
            params: Tool call parameters with 'name' and 'arguments'

        Returns:
            Tool result
        """
        name = params.get("name")
        arguments = params.get("arguments", {})

        if name == "validate_dsl":
            result = self._validate_dsl()
        elif name == "list_modules":
            result = self._list_modules()
        elif name == "inspect_entity":
            result = self._inspect_entity(arguments)
        elif name == "inspect_surface":
            result = self._inspect_surface(arguments)
        elif name == "build":
            result = self._build(arguments)
        elif name == "analyze_patterns":
            result = self._analyze_patterns()
        elif name == "lint_project":
            result = self._lint_project(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return {"content": [{"type": "text", "text": result}]}

    def _validate_dsl(self) -> str:
        """Validate DSL files in the project."""
        try:
            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all files
            modules = parse_modules(dsl_files)

            # Build appspec by linking modules
            app_spec = build_appspec(modules, manifest.project_root)

            return json.dumps(
                {
                    "status": "valid",
                    "modules": len(modules),
                    "entities": len(app_spec.domain.entities),
                    "surfaces": len(app_spec.surfaces),
                    "services": len(app_spec.services),
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)}, indent=2)

    def _list_modules(self) -> str:
        """List all modules in the project."""
        try:
            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all modules
            parsed_modules = parse_modules(dsl_files)

            modules = {}
            for idx, module in enumerate(parsed_modules):
                modules[module.name] = {
                    "file": str(dsl_files[idx].relative_to(self.project_root)),
                    "dependencies": module.uses,
                }

            return json.dumps(modules, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    def _inspect_entity(self, args: dict[str, Any]) -> str:
        """Inspect an entity definition."""
        entity_name = args.get("entity_name")
        if not entity_name:
            return json.dumps({"error": "entity_name required"})

        try:
            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all modules
            modules = parse_modules(dsl_files)

            # Build appspec
            app_spec = build_appspec(modules, manifest.project_root)

            # Find entity
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
                    "constraints": [str(c) for c in entity.constraints]
                    if entity.constraints
                    else [],
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    def _inspect_surface(self, args: dict[str, Any]) -> str:
        """Inspect a surface definition."""
        surface_name = args.get("surface_name")
        if not surface_name:
            return json.dumps({"error": "surface_name required"})

        try:
            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all modules
            modules = parse_modules(dsl_files)

            # Build appspec
            app_spec = build_appspec(modules, manifest.project_root)

            # Find surface
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

    def _build(self, args: dict[str, Any]) -> str:
        """Build artifacts for specified stacks."""
        stacks = args.get("stacks", ["django_micro_modular"])

        try:
            from dazzle.stacks import get_backend

            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all modules
            modules = parse_modules(dsl_files)

            # Build appspec
            app_spec = build_appspec(modules, manifest.project_root)

            # Build each stack
            results = {}
            output_dir = self.project_root / "build"
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

    def _analyze_patterns(self) -> str:
        """Analyze the project for patterns."""
        try:
            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all modules
            modules = parse_modules(dsl_files)

            # Build appspec
            app_spec = build_appspec(modules, manifest.project_root)

            # Analyze patterns
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

    def _lint_project(self, args: dict[str, Any]) -> str:
        """Run linting on the project."""
        extended = args.get("extended", False)

        try:
            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all modules
            modules = parse_modules(dsl_files)

            # Build appspec
            app_spec = build_appspec(modules, manifest.project_root)

            # Run lint
            warnings, _ = lint_appspec(app_spec, extended=extended)

            return json.dumps(
                {"warnings": len(warnings), "issues": [str(w) for w in warnings]}, indent=2
            )

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    def _read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        """Read resource content by URI."""
        uri = params.get("uri")
        content = ""

        if not uri:
            return {"content": "No URI provided"}

        if uri == "dazzle://project/manifest":
            manifest_path = self.project_root / "dazzle.toml"
            if manifest_path.exists():
                content = manifest_path.read_text()
            else:
                content = "No dazzle.toml found"

        elif uri == "dazzle://modules":
            content = self._list_modules()

        elif uri == "dazzle://entities":
            content = self._list_entities()

        elif uri == "dazzle://surfaces":
            content = self._list_surfaces()

        elif uri.startswith("dazzle://dsl/"):
            # Read DSL file
            file_path = uri.replace("dazzle://dsl/", "")
            dsl_file = self.project_root / file_path
            if dsl_file.exists():
                content = dsl_file.read_text()
            else:
                content = f"File not found: {file_path}"

        else:
            content = f"Unknown resource: {uri}"

        return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]}

    def _list_entities(self) -> str:
        """List all entities in the project."""
        try:
            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all modules
            modules = parse_modules(dsl_files)

            # Build appspec
            app_spec = build_appspec(modules, manifest.project_root)

            entities = {
                e.name: {"fields": len(e.fields), "description": e.title or ""}
                for e in app_spec.domain.entities
            }

            return json.dumps(entities, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    def _list_surfaces(self) -> str:
        """List all surfaces in the project."""
        try:
            manifest = load_manifest(self.project_root)
            dsl_files = discover_dsl_files(self.project_root, manifest)

            # Parse all modules
            modules = parse_modules(dsl_files)

            # Build appspec
            app_spec = build_appspec(modules, manifest.project_root)

            surfaces = {
                s.name: {
                    "entity": s.entity_ref,
                    "mode": str(s.mode),
                    "description": s.title or "",
                }
                for s in app_spec.surfaces
            }

            return json.dumps(surfaces, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    def _get_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get a prompt by name."""
        name = params.get("name")
        arguments = params.get("arguments", {})

        # Generate prompt content based on name
        if name == "validate":
            content = "Please validate the DAZZLE project using the validate_dsl tool."
        elif name == "review_dsl":
            aspect = arguments.get("aspect", "all")
            content = f"Please review the DAZZLE DSL focusing on {aspect}. Use inspect_entity and inspect_surface tools to examine definitions."
        elif name == "code_review":
            stack = arguments.get("stack", "django_micro_modular")
            content = f"Please review the generated {stack} code. First build it using the build tool, then examine the output."
        elif name == "suggest_surfaces":
            entity = arguments.get("entity_name")
            content = f"Please suggest surface definitions for the {entity} entity based on CRUD patterns."
        elif name == "optimize_dsl":
            content = "Please analyze the DSL using analyze_patterns and suggest optimizations."
        else:
            content = f"Unknown prompt: {name}"

        return {
            "description": f"Prompt: {name}",
            "messages": [{"role": "user", "content": {"type": "text", "text": content}}],
        }

    def _log_error(self, message: str) -> None:
        """Log error to stderr."""
        print(f"[DAZZLE MCP] {message}", file=sys.stderr)
