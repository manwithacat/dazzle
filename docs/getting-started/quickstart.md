# Quick Start Guide

Get a working application from your Dazzle DSL in under 5 minutes.

## Prerequisites

- Dazzle installed ([Installation Guide](installation.md))
- PostgreSQL running (local or Docker)
- A terminal

## Step 1: Create a Project

```bash
dazzle init my_app
cd my_app
```

Or start from a built-in example:

```bash
dazzle init my_app --from simple_task
cd my_app
```

## Step 2: Validate Your DSL

```bash
dazzle validate
```

Fix any errors before proceeding.

## Step 3: Set Up PostgreSQL

Dazzle requires PostgreSQL for data persistence.

```bash
# Start PostgreSQL via Docker (quick option)
docker run -d --name dazzle-postgres \
  -e POSTGRES_USER=dazzle \
  -e POSTGRES_PASSWORD=dazzle \
  -e POSTGRES_DB=dazzle \
  -p 5432:5432 \
  postgres:16

# Set the database URL
export DATABASE_URL=postgresql://dazzle:dazzle@localhost:5432/dazzle
```

Tables are created automatically on first startup.

## Step 4: Run the Application

```bash
# Docker mode (default — recommended)
dazzle serve

# Or run locally without Docker
dazzle serve --local
```

This starts:

- **UI** at `http://localhost:3000`
- **API** at `http://localhost:8000/api/`
- **API Docs** at `http://localhost:8000/docs`

## Step 5: Try the API

Create a record via the API:

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Learn Dazzle", "status": "open"}'
```

## Example: Simple Task Manager

Given this DSL in `dsl/app.dsl`:

```dsl
module simple_task
app simple_task "Simple Task Manager"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[open, in_progress, done] = open
  created_at: datetime auto_add

surface task_list "Task List" -> Task list:
  section main:
    field title "Title"
    field status "Status"
```

Validate and run:

```bash
dazzle validate
dazzle serve --local
```

## Development Workflow

```bash
# Terminal 1: Serve with hot reload
dazzle serve --local --watch

# Terminal 2: Edit your DSL files
# Changes are picked up automatically
```

## Useful Commands

| Command | Purpose |
|---------|---------|
| `dazzle validate` | Check DSL for errors |
| `dazzle lint` | Extended validation with style checks |
| `dazzle serve` | Start the full-stack app |
| `dazzle serve --local --watch` | Local mode with hot reload |
| `dazzle doctor` | Check environment health |
| `dazzle inspect` | Inspect project structure |

## Next Steps

- [Your First App](first-app.md) — Build a complete task manager step by step
- [CLI Reference](../reference/cli.md) — All command options
- [Architecture](../architecture/overview.md) — How Dazzle works internally
- [MCP Server](../architecture/mcp-server.md) — AI-assisted development with Claude Code
