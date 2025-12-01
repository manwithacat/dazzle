"""
CLI help content for DAZZLE MCP server.

Provides structured documentation for CLI commands to help LLM agents
understand how to use the dazzle tool effectively.
"""

from typing import Any

# =============================================================================
# CLI Command Documentation
# =============================================================================

CLI_COMMANDS: dict[str, dict[str, Any]] = {
    # =========================================================================
    # DNR Commands (Primary)
    # =========================================================================
    "dnr serve": {
        "category": "DNR Runtime",
        "description": "Run a DAZZLE application using the Dazzle Native Runtime. This is the PRIMARY way to run DAZZLE apps.",
        "syntax": "dazzle dnr serve [OPTIONS]",
        "options": {
            "--port, -p": "Frontend port (default: 3000)",
            "--api-port": "Backend API port (default: 8000)",
            "--host": "Host to bind (default: 127.0.0.1)",
            "--local": "Run without Docker (direct Python/Node)",
            "--test-mode": "Enable E2E test endpoints (/__test__/*)",
            "--backend-only": "Run API only, no UI",
            "--ui-only": "Serve static UI only",
            "--db": "SQLite database path (default: .dazzle/data.db)",
            "--attach, -a": "Stream logs to terminal",
            "--rebuild": "Force Docker image rebuild",
        },
        "examples": [
            "dazzle dnr serve                    # Run with defaults",
            "dazzle dnr serve --local            # Run without Docker",
            "dazzle dnr serve --test-mode        # Enable test endpoints",
            "dazzle dnr serve -p 4000 --api-port 9000  # Custom ports",
        ],
        "output": {
            "ui_url": "http://localhost:3000",
            "api_url": "http://localhost:8000",
            "docs_url": "http://localhost:8000/docs",
        },
        "notes": [
            "DNR is the recommended runtime - no code generation needed",
            "Use --test-mode for E2E testing with Playwright",
            "Use --local for development without Docker",
        ],
    },
    "dnr info": {
        "category": "DNR Runtime",
        "description": "Show DNR installation status and project information.",
        "syntax": "dazzle dnr info",
        "examples": ["dazzle dnr info"],
    },
    "dnr stop": {
        "category": "DNR Runtime",
        "description": "Stop running DNR Docker containers.",
        "syntax": "dazzle dnr stop",
        "examples": ["dazzle dnr stop"],
    },
    "dnr logs": {
        "category": "DNR Runtime",
        "description": "View logs from running DNR container.",
        "syntax": "dazzle dnr logs [-f]",
        "options": {
            "-f": "Follow log output (like tail -f)",
        },
        "examples": ["dazzle dnr logs", "dazzle dnr logs -f"],
    },
    # =========================================================================
    # Project Management
    # =========================================================================
    "init": {
        "category": "Project Management",
        "description": "Initialize a new DAZZLE project with starter files.",
        "syntax": "dazzle init [PATH] [OPTIONS]",
        "options": {
            "--from, -f": "Copy from example (e.g., 'simple_task', 'support_tickets')",
            "--name, -n": "Project name (defaults to directory name)",
            "--list, -l": "List available examples",
            "--here": "Initialize in current directory even if not empty",
            "--no-git": "Skip git initialization",
            "--no-llm": "Skip LLM context files",
        },
        "examples": [
            "dazzle init                         # Init in current dir",
            "dazzle init ./my-app                # Create new directory",
            "dazzle init --from simple_task      # Copy from example",
            "dazzle init --list                  # Show available examples",
        ],
        "creates": [
            "dazzle.toml - Project manifest",
            "dsl/ - DSL source directory",
            "dsl/app.dsl - Starter DSL file",
            "README.md - Getting started guide",
        ],
    },
    # =========================================================================
    # Validation & Analysis
    # =========================================================================
    "validate": {
        "category": "Validation",
        "description": "Parse and validate all DSL files in the project.",
        "syntax": "dazzle validate [OPTIONS]",
        "options": {
            "--manifest, -m": "Path to dazzle.toml (default: ./dazzle.toml)",
            "--format, -f": "Output format: 'human' or 'vscode'",
        },
        "examples": [
            "dazzle validate",
            "dazzle validate --format vscode     # Machine-readable output",
        ],
        "notes": [
            "Run from project root (directory with dazzle.toml)",
            "Use 'vscode' format for IDE integration",
        ],
    },
    "lint": {
        "category": "Validation",
        "description": "Run extended lint checks beyond basic validation.",
        "syntax": "dazzle lint [OPTIONS]",
        "options": {
            "--strict": "Treat warnings as errors",
        },
        "examples": ["dazzle lint", "dazzle lint --strict"],
        "checks": [
            "Naming conventions",
            "Dead modules",
            "Unused imports",
            "Style violations",
        ],
    },
    "inspect": {
        "category": "Validation",
        "description": "Inspect AppSpec structure, patterns, and types.",
        "syntax": "dazzle inspect [OPTIONS]",
        "options": {
            "--interfaces/--no-interfaces": "Show module interfaces",
            "--patterns/--no-patterns": "Show detected patterns",
            "--types": "Show type catalog",
        },
        "examples": ["dazzle inspect", "dazzle inspect --types"],
    },
    "layout-plan": {
        "category": "Validation",
        "description": "Visualize workspace layout plans and archetype selection.",
        "syntax": "dazzle layout-plan [OPTIONS]",
        "options": {
            "--workspace, -w": "Show specific workspace only",
            "--persona, -p": "Generate plan for persona",
            "--explain, -e": "Explain archetype selection",
            "--json": "Output as JSON",
        },
        "examples": [
            "dazzle layout-plan",
            "dazzle layout-plan -w dashboard",
            "dazzle layout-plan --explain",
        ],
    },
    # =========================================================================
    # E2E Testing
    # =========================================================================
    "test generate": {
        "category": "E2E Testing",
        "description": "Generate E2E test specification from DSL.",
        "syntax": "dazzle test generate [OPTIONS]",
        "options": {
            "-o": "Output file path",
            "--format": "Output format: 'json' or 'yaml'",
            "--no-flows": "Skip auto-generated flows",
            "--no-fixtures": "Skip auto-generated fixtures",
        },
        "examples": [
            "dazzle test generate                # Print to stdout",
            "dazzle test generate -o tests.json  # Save to file",
        ],
        "generates": [
            "CRUD flows for each entity",
            "Validation flows for field constraints",
            "Navigation flows for surfaces",
            "Auth flows (if auth enabled)",
            "Test fixtures with sample data",
        ],
    },
    "test run": {
        "category": "E2E Testing",
        "description": "Run E2E tests using Playwright.",
        "syntax": "dazzle test run [OPTIONS]",
        "options": {
            "--priority": "Filter by priority (high, medium, low)",
            "--tag": "Filter by tag (e.g., 'crud', 'auth')",
            "--flow": "Run specific flow by ID",
            "--base-url": "Frontend URL (default: http://localhost:3000)",
            "--api-url": "Backend URL (default: http://localhost:8000)",
            "--headed": "Show browser window",
            "--timeout": "Default timeout in ms",
            "-o": "Save results to file",
            "-v": "Verbose output",
        },
        "examples": [
            "dazzle test run                     # Run all tests",
            "dazzle test run --priority high     # High priority only",
            "dazzle test run --tag auth          # Auth tests only",
            "dazzle test run --headed            # Show browser",
        ],
        "prerequisites": [
            "App running with: dazzle dnr serve --test-mode",
            "Playwright installed: pip install playwright && playwright install chromium",
        ],
    },
    "test list": {
        "category": "E2E Testing",
        "description": "List available test flows.",
        "syntax": "dazzle test list [OPTIONS]",
        "options": {
            "--priority": "Filter by priority",
            "--tag": "Filter by tag",
        },
        "examples": ["dazzle test list", "dazzle test list --priority high"],
    },
    # =========================================================================
    # Code Generation (Optional)
    # =========================================================================
    "build": {
        "category": "Code Generation",
        "description": "Generate code from DSL using a stack. NOTE: DNR is preferred - use 'dazzle dnr serve' instead for most cases.",
        "syntax": "dazzle build [OPTIONS]",
        "options": {
            "--stack, -s": "Stack to use (default: from manifest)",
            "--out, -o": "Output directory (default: ./build)",
            "--incremental, -i": "Incremental build",
            "--force": "Force full rebuild",
            "--diff": "Show changes without building",
        },
        "examples": [
            "dazzle build --stack docker         # Generate Docker Compose",
            "dazzle build --stack base           # Use base builder",
        ],
        "notes": [
            "DNR runtime is preferred for development",
            "Code generation is for custom deployments",
            "Legacy stacks (django_micro, express_micro) are deprecated",
        ],
    },
    # =========================================================================
    # MCP Server
    # =========================================================================
    "mcp": {
        "category": "MCP Server",
        "description": "Run the DAZZLE MCP server for Claude Code integration.",
        "syntax": "dazzle mcp [OPTIONS]",
        "options": {
            "--working-dir": "Project root directory",
        },
        "examples": ["dazzle mcp"],
    },
    "mcp-setup": {
        "category": "MCP Server",
        "description": "Register DAZZLE MCP server with Claude Code.",
        "syntax": "dazzle mcp-setup [--force]",
        "examples": ["dazzle mcp-setup"],
    },
}

