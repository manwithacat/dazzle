# DAZZLE Philosophy

> How DAZZLE's features work together to enable specification-driven development

## Core Principle: DSL-First

DAZZLE inverts the traditional development process. Instead of writing code that implements a specification, you write the specification and DAZZLE runs it directly.

```
Traditional:      Spec → Write Code → Deploy
DAZZLE:          DSL → Run Immediately
```

This isn't code generation - it's **specification execution**. Your DSL files ARE your application.

## The DSL Layer

The DAZZLE DSL captures your application's **semantic intent** rather than implementation details:

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,done]=todo
```

This declares WHAT a Task is, not HOW to store or display it. The runtime interprets this intent.

## From Intent to Interface

### Entities → Data Model

Entities define your domain model. DAZZLE automatically provides:
- SQLite persistence with proper types and constraints
- CRUD API endpoints with validation
- Data access patterns optimized for your schema

### Surfaces → UI Components

Surfaces describe how entities are presented:

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field status "Status"
```

The runtime generates appropriate UI components based on:
- **Mode**: list, view, create, edit
- **Field types**: Each type maps to appropriate input/display components
- **Layout**: Sections organize fields into logical groups

### Workspaces → User Experiences

Workspaces compose multiple data views for specific user goals:

```dsl
workspace dashboard "Dashboard":
  purpose: "Overview of all tasks"

  task_count:
    source: Task
    aggregate:
      total: count(Task)

  recent_tasks:
    source: Task
    limit: 5
```

Workspaces use **attention signals** to allocate screen real estate:
- Aggregates become KPI displays
- Limited lists become curated views
- Unlimited sources become browsable tables

The runtime automatically selects appropriate **archetypes**:
- `FOCUS_METRIC` - Single dominant KPI (executive dashboards)
- `DUAL_PANE_FLOW` - List + detail (master-detail)
- `SCANNER_TABLE` - Data-heavy browsing (admin panels)
- `COMMAND_CENTER` - Multi-signal monitoring (ops dashboards)

## The Runtime Architecture

```
DSL Files → Parser → IR (AppSpec) → DNR Runtime
                                    ├── FastAPI Backend
                                    │   └── SQLite + CRUD endpoints
                                    └── Signals-based UI
                                        └── Reactive components
```

### Backend (FastAPI)

The backend translates your DSL into:
- Database schema (SQLite)
- REST API endpoints
- Validation rules
- Query optimization

### Frontend (Signals)

The UI uses a signals-based architecture:
- Reactive updates without virtual DOM
- Entity-aware components
- Automatic form generation
- Semantic HTML with data attributes

## Why This Matters

### 1. Single Source of Truth

Your DSL files are the canonical definition of your application. There's no drift between documentation, API, and UI because they all derive from the same source.

### 2. Rapid Iteration

Change the DSL, see the result immediately. No compilation, no code generation, no deployment.

### 3. AI-Native

The DSL is designed for both human and LLM consumption:
- Minimal syntax reduces token usage
- Semantic structure enables AI understanding
- MCP integration provides context to Claude Code

### 4. Portable Semantics

The IR (AppSpec) captures your application's semantics independently of implementation. This enables:
- Multiple runtime targets
- Code generation for deployment
- Future platform migration

## The Development Flow

1. **Describe** your domain with entities
2. **Define** how data is presented with surfaces
3. **Compose** user experiences with workspaces
4. **Run** instantly with DNR
5. **Iterate** based on feedback

```bash
# Start anywhere
dazzle init my_app
cd my_app

# Edit dsl/app.dsl
# Add entities, surfaces, workspaces

# See results immediately
dazzle dnr serve
```

## When to Use What

| Construct | Purpose | Example |
|-----------|---------|---------|
| **Entity** | Define data model | User, Task, Order |
| **Surface** | Present single entity | user_list, task_edit |
| **Workspace** | Compose multiple views | dashboard, admin_panel |
| **Experience** | Multi-step workflows | onboarding, checkout |
| **Service** | External API integration | GitHub, Stripe |

## The Optional Code Generation Path

DNR is the primary runtime, but DAZZLE also supports code generation for specialized deployment:

```bash
# Development (recommended)
dazzle dnr serve

# Custom deployment (optional)
dazzle build --stack docker
```

Use code generation when you need:
- Deployment to environments without Python
- Integration with existing codebases
- Custom framework requirements

## Summary

DAZZLE is built on the belief that applications are specifications first, code second. By executing specifications directly, we eliminate the gap between intent and implementation, enabling faster development, easier maintenance, and seamless AI assistance.

Write what you mean. Run what you write.
