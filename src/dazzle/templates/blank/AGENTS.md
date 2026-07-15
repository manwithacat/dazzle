# AGENTS.md

Canonical project instructions for **all** coding agents (any harness).
Harness adapters (`.claude/CLAUDE.md`, `.github/copilot-instructions.md`) stay
thin — project facts live only here. After `dazzle agent sync`, a **Workflows**
section is added/refreshed for available agent commands.

## Project Overview

This is a Dazzle project — a DSL-first application. Domain models, surfaces, and
rules live in `dsl/`; the runtime executes the linked AppSpec directly.

```bash
dazzle validate
dazzle serve
# UI: http://localhost:3000 | API: http://localhost:8000/docs
```

## MCP Tools

When the Dazzle MCP server is connected, prefer MCP tools for quick lookups:

- `validate_dsl` / `dsl.validate` — Validate DSL files
- `list_modules` — List project modules
- `inspect_entity` / `inspect_surface` — Inspect definitions
- `lookup_concept` — Look up DSL concepts and patterns
- `find_examples` — Find example code
- `get_workflow_guide` — Step-by-step guides

## Primary Tasks

1. **Write DSL** in the `dsl/` directory
2. **Validate** with `dazzle validate` (or MCP)
3. **Run** with `dazzle serve`
4. **Fix validation errors** by editing `.dsl` files
5. Answer questions about Dazzle DSL syntax and capabilities

## Epistemic layout

| Rank | Location | Role |
|------|----------|------|
| 1 | **`stems/`** | Domain stems (compressed app judgement) |
| 2 | **This file** | Always-on policy + workflows |
| 3 | **`dsl/`** | Executable model (expression of stems) |
| 4 | **SPEC.md** | Narrative requirements (expression) |

Framework stems (DSL-first, hypermedia SSR, …) live in the Dazzle monorepo
`stems/` when developing against source, or in published package docs.

## Project Structure

```
.
├── AGENTS.md           # This file — canonical agent policy
├── stems/              # Domain epistemic stems (INDEX + short stem files)
├── dazzle.toml         # Project configuration
├── SPEC.md             # Natural language requirements (optional)
├── dsl/                # DSL specification files
│   └── *.dsl
├── .agents/skills/     # Portable agent workflows (after dazzle agent sync)
├── .claude/            # Thin harness adapter + discovery shims
└── .dazzle/            # Runtime state and logs (gitignored)
```

## Common Workflows

### Creating DSL from Requirements

If the user has requirements in SPEC.md or describes them:

1. Write entities, surfaces, and other constructs in `.dsl` files
2. Validate with `dazzle validate`
3. Run with `dazzle serve`

### Working with Existing DSL

1. Read existing `.dsl` files in `dsl/`
2. Make modifications as requested
3. Always validate after changes
4. Run with `dazzle serve` to test

### Running the Application

```bash
dazzle serve
```

- UI: http://localhost:3000
- API: http://localhost:8000/docs

### Environment Setup

```bash
# uv is the supported toolchain (matches Heroku's uv buildpack)
uv venv && source .venv/bin/activate && uv pip install -r requirements.txt
# Prefer: dazzle deploy heroku  → pyproject.toml + uv.lock + .python-version
```

## DSL Quick Reference

### Multi-Module Projects

Each `.dsl` file should declare its module and import dependencies:

```dsl
module myapp.core

# Import entities from other modules
use myapp.other_module

app myapp "My Application"

entity User "User":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  created_at: datetime auto_add
```

### Entity with Archetypes and Patterns

```dsl
entity Task "Task":
  intent: "Work items to track progress"
  domain: project_management
  patterns: lifecycle, audit

  id: uuid pk
  title: str(200) required
  description: text optional
  status: enum[open,in_progress,done]=open
  priority: enum[low,medium,high]=medium
  due_date: date optional
  assignee: ref User optional
```

### Surface (UI)

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field status "Status"
    field assignee "Assigned To"
```

### Field Types

- `uuid`, `str(n)`, `text`, `int`, `decimal(p,s)`, `bool`
- `datetime`, `date`
- `email` — validated email address
- `enum[option1,option2,option3]` — enumerated values
- `ref OtherEntity` — foreign key relationship
- `has_many OtherEntity` — one-to-many relationship
- `belongs_to OtherEntity` — inverse of has_many

### Modifiers

- `pk` — Primary key
- `required` — Not nullable
- `optional` — Nullable (default)
- `unique` — Unique constraint
- `auto_add` — Set on creation
- `auto_update` — Update on save
- `=value` — Default value

### Reserved Keywords

Some words are reserved and cannot be used as enum values:

- Use `add/modify/remove` instead of `create/update/delete`
- Use `mail` instead of `email` for channel enums
- Use `sent` instead of `submitted`

Use MCP `lookup_concept` with term `reserved_keywords` for the full list.

## Important Reminders

1. **Always validate before running** — `dazzle validate` first
2. **DSL files go in `dsl/`** — not the project root
3. **Use module imports** — add `use module_name` when referencing entities from other modules

## Agent Capabilities

You can:

- Write and modify DSL files
- Run dazzle commands (validate, serve, lint, etc.)
- Debug validation errors
- Suggest DSL patterns and best practices

You should not:

- Modify runtime files in `.dazzle/` without a clear reason
- Create files outside the project structure without user request

Primary role: help users create applications using Dazzle DSL.
