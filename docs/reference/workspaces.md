# Workspaces

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Workspaces compose multiple data views into cohesive dashboards or information hubs. They aggregate related surfaces, metrics, and data for specific user needs. This page covers workspace definitions, regions, aggregates, display modes, and layout stages.

---

## Workspace

A composition of multiple data views into a cohesive dashboard or information hub.
Workspaces aggregate related surfaces and data for specific user needs.

Region types:
  - Data region: has source + optional filter/sort/limit → renders entity rows
  - Aggregate-only region: has only aggregate: block → renders KPI metric cards
  - Detail region: display: detail with source → renders a single record view

Key features:
  - filter: applies a ConditionExpr so regions only show matching rows (e.g. status = open)
  - sort: orders results (e.g. due_date desc for most urgent first)
  - limit: caps result count (useful for "top 5" style regions)
  - action: links rows to a surface for click-through navigation (e.g. action: task_edit)
  - aggregate: computes metrics like count(Entity where condition) displayed as KPI cards
  - stage: controls CSS grid layout (focus_metric, dual_pane_flow, scanner_table, monitor_wall, command_center)

### Syntax

```dsl
workspace <workspace_name> "<Display Name>":
  purpose: "<semantic intent>"
  [stage: "<stage_name>"]

  <region_name>:
    source: <Entity|surface_name>
    [filter: <condition>]
    [sort: <field> [asc|desc], ...]
    [limit: <number>]
    [display: <list|grid|detail|summary|metrics>]
    [action: <surface_name>]
    [empty: "<message>"]
    [group_by: <field>]
    [aggregate:]
      <metric_name>: <expression>

  [ux:]
    [for <persona>: ...]

# Aggregate expressions:
#   count(Entity)                        → total entity count
#   count(Entity where status = open)    → filtered count
#   sum(Entity.amount)                   → field sum (planned)
#   avg(Entity.duration_days)            → field average (planned)
```

### Example

```dsl
workspace customer_dashboard "Customer Dashboard":
  purpose: "Customer health overview for account managers"
  stage: "command_center"

  active_contracts:
    source: Contract
    filter: status = active
    sort: renewal_date asc
    limit: 10
    action: contract_detail
    display: list
    empty: "No active contracts"

  overdue_invoices:
    source: Invoice
    filter: status = overdue
    sort: due_date asc
    limit: 5
    action: invoice_edit
    display: list
    empty: "All invoices paid!"

  kpi_metrics:
    aggregate:
      active_customers: count(Customer where status = active)
      open_invoices: count(Invoice where status != paid and status != cancelled)
      total_revenue: sum(Invoice.amount)
    display: metrics

  recent_activity:
    source: AuditLog
    sort: created_at desc
    limit: 20
    display: list
```

