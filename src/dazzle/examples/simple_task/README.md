# Simple Task Manager

> **Complexity**: Beginner | **Entities**: 1 | **DSL Lines**: ~160

A personal task management application demonstrating DAZZLE's core features. This is the recommended starting point for learning the DSL.

## Quick Start

```bash
cd examples/simple_task
dazzle dnr serve
```

- **UI**: http://localhost:3000
- **API**: http://localhost:8000/docs

## What This Example Demonstrates

### DSL Features

| Feature | Usage |
|---------|-------|
| **Entity Definition** | Single `Task` entity with various field types |
| **Field Types** | `uuid`, `str(n)`, `text`, `enum`, `date`, `datetime` |
| **Field Modifiers** | `required`, `pk`, `auto_add`, `auto_update`, defaults |
| **Surfaces** | All 4 CRUD modes: `list`, `view`, `create`, `edit` |
| **UX Block** | `purpose`, `sort`, `filter`, `search`, `empty` |
| **Attention Signals** | `warning` and `notice` with conditional expressions |
| **Workspaces** | Metrics aggregation, filtered regions, limits |

### Architecture Pattern

```
SPEC.md          →  Human-readable requirements
    ↓
dsl/app.dsl      →  DAZZLE DSL implementation
    ↓
DNR Runtime      →  Live application (no code generation)
    ↓
E2E Tests        →  Automated validation
```

## Project Structure

```
simple_task/
├── SPEC.md              # Product specification (refined requirements)
├── README.md            # This file
├── dazzle.toml          # Project configuration
├── dsl/
│   └── app.dsl          # DAZZLE DSL definition
├── tests/
│   └── e2e/             # E2E test files
└── testspec.json        # Generated test specification
```

## The Specification Journey

### 1. SPEC.md - The Starting Point

The `SPEC.md` represents a refined product specification - what a founder might produce after working with an LLM assistant to clarify their requirements. It includes:

- **Vision Statement**: What problem does this solve?
- **User Personas**: Who will use this?
- **Domain Model**: Entities, fields, and business rules
- **UI Specification**: Surfaces with purpose, fields, and behaviors
- **Workspace Specification**: Dashboard layouts and data regions
- **User Stories**: Acceptance criteria with test flows

### 2. DSL - The Implementation

The `dsl/app.dsl` translates the spec into DAZZLE's declarative syntax:

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  ...

surface task_list "Task List":
  uses entity Task
  mode: list
  ux:
    attention warning:
      when: due_date < today and status != done
      message: "Overdue task"
```

### 3. Running App - The Result

`dazzle dnr serve` starts a fully functional application:
- **Backend**: FastAPI with SQLite persistence
- **Frontend**: Signals-based reactive UI
- **Features**: Full CRUD, filtering, search, attention signals

## User Stories

| ID | Story | Test Status |
|----|-------|-------------|
| US-1 | Create a Task | Automated |
| US-2 | View Task Details | Automated |
| US-3 | Update Task Status | Automated |
| US-4 | Track Overdue Tasks | Automated |
| US-5 | Delete a Task | Automated |

## Running Tests

```bash
# Generate test specification from DSL
dazzle test generate

# Run E2E tests (requires running server)
dazzle test run

# Or run directly with pytest
pytest tests/e2e/ -v
```

## Learning Path

After understanding this example, progress to:

1. **contact_manager** (Beginner+) - List+detail pattern, DUAL_PANE_FLOW archetype
2. **support_tickets** (Intermediate) - Multi-entity relationships, refs
3. **ops_dashboard** (Intermediate+) - Personas, COMMAND_CENTER archetype
4. **fieldtest_hub** (Advanced) - Complex domain, access rules, persona scoping

## Key Concepts Illustrated

### Attention Signals
```dsl
attention warning:
  when: due_date < today and status != done
  message: "Overdue task"
```
Attention signals highlight important data conditions in the UI without writing custom code.

### Workspace Regions
```dsl
workspace dashboard "Task Dashboard":
  metrics:
    source: Task
    aggregate:
      total: count(Task)
      todo: count(Task where status = todo)
```
Workspaces compose multiple data views with aggregations and filters.

### UX Directives
```dsl
ux:
  purpose: "View and manage all tasks at a glance"
  sort: created_at desc
  filter: status, priority
  search: title, description
  empty: "No tasks yet. Create your first task!"
```
The `ux` block provides semantic hints for the UI layer.

## DSL Quick Reference

### Field Types
| Type | Example | Description |
|------|---------|-------------|
| `str(N)` | `title: str(200)` | String with max length |
| `text` | `description: text` | Unlimited text |
| `enum[...]` | `status: enum[a,b,c]` | Enumerated values |
| `date` | `due_date: date` | Date only |
| `datetime` | `created_at: datetime` | Date and time |
| `uuid` | `id: uuid pk` | Unique identifier |

### Field Modifiers
| Modifier | Example | Description |
|----------|---------|-------------|
| `required` | `title: str required` | Must have value |
| `pk` | `id: uuid pk` | Primary key |
| `=value` | `status: enum[...]=todo` | Default value |
| `auto_add` | `created_at: datetime auto_add` | Set on create |
| `auto_update` | `updated_at: datetime auto_update` | Set on update |

### Surface Modes
| Mode | Purpose |
|------|---------|
| `list` | Table/grid of multiple records |
| `view` | Read-only detail of one record |
| `create` | Form to create new record |
| `edit` | Form to update existing record |

## Customization Ideas

Try extending this example:

1. Add a `category` enum field to Task
2. Create a new workspace for "Weekly Review"
3. Add an attention signal for tasks due tomorrow
4. Create a surface for bulk status updates

## Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

### List View with Data
![List View](screenshots/14_list_view_data.png)

### Create Form
![Create Form](screenshots/05_create_form_no_inputs.png)

---

*Part of the DAZZLE Examples collection. See `/examples/README.md` for the full learning path.*
