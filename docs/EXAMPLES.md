# DAZZLE Example Projects

> **Live demos of DAZZLE DSL-to-application generation**

All examples run instantly with `dazzle dnr serve` - no code generation required.

## Quick Start

```bash
cd examples/simple_task
dazzle dnr serve
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

## Example Gallery

### Simple Task Manager

**Path**: `examples/simple_task/`
**Complexity**: Beginner
**CI Status**: Tested in every PR

A minimal CRUD application - the "Hello World" of DAZZLE.

| Feature | Details |
|---------|---------|
| Entities | Task |
| Surfaces | list, view, create, edit |
| Field Types | uuid, str, text, bool, datetime, enum |

```bash
cd examples/simple_task && dazzle dnr serve
```

---

### Contact Manager

**Path**: `examples/contact_manager/`
**Complexity**: Beginner
**CI Status**: Tested in every PR

Multi-entity CRUD with relationships between contacts and companies.

| Feature | Details |
|---------|---------|
| Entities | Contact, Company |
| Relationships | Contact → Company (ref) |
| Surfaces | list, create, edit for each entity |

```bash
cd examples/contact_manager && dazzle dnr serve
```

---

### Uptime Monitor

**Path**: `examples/uptime_monitor/`
**Complexity**: Intermediate
**Archetype**: FOCUS_METRIC

Single dominant KPI dashboard pattern - executive dashboards, SLA monitoring.

| Feature | Details |
|---------|---------|
| Entities | Service, Check |
| Workspace | Dashboard with aggregate KPIs |
| Layout | Hero metric + context list |

```bash
cd examples/uptime_monitor && dazzle dnr serve
```

---

### Inventory Scanner

**Path**: `examples/inventory_scanner/`
**Complexity**: Intermediate
**Archetype**: SCANNER_TABLE

Data-heavy browsing and filtering pattern - admin panels, catalog browsing.

| Feature | Details |
|---------|---------|
| Entities | Product, Category |
| Workspace | Table-focused browsing |
| Layout | Filterable data table |

```bash
cd examples/inventory_scanner && dazzle dnr serve
```

---

### Email Client

**Path**: `examples/email_client/`
**Complexity**: Intermediate
**Archetype**: MONITOR_WALL

Multi-signal dashboard pattern - operations dashboards, notifications.

| Feature | Details |
|---------|---------|
| Entities | Email, Folder, Label |
| Workspace | Multiple signal regions |
| Layout | Grid-based multi-panel |

```bash
cd examples/email_client && dazzle dnr serve
```

---

### Ops Dashboard

**Path**: `examples/ops_dashboard/`
**Complexity**: Advanced
**Archetype**: COMMAND_CENTER

Complex monitoring with high signal count - DevOps, system monitoring.

| Feature | Details |
|---------|---------|
| Entities | Server, Metric, Alert |
| Workspace | 8+ signal regions |
| Layout | Dense monitoring grid |

```bash
cd examples/ops_dashboard && dazzle dnr serve
```

---

## E2E Test Coverage

All examples are automatically tested in CI using Playwright-based E2E tests.

| Example | Routes | CRUD | Components | Priority |
|---------|--------|------|------------|----------|
| simple_task | 4 | Full | 4 | P0 (blocks PR) |
| contact_manager | 6 | Full | 6 | P0 (blocks PR) |
| uptime_monitor | 4 | Full | 4 | P1 |
| inventory_scanner | 4 | Full | 4 | P1 |
| email_client | 5 | Partial | 5 | P2 |
| ops_dashboard | 8 | Partial | 8 | P2 |

**Test Commands**:
```bash
# Run E2E tests for an example
cd examples/simple_task
dazzle test generate -o testspec.json
dazzle test run --verbose

# List available test flows
dazzle test list
```

## Layout Visualization

Use `dazzle layout-plan` to visualize workspace layouts:

```bash
cd examples/uptime_monitor
dazzle layout-plan
```

Output shows:
- Archetype selection (FOCUS_METRIC, MONITOR_WALL, etc.)
- Signal allocation to layout regions
- Attention budget analysis

## Creating Your Own Example

1. Initialize a new project:
   ```bash
   dazzle init my_app
   cd my_app
   ```

2. Edit `dsl/app.dsl` with your domain model

3. Validate and run:
   ```bash
   dazzle validate
   dazzle dnr serve
   ```

## Documentation

- [DSL Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md)
- [DNR Architecture](dnr/ARCHITECTURE.md)
- [CLI Reference](dnr/CLI.md)
