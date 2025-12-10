# DAZZLE Capabilities

**Version**: 0.2.x
**Last Updated**: 2025-12-01
**Status**: Authoritative reference for current capabilities

This document describes what DAZZLE can do today with the **Dazzle Native Runtime (DNR)**.

---

## Table of Contents

1. [Runtime Overview](#runtime-overview)
2. [DSL Constructs](#dsl-constructs)
3. [Field Types](#field-types)
4. [Constraints & Modifiers](#constraints--modifiers)
5. [Surface Modes](#surface-modes)
6. [Workspace Archetypes](#workspace-archetypes)
7. [UX Semantic Layer](#ux-semantic-layer)
8. [Authentication](#authentication)
9. [E2E Testing](#e2e-testing)
10. [Code Generation (Optional)](#code-generation-optional)
11. [Tooling](#tooling)
12. [Known Limitations](#known-limitations)

---

## Runtime Overview

### DNR (Primary Runtime)

DAZZLE applications run directly via the **Dazzle Native Runtime (DNR)** - no code generation required.

```bash
cd examples/simple_task
dazzle dnr serve
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

**What DNR Provides**:
- **FastAPI Backend**: Auto-generated CRUD endpoints with SQLite persistence
- **Signals-based UI**: Reactive JavaScript frontend (no virtual DOM)
- **Hot Reload**: Changes to DSL files reflect immediately
- **OpenAPI Docs**: Automatic Swagger UI at `/docs`
- **Session Auth**: Built-in authentication with persona support

### Architecture

```
DSL Files → Parser → IR (AppSpec) → DNR Runtime (live app)
                                  → Code Generation (optional)
```

---

## DSL Constructs

| Construct | Status | Description |
|-----------|--------|-------------|
| `entity` | ✅ Stable | Domain models with typed fields |
| `surface` | ✅ Stable | UI entry points (CRUD views) |
| `workspace` | ✅ Stable | Semantic layouts with attention signals |
| `experience` | ✅ Stable | Multi-step workflows |
| `service` | ✅ Stable | External API configurations |
| `foreign_model` | ✅ Stable | External data shapes |
| `integration` | ⚠️ Basic | Service connections (stubs) |
| `persona` | ✅ Stable | Role-based access patterns |

### Example Entity

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false
  priority: enum[low,medium,high]=medium
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

### Example Surface

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field completed "Done"
    field priority "Priority"
```

### Example Workspace

```dsl
workspace dashboard "Dashboard":
  purpose: "Task overview"

  task_stats:
    source: Task
    aggregate:
      total: count(Task)
      completed: count(Task) where completed=true

  recent_tasks:
    source: Task
    limit: 5
    order: created_at desc
```

---

## Field Types

| Type | DNR Backend | DNR UI | Description |
|------|-------------|--------|-------------|
| `str(N)` | ✅ VARCHAR | ✅ text input | String max N chars |
| `text` | ✅ TEXT | ✅ textarea | Unlimited text |
| `int` | ✅ INTEGER | ✅ number input | Integer |
| `decimal(P,S)` | ✅ DECIMAL | ✅ number input | Decimal precision |
| `float` | ✅ FLOAT | ✅ number input | Floating point |
| `bool` | ✅ BOOLEAN | ✅ checkbox | True/false |
| `date` | ✅ DATE | ✅ date picker | Date only |
| `time` | ✅ TIME | ✅ time picker | Time only |
| `datetime` | ✅ TIMESTAMP | ✅ datetime picker | Date and time |
| `uuid` | ✅ UUID | ✅ hidden/readonly | UUID v4 |
| `email` | ✅ VARCHAR + validation | ✅ email input | Email validation |
| `url` | ✅ VARCHAR + validation | ✅ url input | URL validation |
| `enum[a,b,c]` | ✅ VARCHAR + constraint | ✅ select | Enumerated values |
| `ref Entity` | ✅ Foreign key | ✅ select/lookup | Entity reference |

---

## Constraints & Modifiers

| Modifier | Backend | UI | Description |
|----------|---------|-----|-------------|
| `required` | ✅ NOT NULL | ✅ required attr | Must provide value |
| `optional` | ✅ NULL allowed | ✅ no required | May be empty |
| `pk` | ✅ Primary key | ✅ hidden | Primary key |
| `unique` | ✅ UNIQUE constraint | ✅ validation | Must be unique |
| `auto_add` | ✅ Default NOW | ✅ readonly | Set on creation |
| `auto_update` | ✅ Update NOW | ✅ readonly | Update on save |
| `=default` | ✅ Default value | ✅ prefilled | Default value |

---

## Surface Modes

| Mode | DNR Support | Generated UI |
|------|-------------|--------------|
| `list` | ✅ | Data table with sorting, filtering |
| `view` | ✅ | Read-only detail view |
| `create` | ✅ | Form for new entity |
| `edit` | ✅ | Form for updating entity |

---

## Workspace Archetypes

Workspaces automatically select layout archetypes based on signal analysis:

| Archetype | Use Case | Signal Pattern |
|-----------|----------|----------------|
| `DUAL_PANE_FLOW` | List + detail | Low signal count, entity browsing |
| `FOCUS_METRIC` | KPI dashboard | Single dominant aggregate |
| `SCANNER_TABLE` | Data browsing | High entity count, filtering |
| `MONITOR_WALL` | Multi-signal dashboard | Multiple attention signals |
| `COMMAND_CENTER` | Complex operations | High signal count, multiple entities |

**Visualize layouts**:
```bash
dazzle layout-plan
```

---

## UX Semantic Layer

### Personas

Define role-based access and workspace visibility:

```dsl
persona agent "Support Agent":
  description: "Handles customer tickets"
  default_workspace: ticket_queue

persona manager "Team Manager":
  description: "Oversees agent performance"
  default_workspace: team_dashboard
```

### Attention Signals

Workspaces analyze regions and assign attention signals:

- **KPI signals**: Aggregate data (counts, sums, averages)
- **Curated lists**: Limited result sets (top N items)
- **Browsable tables**: Unlimited entity browsing

### UX Blocks

Semantic UI components that map to DaisyUI styling:

| UX Block | DaisyUI Component |
|----------|-------------------|
| `stat` | stat card |
| `table` | table |
| `form` | form with inputs |
| `card` | card |
| `modal` | modal dialog |
| `toast` | toast notification |

---

## Authentication

DNR includes built-in session-based authentication:

| Feature | Status | Description |
|---------|--------|-------------|
| Session auth | ✅ | Cookie-based sessions |
| Login/logout | ✅ | Built-in auth endpoints |
| Persona binding | ✅ | Users assigned to personas |
| Workspace access | ✅ | Persona controls workspace visibility |
| RBAC | ⚠️ Basic | Entity-level permissions planned |

**Auth endpoints**:
- `POST /auth/login` - Login with credentials
- `POST /auth/logout` - End session
- `GET /auth/me` - Current user info

---

## E2E Testing

DNR applications include E2E testing infrastructure:

```bash
# Generate test specification
dazzle test generate -o testspec.json

# Run E2E tests
dazzle test run --verbose

# List available test flows
dazzle test list
```

**Test coverage**:
- Route navigation
- CRUD operations
- Form validation
- Workspace rendering
- Authentication flows

**Semantic DOM**: Tests use `data-dazzle-*` attributes for reliable selectors.

---

## Ejection (Production Deployment)

When ready for production, the ejection toolchain generates standalone code:

```bash
dazzle eject run
```

| Adapter | Type | Description |
|---------|------|-------------|
| `fastapi` | Backend | FastAPI with SQLAlchemy models, Pydantic schemas |
| `react` | Frontend | React with TypeScript, TanStack Query, Zod |
| `schemathesis` | Testing | Contract tests from OpenAPI |
| `pytest` | Testing | Unit tests for backend |
| `github_actions` | CI | CI/CD pipeline |

See [Ejection Toolchain](design/EJECTION_TOOLCHAIN_v0.7.2.md) for details.

---

## Tooling

### CLI Commands

| Command | Description |
|---------|-------------|
| `dazzle dnr serve` | Run the application |
| `dazzle dnr info` | Show project info |
| `dazzle validate` | Parse and validate DSL |
| `dazzle lint` | Extended validation checks |
| `dazzle layout-plan` | Visualize workspace layouts |
| `dazzle test generate` | Generate E2E test spec |
| `dazzle test run` | Run E2E tests |

### IDE Integration

| Feature | Status |
|---------|--------|
| VS Code extension | ✅ |
| LSP server | ✅ |
| Real-time diagnostics | ✅ |
| Hover documentation | ✅ |
| Go-to-definition | ✅ |
| Auto-completion | ✅ |

### MCP Server

DAZZLE includes an MCP server for Claude Code integration:

```bash
# Auto-registered with Homebrew install
# Or register manually:
dazzle mcp-setup
dazzle mcp-check
```

**Available tools**:
- `validate_dsl` - Validate DSL files
- `inspect_entity` - Inspect entity definitions
- `analyze_patterns` - Detect CRUD patterns
- `lookup_concept` - DSL concept documentation

---

## Known Limitations

### Current (v0.2.x)

| Limitation | Workaround | Planned |
|------------|------------|---------|
| Integration actions use stubs | Manual API code | v0.3 |
| No file/image field types | Manual implementation | v0.3 |
| No many-to-many syntax | Junction entities | v0.3 |
| No WebSocket support | Manual implementation | v1.0 |
| No GraphQL | Use REST API | No plans |

### Design Limitations

| Feature | Status | Notes |
|---------|--------|-------|
| NoSQL databases | Not planned | SQL only (SQLite, PostgreSQL) |
| Microservices | Not planned | Monolith focus |
| Multi-tenancy | Not planned | Single-tenant apps |

---

## Version History

| Version | Key Changes |
|---------|-------------|
| **v0.2.x** | DNR runtime, UX Semantic Layer, personas, workspaces |
| v0.1.x | Code generation stacks (now deprecated) |

---

**Questions?** See the [DSL Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md) or open an issue.
**Examples**: Check `examples/` directory for working projects.