**Related:** [Persona](ux.md#persona), [Regions](workspaces.md#regions), [Aggregates](workspaces.md#aggregates), [Display Modes](workspaces.md#display-modes), [Stage](experiences.md#stage)

---

## Regions

Named sections within a workspace that pull data from entities or surfaces.
Each region defines a data view with optional filtering, sorting, display mode,
and aggregation. Three types of regions:
- Data region: has source + optional filter/sort/limit (renders entity rows)
- Aggregate-only region: has only aggregate: block (renders KPI metric cards)
- Multi-source region: has sources: [Entity1, Entity2] (renders tabbed list)

Regions support date-range filtering (v0.34.0) with date_field + date_range flag.

### Syntax

```dsl
<region_name>:
  source: <EntityName>                       # Single source
  source: [<Entity1>, <Entity2>]             # Multi-source (tabbed list)
  [filter: <condition_expr>]                 # Row filter
  [filter_map:]                              # Per-source filters (multi-source)
    [<EntityName>: <condition>]
  [sort: <field> [asc|desc], ...]            # Sort order
  [limit: <1-1000>]                          # Max records
  [display: <list|grid|timeline|map|detail|summary|metrics|kanban|bar_chart|funnel_chart|queue|tabbed_list>]
  [action: <surface_name>]                   # Click-through surface
  [empty: "<message>"]                       # Empty state message
  [group_by: <field>]                        # Group data by field
  [date_field: <field>]                      # Date-range filter field
  [date_range]                               # Enable date picker
  [aggregate:]                               # KPI metrics
    [<metric_name>: <expression>]
```

### Example

```dsl
workspace ops_dashboard "Operations Dashboard":
  purpose: "Monitor daily operations"

  # Data region with filter and sort
  open_tickets:
    source: Ticket
    filter: status = open
    sort: priority desc, created_at asc
    limit: 20
    display: list
    action: ticket_detail
    empty: "No open tickets"

  # Aggregate-only region (no source needed)
  kpi_metrics:
    aggregate:
      total_tickets: count(Ticket)
      open_count: count(Ticket where status = open)
    display: metrics

  # Detail region (single record view)
  current_user_profile:
    source: UserProfile
    display: detail

  # Multi-source tabbed region
  activity:
    source: [Ticket, Order, Invoice]
    sort: created_at desc
    limit: 10
    display: tabbed_list

  # Date-range filtered region
  sales:
    source: Order
    date_field: created_at
    date_range
    sort: created_at desc
    display: list
```

**Related:** [Workspace](workspaces.md#workspace), [Display Modes](workspaces.md#display-modes), [Aggregates](workspaces.md#aggregates)

---

## Aggregate

Computed metrics on workspace regions. Aggregates calculate summary values from entity data using count(), sum(), avg(), min(), max() functions with optional WHERE conditions.

### Syntax

```dsl
aggregate:
  <metric_name>: count(<Entity>)
  <metric_name>: count(<Entity> where <condition>)
  <metric_name>: sum(<field>)
  <metric_name>: avg(<field>)
```

### Example

```dsl
workspace dashboard "Dashboard":
  purpose: "Team overview"

  metrics:
    source: Task
    aggregate:
      total_tasks: count(Task)
      open_tasks: count(Task where status = open)
      critical: count(Task where priority = critical and status != closed)
```

**Related:** [Workspace](workspaces.md#workspace)

---

## Aggregates

Computed metrics and aggregate functions for workspace regions.

### Syntax

```dsl
aggregate:
  total: count(Task)
  completed: count(Task where status = done)
  completion_rate: count(Task where status = done) * 100 / count(Task)
  avg_duration: avg(Task.duration_days)
```

**Related:** [Regions](workspaces.md#regions), [Workspace](workspaces.md#workspace)

---

## Display Modes

Visualization modes for workspace regions.

### Syntax

```dsl
display: <list|grid|timeline|map>
```

**Related:** [Regions](workspaces.md#regions), [Workspace](workspaces.md#workspace)

---

## Nav Group

A collapsible navigation group within a workspace. Groups workspace navigation items under a labeled, optionally collapsible header with an optional Lucide icon. Each item links to an entity or workspace by name and can have its own icon.

### Syntax

```dsl
workspace <name> "<Title>":
  ...
  nav_group "<Label>" [icon=<lucide-icon-name>] [collapsed]:
    <EntityOrWorkspaceName> [icon=<lucide-icon-name>]
    <EntityOrWorkspaceName> [icon=<lucide-icon-name>]
    ...

# icon: Lucide icon name (e.g., settings, file-text, check-circle)
# collapsed: if present, group starts collapsed (default: expanded)
```

### Example

```dsl
workspace dashboard "Dashboard":
  nav_group "Management" icon=settings:
    Task icon=check-circle
    User icon=users
    Project icon=folder

  nav_group "Reports" icon=bar-chart-2 collapsed:
    Invoice icon=file-text
    Payment icon=credit-card

  tasks:
    source: Task
    display: list
```

### Best Practices

- Use nav_group to organize workspaces with many entities
- Use collapsed for secondary navigation that is rarely needed
- Use Lucide icon names for visual clarity (hyphenated, e.g., file-text)

**Related:** [Workspace](workspaces.md#workspace), [Regions](workspaces.md#regions)

---
