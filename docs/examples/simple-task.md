# Simple Task Manager

> The "Hello World" of DAZZLE - a minimal CRUD application demonstrating core DSL concepts.

## Quick Start

```bash
cd examples/simple_task
dazzle dnr serve
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

## Overview

| Attribute | Value |
|-----------|-------|
| **Complexity** | Beginner |
| **CI Priority** | P0 (blocks PRs) |
| **Entities** | Task |
| **Surfaces** | list, view, create, edit |
| **Workspaces** | dashboard, my_work |

## DSL Specification

**Source**: [examples/simple_task/dsl/app.dsl](https://github.com/manwithacat/dazzle/blob/main/examples/simple_task/dsl/app.dsl)

### Entity: Task

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  due_date: date
  assigned_to: str(100)
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

### Surfaces

- **task_list** - Main task overview (list mode)
- **task_detail** - Individual task view (view mode)
- **task_create** - New task form (create mode)
- **task_edit** - Edit existing task (edit mode)

### Workspaces

#### Task Dashboard
```dsl
workspace dashboard "Task Dashboard":
  purpose: "Overview of all tasks with key metrics"

  task_count:
    source: Task
    aggregate:
      total: count(Task)

  urgent_tasks:
    source: Task
    limit: 5

  all_tasks:
    source: Task
```

#### My Work
```dsl
workspace my_work "My Work":
  purpose: "Personal task view for assigned work"

  in_progress:
    source: Task
    limit: 10

  upcoming:
    source: Task
    limit: 5
```

## E2E Test Coverage

| Metric | Coverage |
|--------|----------|
| Routes | 4 |
| CRUD Operations | Full |
| Components | 4 |

### Test Commands

```bash
# Generate test specification
dazzle test generate -o testspec.json

# Run E2E tests
dazzle test run --verbose

# List available test flows
dazzle test list
```

## Screenshots

### Dashboard
![Dashboard](https://raw.githubusercontent.com/manwithacat/dazzle/main/examples/simple_task/screenshots/dashboard.png)

### List View
![List View](https://raw.githubusercontent.com/manwithacat/dazzle/main/examples/simple_task/screenshots/list_view.png)

### Create Form
![Create Form](https://raw.githubusercontent.com/manwithacat/dazzle/main/examples/simple_task/screenshots/create_form.png)

## API Endpoints

When running, the following endpoints are available:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List all tasks |
| POST | `/api/tasks` | Create a task |
| GET | `/api/tasks/{id}` | Get task by ID |
| PUT | `/api/tasks/{id}` | Update task |
| DELETE | `/api/tasks/{id}` | Delete task |

## Related Examples

- [Contact Manager](contact-manager.md) - Multi-entity with relationships
- [Uptime Monitor](uptime-monitor.md) - FOCUS_METRIC workspace archetype
