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
    # Runtime Commands (Primary)
    # =========================================================================
    "serve": {
        "category": "Dazzle Runtime",
        "description": "Run a DAZZLE application using the Dazzle Runtime. This is the PRIMARY way to run DAZZLE apps.",
        "syntax": "dazzle serve [OPTIONS]",
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
            "dazzle serve                    # Run with defaults",
            "dazzle serve --local            # Run without Docker",
            "dazzle serve --test-mode        # Enable test endpoints",
            "dazzle serve -p 4000 --api-port 9000  # Custom ports",
        ],
        "output": {
            "ui_url": "http://localhost:3000",
            "api_url": "http://localhost:8000",
            "docs_url": "http://localhost:8000/docs",
        },
        "notes": [
            "Dazzle is the recommended runtime - no code generation needed",
            "Use --test-mode for E2E testing with Playwright",
            "Use --local for development without Docker",
        ],
    },
    "info": {
        "category": "Dazzle Runtime",
        "description": "Show DNR installation status and project information.",
        "syntax": "dazzle info",
        "examples": ["dazzle info"],
    },
    "stop": {
        "category": "Dazzle Runtime",
        "description": "Stop running DNR Docker containers.",
        "syntax": "dazzle stop",
        "examples": ["dazzle stop"],
    },
    "logs": {
        "category": "Dazzle Runtime",
        "description": "View logs from running DNR container.",
        "syntax": "dazzle logs [-f]",
        "options": {
            "-f": "Follow log output (like tail -f)",
        },
        "examples": ["dazzle logs", "dazzle logs -f"],
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
            "App running with: dazzle serve --test-mode",
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
        "description": "Generate code from DSL using a stack. NOTE: DNR is preferred - use 'dazzle serve' instead for most cases.",
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
            "Dazzle runtime is preferred for development",
            "Code generation is for custom deployments",
            "Legacy stacks (django_micro, express_micro) are deprecated",
        ],
    },
    # =========================================================================
    # Stubs (v0.5.0)
    # =========================================================================
    "stubs generate": {
        "category": "Stubs",
        "description": "Generate Python/TypeScript stub files from domain service definitions.",
        "syntax": "dazzle stubs generate [OPTIONS]",
        "options": {
            "--service": "Generate stub for specific service only",
            "--language": "Override stub language (python, typescript)",
            "--output-dir": "Output directory (default: stubs/)",
            "--force": "Overwrite existing stub files",
        },
        "examples": [
            "dazzle stubs generate              # Generate all stubs",
            "dazzle stubs generate --service calculate_vat",
            "dazzle stubs generate --force      # Regenerate all",
        ],
        "creates": [
            "stubs/<service_name>.py - Python stub with typed signature",
            "stubs/<service_name>.ts - TypeScript stub with interfaces",
        ],
        "notes": [
            "Stubs have auto-generated headers with service contracts",
            "Implement the function body - don't modify the header",
            "Run after adding/changing domain services in DSL",
        ],
    },
    "stubs list": {
        "category": "Stubs",
        "description": "List all domain services and their stub implementation status.",
        "syntax": "dazzle stubs list",
        "examples": ["dazzle stubs list"],
        "output": {
            "service_name": "Name of the domain service",
            "kind": "Service kind (domain_logic, validation, integration, workflow)",
            "stub_language": "Target language (python, typescript)",
            "status": "implemented | not_implemented | missing",
        },
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
dazzle serve           # Start the app
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
dazzle serve --test-mode  # Start with test endpoints
dazzle test generate -o tests.json
dazzle test run
```

## Common Issues

### "No dazzle.toml found"
Run commands from project root (directory containing dazzle.toml)

### Port already in use
```bash
dazzle stop            # Stop existing container
dazzle serve -p 4000   # Use different port
```

### Docker issues
```bash
dazzle serve --local   # Run without Docker
```
"""


# =============================================================================
# Lookup Functions
# =============================================================================


def get_cli_help(command: str | None = None) -> dict[str, Any]:
    """
    Get CLI help for a specific command or general overview.

    Args:
        command: Command name (e.g., 'serve', 'test run') or None for overview

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
            "primary_command": "dazzle serve",
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
    workflows: dict[str, dict[str, Any]] = {
        "getting_started": {
            "name": "Getting Started with DAZZLE",
            "description": "Complete beginner's guide to building your first DAZZLE app",
            "steps": [
                {
                    "step": 1,
                    "action": "Create a new project",
                    "command": "dazzle init my-app && cd my-app",
                    "notes": "This creates dazzle.toml and dsl/app.dsl starter files",
                },
                {
                    "step": 2,
                    "action": "Understand the project structure",
                    "explanation": """
my-app/
├── dazzle.toml    # Project manifest (name, version)
├── dsl/
│   └── app.dsl    # Your DSL definitions
└── .dazzle/       # Runtime data (created on first run)
    └── data.db    # SQLite database""",
                },
                {
                    "step": 3,
                    "action": "Edit the DSL file",
                    "file": "dsl/app.dsl",
                    "example": """module my_app
app MyApp "My Application"

# Define your data model
entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false
  created_at: datetime auto_add

# Define the UI
surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field completed "Done"
  ux:
    purpose: "Track your daily tasks"
    sort: created_at desc
    empty: "No tasks yet. Create your first one!"

surface task_create "New Task":
  uses entity Task
  mode: create
  section main:
    field title "Title" """,
                },
                {
                    "step": 4,
                    "action": "Validate your DSL",
                    "command": "dazzle validate",
                    "notes": "Fix any syntax errors before running",
                },
                {
                    "step": 5,
                    "action": "Run the application",
                    "command": "dazzle serve",
                    "output": {
                        "ui": "http://localhost:3000",
                        "api": "http://localhost:8000/docs",
                    },
                    "notes": "Dazzle creates the database and runs both frontend and API",
                },
            ],
            "next_steps": [
                "Add more entities (use 'add_entity' workflow)",
                "Create a dashboard workspace (use 'add_workspace' workflow)",
                "Add personas for role-based access (use 'add_personas' workflow)",
                "Generate demo data: mcp__dazzle__propose_demo_blueprint",
                "Set up E2E testing (use 'setup_testing' workflow)",
            ],
            "demo_data_hint": """
After validation succeeds, generate realistic demo data:

1. Propose a demo data blueprint:
   mcp__dazzle__propose_demo_blueprint

2. Review and save the blueprint:
   mcp__dazzle__save_demo_blueprint

3. Generate demo data files:
   mcp__dazzle__generate_demo_data
""",
        },
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
                    "command": "dazzle serve",
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
                    "example": """entity Customer "Customer":
  id: uuid pk
  name: str(200) required
  email: email unique
  created_at: datetime auto_add""",
                },
                {
                    "step": 2,
                    "action": "Add CRUD surfaces",
                    "example": """surface customer_list "Customers":
  uses entity Customer
  mode: list
  section main:
    field name
    field email

surface customer_create "New Customer":
  uses entity Customer
  mode: create""",
                },
                {
                    "step": 3,
                    "action": "Validate",
                    "command": "dazzle validate",
                },
                {
                    "step": 4,
                    "action": "Restart app",
                    "command": "dazzle serve",
                    "notes": "Dazzle picks up changes automatically on restart",
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
                    "command": "dazzle serve --test-mode",
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
        "add_workspace": {
            "name": "Add a Dashboard Workspace",
            "description": "Create a workspace that aggregates multiple data views",
            "steps": [
                {
                    "step": 1,
                    "action": "Add workspace to DSL",
                    "file": "dsl/app.dsl",
                    "example": """workspace dashboard "Dashboard":
  purpose: "Overview of all active tasks and team metrics"

  # Recent urgent tasks
  urgent_tasks:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc
    limit: 5
    action: task_edit
    empty: "No urgent tasks!"

  # Activity summary
  recent_activity:
    source: Task
    filter: status = done
    sort: completed_at desc
    limit: 10
    display: timeline

  # Key metrics
  metrics:
    aggregate:
      total_tasks: count(Task)
      completed: count(Task where status = done)
      overdue: count(Task where due_date < today and status != done)""",
                },
                {
                    "step": 2,
                    "action": "Validate",
                    "command": "dazzle validate",
                },
                {
                    "step": 3,
                    "action": "Preview layout",
                    "command": "dazzle layout-plan --explain",
                    "notes": "See which archetype is selected and why",
                },
            ],
            "archetypes": [
                "FOCUS_METRIC - Single KPI with supporting data",
                "SCANNER_TABLE - Data table for scanning records",
                "DUAL_PANE_FLOW - List + detail side by side",
                "MONITOR_WALL - Multiple signal regions",
                "COMMAND_CENTER - Complex multi-region layout",
            ],
            "next_steps": [
                "Define personas for role-based access (use 'add_personas' workflow)",
                "Add attention signals to highlight important data",
                "Generate demo data: mcp__dazzle__propose_demo_blueprint",
            ],
            "persona_hint": """
You've created a workspace. Consider defining personas for role-based access:

  workspace dashboard → persona admin (full visibility)
  workspace customer_portal → persona customer (sees own data)
  workspace sales_dashboard → persona sales_rep (sees team data)

Use: get_workflow_guide('add_personas') for step-by-step instructions.
""",
        },
        "add_personas": {
            "name": "Add Role-Based Access with Personas",
            "description": "Define different views for admin, manager, and regular users",
            "steps": [
                {
                    "step": 1,
                    "action": "Add personas to surface UX block",
                    "file": "dsl/app.dsl",
                    "example": """surface user_list "Users":
  uses entity User
  mode: list

  section main:
    field name
    field email
    field role

  ux:
    purpose: "Manage user accounts"

    # Admin sees everything
    for admin:
      scope: all
      action_primary: user_create
      show_aggregate: total_users, active_count

    # Manager sees their department
    for manager:
      scope: department = current_user.department
      hide: salary, ssn
      action_primary: user_invite

    # Regular users see only themselves
    for member:
      scope: id = current_user.id
      read_only: true""",
                },
                {
                    "step": 2,
                    "action": "Add personas to workspace",
                    "example": """workspace dashboard "Dashboard":
  purpose: "Team overview"

  tasks:
    source: Task

  ux:
    for admin:
      scope: all
      purpose: "Full system visibility"

    for member:
      scope: assigned_to = current_user
      purpose: "Your personal tasks" """,
                },
            ],
            "persona_directives": {
                "scope": "Filter expression (all, owner = current_user, etc.)",
                "purpose": "Persona-specific purpose statement",
                "show": "Fields to display",
                "hide": "Fields to hide",
                "show_aggregate": "Metrics to display",
                "action_primary": "Default action surface",
                "read_only": "Disable editing (true/false)",
            },
        },
        "add_relationships": {
            "name": "Add Entity Relationships",
            "description": "Connect entities with foreign key references",
            "steps": [
                {
                    "step": 1,
                    "action": "Define related entities",
                    "example": """entity Project "Project":
  id: uuid pk
  name: str(200) required
  owner: ref User required

entity Task "Task":
  id: uuid pk
  title: str(200) required
  project: ref Project required
  assigned_to: ref User optional""",
                },
                {
                    "step": 2,
                    "action": "Show related data in surfaces",
                    "example": """surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field project.name "Project"
    field assigned_to.name "Assigned To" """,
                },
            ],
            "relationship_types": {
                "ref Entity required": "Must have a related record",
                "ref Entity optional": "Can be null",
                "ref Entity[]": "One-to-many (array of references)",
            },
        },
        "add_attention_signals": {
            "name": "Add Attention Signals",
            "description": "Alert users to important conditions in their data",
            "steps": [
                {
                    "step": 1,
                    "action": "Add attention blocks to surface UX",
                    "example": """surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status
    field due_date

  ux:
    purpose: "Track task progress"

    # Critical - action required immediately
    attention critical:
      when: due_date < today and status != done
      message: "Overdue!"
      action: task_edit

    # Warning - needs attention soon
    attention warning:
      when: due_date = today and status != done
      message: "Due today"

    # Notice - informational
    attention notice:
      when: status = blocked
      message: "Blocked - needs help" """,
                },
            ],
            "levels": {
                "critical": "Requires immediate action (red)",
                "warning": "Needs attention soon (yellow/orange)",
                "notice": "Worth noting (blue)",
                "info": "Informational only (gray)",
            },
        },
        "add_domain_service": {
            "name": "Add a Domain Service",
            "description": "Create custom business logic with DSL declaration and Python stub",
            "steps": [
                {
                    "step": 1,
                    "action": "Add service declaration to DSL",
                    "file": "dsl/app.dsl",
                    "example": """service calculate_discount "Calculate Order Discount":
  kind: domain_logic
  input:
    order_id: uuid required
    coupon_code: str(20)
  output:
    discount_amount: decimal(10,2)
    discount_type: str(20)
    applied_rules: json
  guarantees:
    - "Must not modify order record"
    - "Must validate coupon exists before applying"
  stub: python""",
                },
                {
                    "step": 2,
                    "action": "Validate DSL",
                    "command": "dazzle validate",
                    "notes": "Ensure service declaration is syntactically correct",
                },
                {
                    "step": 3,
                    "action": "Generate stub file",
                    "command": "dazzle stubs generate --service calculate_discount",
                    "creates": "stubs/calculate_discount.py",
                },
                {
                    "step": 4,
                    "action": "Implement the stub",
                    "file": "stubs/calculate_discount.py",
                    "example": """def calculate_discount(order_id: str, coupon_code: str | None = None) -> CalculateDiscountResult:
    order = db.get_order(order_id)

    # Check for valid coupon
    if coupon_code:
        coupon = db.get_coupon(coupon_code)
        if coupon and coupon.is_valid:
            return {
                "discount_amount": order.total * coupon.discount_percent,
                "discount_type": "coupon",
                "applied_rules": {"coupon": coupon_code, "percent": coupon.discount_percent}
            }

    # Apply default volume discount
    if order.total >= 100:
        return {
            "discount_amount": order.total * 0.10,
            "discount_type": "volume",
            "applied_rules": {"rule": "10% off orders over $100"}
        }

    return {"discount_amount": 0, "discount_type": "none", "applied_rules": {}}""",
                },
                {
                    "step": 5,
                    "action": "Restart app",
                    "command": "dazzle serve",
                    "notes": "Dazzle discovers and loads stubs automatically",
                },
            ],
            "service_kinds": {
                "domain_logic": "Business calculations (tax, pricing, scoring)",
                "validation": "Complex validation across fields/entities",
                "integration": "External API calls (payment, email, SMS)",
                "workflow": "Multi-step processes (approvals, fulfillment)",
            },
        },
        "pitch_deck": {
            "name": "Create Pitch Deck",
            "description": "Generate an investor pitch deck from your DSL project",
            "steps": [
                {
                    "step": 1,
                    "action": "Scaffold pitchspec",
                    "command": "pitch(operation='scaffold')",
                    "notes": "Creates pitchspec.yaml with template sections",
                },
                {
                    "step": 2,
                    "action": "Fill in company details",
                    "file": "pitchspec.yaml",
                    "notes": "Add company name, tagline, funding_ask, problem, solution, market sizing, team, and financials",
                },
                {
                    "step": 3,
                    "action": "Validate the pitchspec",
                    "command": "pitch(operation='validate')",
                    "notes": "Checks for structural errors and missing required fields",
                },
                {
                    "step": 4,
                    "action": "Generate the deck",
                    "command": "pitch(operation='generate', format='all')",
                    "notes": "Creates pitch_deck.pptx and pitch_narrative.md",
                },
                {
                    "step": 5,
                    "action": "Review content quality",
                    "command": "pitch(operation='review')",
                    "notes": "Analyzes each section for investor-readiness and gives specific improvement suggestions",
                },
                {
                    "step": 6,
                    "action": "Iterate on content",
                    "notes": "Address review suggestions, then re-run validate → generate → review until satisfied",
                },
            ],
            "next_steps": [
                "Use pitch(operation='get') to inspect current pitchspec contents",
                "Use pitch(operation='review') after each edit cycle to track improvement",
                "Add speaker_notes to sections for presenter guidance",
                "Add extra_slides for appendix material (case studies, technical architecture)",
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
                    "solution": "Run 'dazzle stop' or use -p flag for different port",
                },
                {
                    "problem": "Docker not running",
                    "solution": "Start Docker or use 'dazzle serve --local'",
                },
                {
                    "problem": "Validation errors",
                    "solution": "Run 'dazzle validate' and fix syntax errors",
                },
                {
                    "problem": "Tests fail to find elements",
                    "solution": "Check data-dazzle-* attributes, use --headed to debug",
                },
                {
                    "problem": "Database locked",
                    "solution": "Stop any running 'dazzle serve' instances",
                },
                {
                    "problem": "Changes not appearing",
                    "solution": "Restart 'dazzle serve' - hot reload coming in v0.3.3",
                },
            ],
        },
    }

    workflow_normalized = workflow.lower().replace("-", "_").replace(" ", "_")

    if workflow_normalized in workflows:
        workflow_data = workflows[workflow_normalized]
        result: dict[str, Any] = {"workflow": workflow, "found": True}
        result.update(workflow_data)
        return result

    return {
        "workflow": workflow,
        "found": False,
        "available_workflows": list(workflows.keys()),
    }
