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

| Example | Complexity | Archetype | Features |
|---------|------------|-----------|----------|
| [Simple Task](#simple-task-manager) | Beginner | - | Basic CRUD |
| [Contact Manager](#contact-manager) | Beginner | DUAL_PANE_FLOW | Multi-entity relations |
| [Support Tickets](#support-tickets) | Intermediate | - | UX Semantic Layer, personas |
| [Fieldtest Hub](#fieldtest-hub) | Intermediate | - | Workspaces, personas |
| [Uptime Monitor](#uptime-monitor) | Intermediate | FOCUS_METRIC | KPI dashboard |
| [Inventory Scanner](#inventory-scanner) | Intermediate | SCANNER_TABLE | Data browsing |
| [Email Client](#email-client) | Intermediate | MONITOR_WALL | Multi-signal dashboard |
| [Ops Dashboard](#ops-dashboard) | Advanced | COMMAND_CENTER | Complex monitoring |
| [Urban Canopy](#urban-canopy) | Advanced | - | Local vocabulary |
| [Archetype Showcase](#archetype-showcase) | Reference | Multiple | All layout archetypes |

---

### Simple Task Manager

**[Full Documentation](examples/simple_task/)**

The "Hello World" of DAZZLE - a minimal CRUD application demonstrating core DSL concepts.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/simple_task/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/simple_task/dsl/app.dsl) |
| **Entities** | Task |
| **Surfaces** | list, view, create, edit |
| **CI Status** | P0 (blocks PRs) |

```bash
cd examples/simple_task && dazzle dnr serve
```

---

### Contact Manager

**[Full Documentation](examples/contact_manager/)**

Multi-entity CRUD with the DUAL_PANE_FLOW archetype - list + detail pattern.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/contact_manager/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/contact_manager/dsl/app.dsl) |
| **Entities** | Contact |
| **Archetype** | DUAL_PANE_FLOW |
| **CI Status** | P0 (blocks PRs) |

```bash
cd examples/contact_manager && dazzle dnr serve
```

---

### Uptime Monitor

**[Full Documentation](examples/uptime_monitor/)**

Single dominant KPI dashboard pattern - executive dashboards, SLA monitoring.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/uptime_monitor/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/uptime_monitor/dsl/app.dsl) |
| **Entities** | Service |
| **Archetype** | FOCUS_METRIC |
| **CI Status** | P1 |

```bash
cd examples/uptime_monitor && dazzle dnr serve
```

---

### Inventory Scanner

**[Full Documentation](examples/inventory_scanner/)**

Data-heavy browsing and filtering pattern - admin panels, catalog browsing.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/inventory_scanner/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/inventory_scanner/dsl/app.dsl) |
| **Entities** | Product |
| **Archetype** | SCANNER_TABLE |
| **CI Status** | P1 |

```bash
cd examples/inventory_scanner && dazzle dnr serve
```

---

### Email Client

**[Full Documentation](examples/email_client/)**

Multi-signal dashboard pattern - operations dashboards, notifications.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/email_client/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/email_client/dsl/app.dsl) |
| **Entities** | Message |
| **Archetype** | MONITOR_WALL |
| **CI Status** | P2 |

```bash
cd examples/email_client && dazzle dnr serve
```

---

### Ops Dashboard

**[Full Documentation](examples/ops_dashboard/)**

Complex monitoring with high signal count - DevOps, system monitoring.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/ops_dashboard/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/ops_dashboard/dsl/app.dsl) |
| **Entities** | System, Alert |
| **Archetype** | COMMAND_CENTER |
| **CI Status** | P2 |

```bash
cd examples/ops_dashboard && dazzle dnr serve
```

---

### Support Tickets

**Path**: `examples/support_tickets/`

Full UX Semantic Layer showcase - demonstrates personas, workspaces, and attention signals.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/support_tickets/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/support_tickets/dsl/app.dsl) |
| **v0.2 Features** | Personas, workspaces, UX blocks |
| **CI Status** | P1 |

```bash
cd examples/support_tickets && dazzle dnr serve
```

---

### Fieldtest Hub

**Path**: `examples/fieldtest_hub/`

Demonstrates workspace organization with multiple personas.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/fieldtest_hub/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/fieldtest_hub/dsl/app.dsl) |
| **v0.2 Features** | Workspaces, personas |
| **CI Status** | P2 |

```bash
cd examples/fieldtest_hub && dazzle dnr serve
```

---

### Urban Canopy

**Path**: `examples/urban_canopy/`

Advanced example demonstrating local vocabulary for domain-specific terminology.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/urban_canopy/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/urban_canopy/dsl/app.dsl) |
| **v0.2 Features** | Local vocabulary, domain patterns |
| **CI Status** | P2 |

```bash
cd examples/urban_canopy && dazzle dnr serve
```

---

### Archetype Showcase

**Path**: `examples/archetype_showcase/`

Reference implementation demonstrating all available layout archetypes.

| Attribute | Value |
|-----------|-------|
| **Path** | `examples/archetype_showcase/` |
| **DSL Source** | [`dsl/app.dsl`](../examples/archetype_showcase/dsl/app.dsl) |
| **Purpose** | Layout archetype reference |
| **CI Status** | P2 |

```bash
cd examples/archetype_showcase && dazzle dnr serve
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
