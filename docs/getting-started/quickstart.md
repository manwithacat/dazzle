# Quick Start Guide

Get a working application from your Dazzle DSL in under 5 minutes.

## What you'll write

A Dazzle app is a DSL spec. The `entity` is the core building block — it becomes a database table, a typed REST API, and a UI surface:

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[open, in_progress, done] = open
  due: date
```

## Prerequisites

- Dazzle installed ([Installation Guide](installation.md))
- PostgreSQL running locally (or a managed instance)
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

Dazzle requires PostgreSQL for data persistence. Bring your own — a local
install or a managed instance — and point `DATABASE_URL` at it:

```bash
# Point at your Postgres
export DATABASE_URL=postgresql://dazzle:dazzle@localhost:5432/dazzle
```

Tables are created automatically on first startup.

## Step 4: Run the Application

```bash
dazzle serve
```

`dazzle serve` connects to the Postgres in your `DATABASE_URL` (and Redis in
`REDIS_URL`, if set). This starts:

- **UI** at `http://localhost:3000`
- **API** at `http://localhost:8000/api/`
- **API Docs** at `http://localhost:8000/docs`

## Step 5: Try the API

Create a record via the API:

```bash
curl -X POST http://localhost:8000/_dazzle/tasks \
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
dazzle serve
```

## Development Workflow

```bash
# Terminal 1: Serve with hot reload
dazzle serve --watch

# Terminal 2: Edit your DSL files
# Changes are picked up automatically
```

## Useful Commands

| Command | Purpose |
|---------|---------|
| `dazzle validate` | Check DSL for errors |
| `dazzle lint` | Extended validation with style checks |
| `dazzle serve` | Start the full-stack app |
| `dazzle serve --watch` | Serve with hot reload |
| `dazzle doctor` | Check environment health |
| `dazzle inspect` | Inspect project structure |

## Next Steps

- [Your First App](first-app.md) — Build a complete task manager step by step
- [CLI Reference](../reference/cli.md) — All command options
- [Architecture](../architecture/overview.md) — How Dazzle works internally
- [MCP Server](../architecture/mcp-server.md) — AI-assisted development with Claude Code