# =============================================================================
# Quick Reference
# =============================================================================

QUICK_REFERENCE = """
# DAZZLE CLI Quick Reference

## Run an App (Primary Workflow)
```bash
cd my-project
dazzle dnr serve           # Start the app
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

## Create a New Project
```bash
dazzle init my-app         # Create new project
dazzle init --from simple_task  # Copy from example
```

## Validate & Inspect
```bash
dazzle validate            # Check DSL syntax
dazzle lint                # Extended checks
dazzle layout-plan         # Visualize workspaces
```

## E2E Testing
```bash
dazzle dnr serve --test-mode  # Start with test endpoints
dazzle test generate -o tests.json
dazzle test run
```

## Common Issues

### "No dazzle.toml found"
Run commands from project root (directory containing dazzle.toml)

### Port already in use
```bash
dazzle dnr stop            # Stop existing container
dazzle dnr serve -p 4000   # Use different port
```

### Docker issues
```bash
dazzle dnr serve --local   # Run without Docker
```
"""


# =============================================================================
# Lookup Functions
# =============================================================================


def get_cli_help(command: str | None = None) -> dict[str, Any]:
    """
    Get CLI help for a specific command or general overview.

    Args:
        command: Command name (e.g., 'dnr serve', 'test run') or None for overview

    Returns:
        Help information for the command
    """
    if command is None:
        # Return overview
        categories: dict[str, list[str]] = {}
        for cmd, info in CLI_COMMANDS.items():
            cat = info.get("category", "Other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(cmd)

        return {
            "overview": True,
            "quick_reference": QUICK_REFERENCE,
            "categories": categories,
            "primary_command": "dazzle dnr serve",
            "hint": "Use get_cli_help with a specific command for detailed help",
        }

    # Normalize command
    cmd_normalized = command.lower().strip()

    # Direct lookup
    if cmd_normalized in CLI_COMMANDS:
        return {"command": cmd_normalized, "found": True, **CLI_COMMANDS[cmd_normalized]}

    # Try with 'dazzle' prefix removed
    if cmd_normalized.startswith("dazzle "):
        cmd_normalized = cmd_normalized[7:]
        if cmd_normalized in CLI_COMMANDS:
            return {"command": cmd_normalized, "found": True, **CLI_COMMANDS[cmd_normalized]}

    # Partial match
    matches = [cmd for cmd in CLI_COMMANDS if cmd_normalized in cmd or cmd in cmd_normalized]
    if matches:
        return {
            "command": command,
            "found": False,
            "suggestions": matches,
            "hint": f"Did you mean one of: {', '.join(matches)}?",
        }

    return {
        "command": command,
        "found": False,
        "error": f"Command '{command}' not found",
        "available_commands": list(CLI_COMMANDS.keys()),
    }


def get_workflow_guide(workflow: str) -> dict[str, Any]:
    """
    Get a step-by-step guide for common workflows.

    Args:
        workflow: Workflow name (e.g., 'new_project', 'add_entity', 'setup_testing')

    Returns:
        Step-by-step workflow guide
    """
    workflows = {
        "new_project": {
            "name": "Create a New DAZZLE Project",
            "steps": [
                {
                    "step": 1,
                    "action": "Initialize project",
                    "command": "dazzle init my-app",
                    "notes": "Or use --from simple_task to copy an example",
                },
                {
                    "step": 2,
                    "action": "Navigate to project",
                    "command": "cd my-app",
                },
                {
                    "step": 3,
                    "action": "Edit DSL",
                    "file": "dsl/app.dsl",
                    "notes": "Define your entities, surfaces, and workspaces",
                },
                {
                    "step": 4,
                    "action": "Validate",
                    "command": "dazzle validate",
                },
                {
                    "step": 5,
                    "action": "Run the app",
                    "command": "dazzle dnr serve",
                },
            ],
        },
        "add_entity": {
            "name": "Add a New Entity",
            "steps": [
                {
                    "step": 1,
                    "action": "Edit DSL file",
                    "file": "dsl/app.dsl",
                    "example": '''entity Customer "Customer":
  id: uuid pk
  name: str(200) required
  email: email unique
  created_at: datetime auto_add''',
                },
                {
                    "step": 2,
                    "action": "Add CRUD surfaces",
                    "example": '''surface customer_list "Customers":
  uses entity Customer
  mode: list
  section main:
    field name
    field email

surface customer_create "New Customer":
  uses entity Customer
  mode: create''',
                },
                {
                    "step": 3,
                    "action": "Validate",
                    "command": "dazzle validate",
                },
                {
                    "step": 4,
                    "action": "Restart app",
                    "command": "dazzle dnr serve",
                    "notes": "DNR picks up changes automatically on restart",
                },
            ],
        },
        "setup_testing": {
            "name": "Set Up E2E Testing",
            "steps": [
                {
                    "step": 1,
                    "action": "Install Playwright",
                    "command": "pip install playwright && playwright install chromium",
                },
                {
                    "step": 2,
                    "action": "Start app in test mode",
                    "command": "dazzle dnr serve --test-mode",
                    "notes": "Enables /__test__/* endpoints for fixtures",
                },
                {
                    "step": 3,
                    "action": "Generate test spec",
                    "command": "dazzle test generate -o testspec.json",
                },
                {
                    "step": 4,
                    "action": "Run tests",
                    "command": "dazzle test run -v",
                },
            ],
        },
        "troubleshoot": {
            "name": "Troubleshooting Common Issues",
            "issues": [
                {
                    "problem": "No dazzle.toml found",
                    "solution": "Run commands from project root directory",
                },
                {
                    "problem": "Port already in use",
                    "solution": "Run 'dazzle dnr stop' or use -p flag for different port",
                },
                {
                    "problem": "Docker not running",
                    "solution": "Start Docker or use 'dazzle dnr serve --local'",
                },
                {
                    "problem": "Validation errors",
                    "solution": "Run 'dazzle validate' and fix syntax errors",
                },
                {
                    "problem": "Tests fail to find elements",
                    "solution": "Check data-dazzle-* attributes, use --headed to debug",
                },
            ],
        },
    }

    workflow_normalized = workflow.lower().replace("-", "_").replace(" ", "_")

    if workflow_normalized in workflows:
        return {"workflow": workflow, "found": True, **workflows[workflow_normalized]}

    return {
        "workflow": workflow,
        "found": False,
        "available_workflows": list(workflows.keys()),
    }
