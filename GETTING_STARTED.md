# Getting Started with DAZZLE

This guide walks you through creating your first DAZZLE application using the CLI.

## Prerequisites

- Python 3.11+
- DAZZLE installed (`pip install dazzle` or `pip install -e '.[dev]'` for development)

Verify installation:

```bash
dazzle --version
```

## Quick Start (5 minutes)

### Option 1: Start from an Example

The fastest way to get started is to use a built-in example:

```bash
# Create a new project from the simple_task example
dazzle init my_task_app --from simple_task

# Navigate to your project
cd my_task_app

# Validate the DSL
dazzle validate

# Run the application
dazzle dnr serve
```

Your app is now running at:
- **UI**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Option 2: Start from Scratch

Create a blank project and build your own DSL:

```bash
# Create a new empty project
dazzle init my_project

# Navigate to your project
cd my_project

# Edit SPEC.md with your requirements, then create DSL files
# See "Writing Your First DSL" below
```

## Project Structure

After initialization, your project will have:

```
my_task_app/
├── dazzle.toml          # Project manifest
├── dsl/
│   └── app.dsl          # Your DSL definitions
├── SPEC.md              # Natural language requirements
├── README.md            # Project readme
├── LLM_CONTEXT.md       # Context for AI assistants
├── .claude/             # Claude Code instructions
├── .llm/                # LLM context files
└── .dazzle/             # Runtime data (created on first run)
    └── data.db          # SQLite database
```

## Essential CLI Commands

### Project Setup

```bash
# Initialize new project
dazzle init my_project

# Initialize from example
dazzle init my_project --from simple_task

# List available examples
dazzle init --list
```

### Development

```bash
# Validate DSL syntax and references
dazzle validate

# Run extended lint checks
dazzle lint

# Inspect the generated AppSpec
dazzle inspect

# View layout plans for workspaces
dazzle layout-plan

# Explain archetype selection
dazzle layout-plan --explain
```

### Running Your App

```bash
# Start the development server (recommended)
dazzle dnr serve

# Check DNR installation status
dazzle dnr info

# Build production UI assets
dazzle dnr build-ui
```

## Writing Your First DSL

The DAZZLE DSL defines your application structure. Here's a minimal example:

```dsl
# dsl/app.dsl
module my_app.core

app my_app "My Application"

# Define an entity (database table)
entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false
  created_at: datetime auto_add

# Define a surface (UI view)
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field completed "Done"
    field created_at "Created"

# Define a workspace (dashboard)
workspace dashboard "Dashboard":
  purpose: "Task overview"

  task_count:
    source: Task
    aggregate:
      total: count(Task)

  recent_tasks:
    source: Task
    limit: 5
```

Save this file, then:

```bash
dazzle validate   # Check for errors
dazzle dnr serve  # Run the app
```

## Available Examples

View all examples with `dazzle init --list`:

| Example | Description |
|---------|-------------|
| `simple_task` | Basic CRUD app - perfect for learning |
| `contact_manager` | Multiple entities with relationships |
| `uptime_monitor` | Single KPI dashboard (FOCUS_METRIC archetype) |
| `email_client` | Multi-signal dashboard (MONITOR_WALL archetype) |
| `ops_dashboard` | Operations console (COMMAND_CENTER archetype) |
| `support_tickets` | Multi-entity system with workflows |

## Layout Archetypes

DAZZLE automatically selects the best layout for your workspace:

| Archetype | Best For | Triggered By |
|-----------|----------|--------------|
| FOCUS_METRIC | Single KPI dashboards | Dominant KPI signal (weight > 0.7) |
| SCANNER_TABLE | Data tables with filters | Strong table signal (weight > 0.6) |
| DUAL_PANE_FLOW | Master-detail views | List + detail signals |
| MONITOR_WALL | Multi-widget dashboards | 3-8 signals |
| COMMAND_CENTER | Expert operations | 5+ signals with expert persona |

View archetype selection with:

```bash
dazzle layout-plan --explain
```

## Next Steps

1. **Explore the DSL Reference**: See `docs/DAZZLE_DSL_REFERENCE_0_1.md`
2. **Try Different Examples**: `dazzle init --list`
3. **Read the API Docs**: Visit http://localhost:8000/docs when running
4. **Check the Roadmap**: See `ROADMAP.md` for upcoming features

## Troubleshooting

### "OK: spec is valid" but app won't start

Check DNR installation:

```bash
dazzle dnr info
```

If components are missing, reinstall:

```bash
pip install -e '.[dev]'
```

### "No module named dazzle_dnr_back"

The DNR backend package is required. Install with:

```bash
pip install -e '.[dev]'
```

### Port already in use

The default ports are 3000 (UI) and 8000 (API). Kill existing processes or use different ports:

```bash
# Find processes using ports
lsof -i :3000
lsof -i :8000

# Kill if needed
kill -9 <PID>
```

## Getting Help

- **Documentation**: `docs/` directory
- **Examples**: `examples/` directory
- **Issues**: https://github.com/manwithacat/dazzle/issues
- **Roadmap**: `ROADMAP.md`

---

**Version**: 0.3.0 | **Last Updated**: November 2025
