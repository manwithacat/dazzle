# DAZZLE Examples

A curated collection of example projects demonstrating DAZZLE's capabilities, organized by complexity level. Each example shows the complete journey from product specification to working application.

## Quick Start

```bash
cd examples/simple_task
dazzle dnr serve
```

Open http://localhost:3000 to see the running app.

---

## Learning Path

The examples are organized in a progressive learning sequence. Each builds on concepts from the previous level.

| Level | Example | Entities | Key Concepts |
|-------|---------|----------|--------------|
| 1. **Beginner** | [simple_task](simple_task/) | 1 | Entity basics, CRUD surfaces, workspaces, attention signals |
| 2. **Beginner+** | [contact_manager](contact_manager/) | 1 | DUAL_PANE_FLOW archetype, signal weighting, list+detail pattern |
| 3. **Intermediate** | [support_tickets](support_tickets/) | 3 | Entity relationships (refs), indexes, multi-entity surfaces |
| 4. **Intermediate+** | [ops_dashboard](ops_dashboard/) | 2 | Personas, COMMAND_CENTER archetype, engine hints |
| 5. **Advanced** | [fieldtest_hub](fieldtest_hub/) | 6 | Complex domain, persona scoping, access rules, attention signals |

---

## Example Details

### 1. Simple Task Manager (Beginner)

**Location**: [`simple_task/`](simple_task/)

A personal task management app - the recommended starting point for learning DAZZLE.

**What You'll Learn**:
- Entity definition with various field types
- All four surface modes (list, view, create, edit)
- UX blocks (purpose, sort, filter, search, empty)
- Attention signals (warning, notice)
- Workspace composition with metrics and filtered regions

**Quick Start**:
```bash
cd simple_task && dazzle dnr serve
```

---

### 2. Contact Manager (Beginner+)

**Location**: [`contact_manager/`](contact_manager/)

A contacts application demonstrating the list+detail pattern.

**What You'll Learn**:
- DUAL_PANE_FLOW archetype (master-detail layout)
- Signal weighting for layout selection
- Workspace with paired signals

**Quick Start**:
```bash
cd contact_manager && dazzle dnr serve
```

---

### 3. Support Ticket System (Intermediate)

**Location**: [`support_tickets/`](support_tickets/)

A multi-entity support system with user, ticket, and comment relationships.

**What You'll Learn**:
- Entity relationships with `ref` fields
- Required vs optional references
- Database indexes for performance
- Multiple surfaces per entity
- Cross-entity navigation

**Quick Start**:
```bash
cd support_tickets && dazzle dnr serve
```

---

### 4. Operations Dashboard (Intermediate+)

**Location**: [`ops_dashboard/`](ops_dashboard/)

A real-time operations monitoring dashboard for DevOps teams.

**What You'll Learn**:
- Persona definition with proficiency levels
- COMMAND_CENTER archetype for expert users
- Engine hints for layout control
- Dense, information-rich interfaces

**Quick Start**:
```bash
cd ops_dashboard && dazzle dnr serve
```

---

### 5. FieldTest Hub (Advanced)

**Location**: [`fieldtest_hub/`](fieldtest_hub/)

A complex hardware field testing platform with multiple user roles.

**What You'll Learn**:
- 6-entity domain model with relationships
- Persona-aware surface scoping (`for engineer`, `for tester`)
- Access rules for data visibility
- Complex filtering and aggregations
- Real-world workflow modeling

**Quick Start**:
```bash
cd fieldtest_hub && dazzle dnr serve
```

---

## Example Structure

Each example follows a consistent structure:

```
example_name/
├── SPEC.md              # Product specification (refined requirements)
├── README.md            # Example documentation
├── dazzle.toml          # Project configuration
├── dsl/
│   └── app.dsl          # DAZZLE DSL definition
└── testspec.json        # Generated test specification (if present)
```

### The Specification Journey

```
SPEC.md          →  Human-readable requirements
    ↓                (refined through LLM collaboration)
dsl/app.dsl      →  DAZZLE DSL implementation
    ↓                (declarative, stack-agnostic)
DNR Runtime      →  Live application
    ↓                (no code generation needed)
E2E Tests        →  Automated validation
                     (generated from spec)
```

---

## Running Examples

### Start an Example
```bash
cd examples/<name>
dazzle dnr serve
```

### Validate DSL
```bash
dazzle validate
```

### Generate Test Specification
```bash
dazzle test generate
```

### Run E2E Tests
```bash
dazzle test run
```

---

## DSL Quick Reference

### Entity Definition
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done]=todo
  created_at: datetime auto_add
```

### Surface Definition
```dsl
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"

  ux:
    purpose: "View all tasks"
    sort: created_at desc
    filter: status
```

### Workspace Definition
```dsl
workspace dashboard "Dashboard":
  purpose: "Overview with metrics"

  metrics:
    source: Task
    aggregate:
      total: count(Task)
```

### Attention Signal
```dsl
ux:
  attention warning:
    when: due_date < today and status != done
    message: "Overdue"
```

---

## Archived Examples

Additional examples are available in `_archive/` for reference:
- `uptime_monitor` - FOCUS_METRIC archetype demo
- `inventory_scanner` - SCANNER_TABLE archetype demo
- `email_client` - MONITOR_WALL archetype demo
- `urban_canopy` - Volunteer tree monitoring
- `archetype_showcase` - All 5 archetypes in one project

These were consolidated to focus the learning path on the 5 core examples.

---

## Creating Your Own

```bash
# Initialize a new project
dazzle init my_project
cd my_project

# Edit the DSL
vim dsl/app.dsl

# Validate
dazzle validate

# Run
dazzle dnr serve
```

---

## Getting Help

- **Documentation**: See `docs/` directory
- **DSL Reference**: `docs/DAZZLE_DSL_QUICK_REFERENCE.md`
- **Issues**: https://github.com/anthropics/dazzle/issues

---

*Part of the DAZZLE project - DSL-first application development.*
