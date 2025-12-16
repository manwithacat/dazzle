# Workspaces

Workspaces are data-centric dashboard views with regions, filtering, and aggregates.

## Basic Syntax

```dsl
workspace workspace_name "Display Title":
  purpose: "Description of the workspace"
  stage: "archetype_name"

  region_name:
    source: EntityName
    filter: condition
    sort: field direction
    limit: number
    display: list|grid|timeline|map
    action: surface_name
    empty: "Empty state message"
    group_by: field_name
    aggregate:
      metric_name: expression
```

## Workspace Properties

| Property | Description |
|----------|-------------|
| `purpose` | Human-readable description |
| `stage` | UI archetype hint (e.g., "dashboard", "kanban") |

## Region Properties

| Property | Description | Required |
|----------|-------------|----------|
| `source` | Entity to display | Yes |
| `filter` | Condition expression | No |
| `sort` | Sort expression(s) | No |
| `limit` | Max records to show | No |
| `display` | Display mode | No (default: list) |
| `action` | Surface to navigate to on click | No |
| `empty` | Message when no records | No |
| `group_by` | Field to group records by | No |
| `aggregate` | Computed metrics | No |

## Display Modes

| Mode | Description |
|------|-------------|
| `list` | Table/list view |
| `grid` | Card grid layout |
| `timeline` | Chronological timeline |
| `map` | Geographic map (requires location data) |

## Filter Expressions

Filter uses simple condition expressions:

```dsl
# Equality
filter: status == "active"

# Comparison
filter: due_date < today

# Field references
filter: assignee == current_user

# Combined conditions
filter: status == "pending" and priority == "high"
```

## Sort Expressions

```dsl
# Single field
sort: created_at desc

# Multiple fields (comma-separated)
sort: priority desc, due_date asc
```

## Aggregates

Define computed metrics for regions:

```dsl
aggregate:
  total_value: sum(amount)
  average_score: avg(rating)
  item_count: count(*)
  max_priority: max(priority)
```

## Complete Example

```dsl
workspace sales_dashboard "Sales Dashboard":
  purpose: "Monitor sales performance and pipeline"
  stage: "dashboard"

  # Summary metrics region
  summary:
    source: Order
    filter: order_date >= first_day_of_month
    display: grid
    aggregate:
      total_revenue: sum(subtotal)
      order_count: count(*)
      avg_order_value: avg(subtotal)

  # Recent orders
  recent_orders:
    source: Order
    sort: order_date desc
    limit: 10
    display: list
    action: order_detail
    empty: "No orders yet this period"

  # Orders by status
  by_status:
    source: Order
    filter: order_date >= first_day_of_month
    group_by: status
    display: grid
    aggregate:
      count: count(*)
      value: sum(subtotal)

  # Overdue invoices alert
  overdue:
    source: Invoice
    filter: status == "overdue"
    sort: due_date asc
    limit: 5
    display: list
    action: invoice_detail
    empty: "No overdue invoices"

workspace task_board "Task Board":
  purpose: "Kanban-style task management"
  stage: "kanban"

  # Backlog column
  backlog:
    source: Task
    filter: status == "backlog"
    sort: priority desc, created_at asc
    display: list
    action: task_detail
    empty: "Backlog is empty"
    aggregate:
      count: count(*)

  # In Progress column
  in_progress:
    source: Task
    filter: status == "in_progress"
    sort: priority desc
    display: list
    action: task_detail
    empty: "Nothing in progress"
    aggregate:
      count: count(*)

  # Review column
  review:
    source: Task
    filter: status == "review"
    sort: updated_at desc
    display: list
    action: task_detail
    aggregate:
      count: count(*)

  # Done column
  done:
    source: Task
    filter: status == "done" and completed_at >= week_start
    sort: completed_at desc
    limit: 20
    display: list
    action: task_detail
    aggregate:
      count: count(*)

workspace team_calendar "Team Calendar":
  purpose: "View team schedules and deadlines"
  stage: "calendar"

  # Upcoming deadlines
  deadlines:
    source: Task
    filter: due_date != null and status != "done"
    sort: due_date asc
    display: timeline
    action: task_detail

  # Team meetings
  meetings:
    source: Meeting
    filter: start_time >= today
    sort: start_time asc
    display: timeline
    action: meeting_detail
    empty: "No upcoming meetings"

  # Out of office
  time_off:
    source: TimeOff
    filter: start_date <= next_week and end_date >= today
    sort: start_date asc
    display: timeline
```

## UX Semantic Layer

Workspaces support the UX block for additional customization:

```dsl
workspace inventory_overview "Inventory":
  purpose: "Monitor stock levels"

  low_stock:
    source: Product
    filter: quantity < reorder_point
    sort: quantity asc
    display: list
    action: product_detail
    empty: "All stock levels healthy"

  ux:
    attention critical:
      when: quantity == 0
      message: "Out of stock!"
      action: product_reorder

    attention warning:
      when: quantity < reorder_point
      message: "Stock running low"

    for warehouse_manager:
      scope: all
      focus: low_stock, recent_orders
      action_primary: product_detail

    for sales_rep:
      scope: all
      focus: low_stock
      read_only: true
```
