# DAZZLE Archetype Showcase
# Demonstrates all five DNR layout archetypes

module archetype_showcase.core

app archetype_showcase "Archetype Showcase"

# =============================================================================
# Entities for demonstrating all archetypes
# =============================================================================

entity Metric "System Metric":
  id: uuid pk
  name: str(100) required
  value: decimal(10,2) required
  unit: str(20)
  status: enum[normal,warning,critical]=normal
  updated_at: datetime auto_update

entity Item "Inventory Item":
  id: uuid pk
  sku: str(50) required unique
  name: str(200) required
  category: str(100)
  quantity: int
  price: decimal(10,2)
  status: enum[available,low_stock,out_of_stock]=available

entity Task "Work Task":
  id: uuid pk
  title: str(200) required
  description: text
  priority: enum[low,medium,high,urgent]=medium
  status: enum[pending,in_progress,completed,blocked]=pending
  assigned_to: str(100)
  due_date: date
  created_at: datetime auto_add

entity Alert "System Alert":
  id: uuid pk
  title: str(200) required
  severity: enum[low,medium,high]=low
  source: str(100)
  message: text
  is_acknowledged: bool = false
  created_at: datetime auto_add

entity Service "Monitored Service":
  id: uuid pk
  name: str(100) required
  endpoint: str(255) required
  status: enum[healthy,degraded,down,unknown]=unknown
  uptime_percent: decimal(5,2)
  response_time_ms: int
  last_check: datetime

# =============================================================================
# FOCUS_METRIC: Single dominant KPI display
# Use: When one metric is the primary focus
# =============================================================================

workspace focus_metric_demo "Focus Metric Demo":
  purpose: "Demonstrates FOCUS_METRIC archetype - single dominant KPI"
  engine_hint: "focus_metric"

  hero:
    source: Metric
    limit: 1
    display: detail
    aggregate:
      main_value: value

  supporting:
    source: Metric
    limit: 4
    display: list

# =============================================================================
# SCANNER_TABLE: Dense table with filters
# Use: Data-heavy views where scanning is primary
# =============================================================================

workspace scanner_table_demo "Scanner Table Demo":
  purpose: "Demonstrates SCANNER_TABLE archetype - dense table view"
  engine_hint: "scanner_table"

  inventory:
    source: Item
    display: list

  filters:
    source: Item
    aggregate:
      count: count(Item)

# =============================================================================
# DUAL_PANE_FLOW: List + Detail master-detail
# Use: Browse lists and view details side-by-side
# =============================================================================

workspace dual_pane_demo "Dual Pane Demo":
  purpose: "Demonstrates DUAL_PANE_FLOW archetype - list + detail"
  engine_hint: "dual_pane_flow"

  task_list:
    source: Task
    display: list
    limit: 20

  task_detail:
    source: Task
    display: detail
    limit: 1

# =============================================================================
# MONITOR_WALL: Grid of moderate-importance signals
# Use: Dashboards monitoring multiple metrics
# =============================================================================

workspace monitor_wall_demo "Monitor Wall Demo":
  purpose: "Demonstrates MONITOR_WALL archetype - grid of metrics"
  engine_hint: "monitor_wall"

  services:
    source: Service
    display: grid
    aggregate:
      total: count(Service)

  uptime:
    source: Service
    display: grid
    aggregate:
      avg_uptime: avg(uptime_percent)

  performance:
    source: Service
    display: list
    limit: 5

  alerts:
    source: Alert
    display: list
    limit: 5

# =============================================================================
# COMMAND_CENTER: Dense, expert-focused dashboard
# Use: Operations centers, expert users
# =============================================================================

workspace command_center_demo "Command Center Demo":
  purpose: "Demonstrates COMMAND_CENTER archetype - expert dashboard"
  engine_hint: "command_center"

  critical_alerts:
    source: Alert
    display: list
    aggregate:
      critical_count: count(Alert)

  service_health:
    source: Service
    display: grid
    aggregate:
      healthy: count(Service)

  active_tasks:
    source: Task
    display: list
    limit: 10

  pending_tasks:
    source: Task
    display: list
    limit: 10

  metrics_overview:
    source: Metric
    display: grid
    limit: 8

  recent_alerts:
    source: Alert
    display: list
    limit: 10

# =============================================================================
# Surfaces for CRUD operations
# =============================================================================

surface metric_list "Metrics":
  uses entity Metric
  mode: list

  section main:
    field name
    field value
    field unit
    field status

surface item_list "Inventory":
  uses entity Item
  mode: list

  section main:
    field sku
    field name
    field category
    field quantity
    field status

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field priority
    field status
    field assigned_to

surface task_detail "Task Detail":
  uses entity Task
  mode: view

  section main:
    field title
    field description
    field priority
    field status
    field assigned_to
    field due_date

surface alert_list "Alerts":
  uses entity Alert
  mode: list

  section main:
    field title
    field severity
    field source
    field is_acknowledged

surface service_list "Services":
  uses entity Service
  mode: list

  section main:
    field name
    field status
    field uptime_percent
    field response_time_ms
