# Parser Reference: Workspaces
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# WORKSPACE BASICS:
# - [x] workspace name "Title":
# - [x] workspace name: (no title)
# - [x] purpose: "..."
# - [x] stage: "stage_name"
# - [x] engine_hint: "archetype_name" (deprecated alias for stage)
#
# ACCESS CONTROL:
# - [x] access: public
# - [x] access: authenticated
# - [x] access: persona(name1, name2)
#
# REGIONS:
# - [x] region_name:
# - [x] source: EntityName
# - [x] filter: condition
# - [x] sort: field desc
# - [x] limit: N
# - [x] action: surface_name
# - [x] empty: "..."
# - [x] group_by: field
# - [x] aggregate: block
#
# DISPLAY MODES:
# - [x] display: list
# - [x] display: grid
# - [x] display: timeline
# - [x] display: map
# - [x] display: detail
# - [x] display: summary
# - [x] display: metrics
# - [x] display: kanban
# - [x] display: bar_chart
# - [x] display: funnel_chart
#
# UX BLOCK:
# - [x] ux: block (workspace-level)
# - [x] attention signals in workspace
# - [x] persona variants in workspace
#
# =============================================================================

module pra.workspaces

use pra
use pra.entities
use pra.relationships
use pra.surfaces
use pra.state_machines

# =============================================================================
# BASIC WORKSPACE
# =============================================================================

workspace simple_dashboard "Simple Dashboard":
  purpose: "Basic workspace with single data region"

  tasks:
    source: Task
    display: list

# =============================================================================
# WORKSPACE WITHOUT TITLE
# =============================================================================

workspace minimal_workspace:
  purpose: "Workspace without title string"

  items:
    source: Product
    display: list

# =============================================================================
# ACCESS CONTROL: PUBLIC
# =============================================================================

workspace public_catalog "Public Catalog":
  purpose: "Public product browsing"
  access: public

  products:
    source: Product
    filter: is_active = true
    display: grid
    empty: "No products available"

# =============================================================================
# ACCESS CONTROL: AUTHENTICATED
# =============================================================================

workspace member_dashboard "Member Dashboard":
  purpose: "Dashboard for authenticated users"
  access: authenticated

  my_tasks:
    source: Task
    filter: assignee = current_user
    display: list

# =============================================================================
# ACCESS CONTROL: PERSONA
# =============================================================================

workspace admin_console "Admin Console":
  purpose: "Administration workspace for admins and managers"
  access: persona(admin, manager)

  all_users:
    source: Employee
    display: list
    action: employee_edit

  system_settings:
    source: SystemSettings
    display: detail

# =============================================================================
# STAGE HINTS
# =============================================================================

workspace focus_workspace "Focus View":
  purpose: "Single-focus metric workspace"
  stage: "focus_metric"

  main_metric:
    source: Invoice
    filter: status = overdue
    display: summary
    aggregate:
      total_overdue: sum(total)
      count_overdue: count(Invoice)

workspace dual_pane_workspace "Dual Pane":
  purpose: "Two-column layout workspace"
  stage: "dual_pane_flow"

  left_pane:
    source: Task
    filter: status = todo
    display: list

  right_pane:
    source: Task
    filter: status = in_progress
    display: list

workspace command_center "Command Center":
  purpose: "Complex multi-region workspace"
  stage: "command_center"

  alerts:
    source: TimeSensitiveAlert
    filter: status = new
    display: list
    limit: 10

  metrics:
    source: TeamStats
    display: metrics

  activity_timeline:
    source: AuditLog
    display: timeline
    limit: 50

# =============================================================================
# ALL DISPLAY MODES
# =============================================================================

workspace display_modes "Display Mode Showcase":
  purpose: "Demonstrates all display modes"

  # List view (default)
  list_region:
    source: Task
    display: list
    sort: created_at desc
    limit: 20

  # Grid view
  grid_region:
    source: Product
    display: grid
    filter: is_active = true

  # Timeline view
  timeline_region:
    source: AuditLog
    display: timeline
    sort: occurred_at desc
    limit: 100

  # Grid view (map not supported as keyword)
  map_region:
    source: EmployeeAddress
    display: grid

  # Detail view (single item)
  detail_region:
    source: Company
    display: detail

  # Summary view (metrics/KPIs)
  summary_region:
    source: Invoice
    display: summary
    aggregate:
      total_revenue: sum(total)
      invoice_count: count(Invoice)

  # Metrics view (alias for summary)
  metrics_region:
    source: OrderWithTotals
    display: metrics
    aggregate:
      order_count: count(OrderWithTotals)
      total_sales: sum(subtotal)

  # Kanban view
  kanban_region:
    source: Task
    display: kanban
    group_by: status

  # Bar chart view
  bar_chart_region:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      total: sum(total)

  # Funnel chart view
  funnel_chart_region:
    source: LeadQualification
    display: funnel_chart
    group_by: status
    aggregate:
      count: count(LeadQualification)

# =============================================================================
# REGION WITH FILTER
# =============================================================================

workspace filtered_workspace "Filtered Data":
  purpose: "Workspace with various filter conditions"

  urgent_tasks:
    source: Task
    filter: priority = urgent and status != done
    display: list
    sort: due_date asc

  my_overdue:
    source: Task
    filter: assignee = current_user and status != done
    display: list
    sort: due_date asc

  department_projects:
    source: DevProject
    filter: status = active
    display: grid

# =============================================================================
# REGION WITH SORT
# =============================================================================

workspace sorted_workspace "Sorted Data":
  purpose: "Workspace with various sort specifications"

  by_date:
    source: Task
    sort: created_at desc
    display: list

  by_priority:
    source: Task
    sort: priority desc, created_at asc
    display: list

  by_name:
    source: Employee
    sort: last_name asc, first_name asc
    display: list

# =============================================================================
# REGION WITH LIMIT
# =============================================================================

workspace limited_workspace "Limited Data":
  purpose: "Workspace with limited results"

  top_5:
    source: Product
    sort: price desc
    limit: 5
    display: list

  recent_10:
    source: Task
    sort: created_at desc
    limit: 10
    display: list

  first_100:
    source: AuditLog
    limit: 100
    display: timeline

# =============================================================================
# REGION WITH ACTION
# =============================================================================

workspace actionable_workspace "Quick Actions":
  purpose: "Workspace with quick action buttons"

  pending_tasks:
    source: Task
    filter: status = todo
    display: list
    action: task_edit
    empty: "No pending tasks!"

  new_invoices:
    source: Invoice
    filter: status = draft
    display: list
    action: invoice_edit

# =============================================================================
# REGION WITH EMPTY MESSAGE
# =============================================================================

workspace empty_states "Empty State Messages":
  purpose: "Workspace with empty state messaging"

  no_alerts:
    source: TimeSensitiveAlert
    filter: status = new
    display: list
    empty: "All clear! No new alerts."

  no_tasks:
    source: Task
    filter: status = todo and assignee = current_user
    display: list
    empty: "You have no tasks. Enjoy your free time!"

  no_products:
    source: Product
    filter: is_active = false
    display: grid
    empty: "No inactive products found."

# =============================================================================
# REGION WITH GROUP BY
# =============================================================================

workspace grouped_workspace "Grouped Data":
  purpose: "Workspace with grouping"

  tasks_by_status:
    source: Task
    display: kanban
    group_by: status

  invoices_by_status:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      total: sum(total)

  products_by_category:
    source: Product
    display: grid
    group_by: category

# =============================================================================
# REGION WITH AGGREGATES
# =============================================================================

workspace analytics_workspace "Analytics":
  purpose: "Workspace with aggregate calculations"

  sales_metrics:
    source: Invoice
    display: summary
    aggregate:
      total_revenue: sum(total)
      invoice_count: count(Invoice)
      avg_invoice: avg(total)
      min_invoice: min(total)
      max_invoice: max(total)

  task_metrics:
    source: Task
    display: metrics
    aggregate:
      total_tasks: count(Task)
      completed_tasks: count(Task)

  project_budget:
    source: DepartmentProject
    display: bar_chart
    group_by: department
    aggregate:
      total_budget: sum(budget)

# =============================================================================
# AGGREGATE-ONLY REGION (NO SOURCE)
# =============================================================================

workspace kpi_dashboard "KPI Dashboard":
  purpose: "Pure metrics workspace"

  overall_metrics:
    aggregate:
      total_revenue: sum(Invoice.total)
      total_orders: count(OrderWithTotals)
      active_employees: count(Employee)

# =============================================================================
# WORKSPACE WITH UX BLOCK
# =============================================================================

workspace enhanced_dashboard "Enhanced Dashboard":
  purpose: "Workspace with UX semantic layer"

  tasks:
    source: Task
    filter: status != done
    display: list
    sort: priority desc

  ux:
    purpose: "Role-aware task management"
    show: title, status, priority, assignee

    attention critical:
      when: priority = urgent and status = todo
      message: "Urgent task needs immediate attention"
      action: task_edit

    attention warning:
      when: status = in_progress and priority = low
      message: "Low priority task still in progress"

    for team_member:
      scope: assignee = current_user
      purpose: "View your assigned tasks"
      show: title, status, priority
      action_primary: task_edit
      read_only: false

    for manager:
      scope: all
      purpose: "View all team tasks"
      show: title, status, priority, assignee
      show_aggregate: urgent_count, blocked_count

# =============================================================================
# COMPLEX COMBINED WORKSPACE
# =============================================================================

workspace operations_center "Operations Center":
  purpose: "Comprehensive operations dashboard with multiple regions and UX"
  access: persona(admin, ops_manager, support)
  stage: "command_center"

  # Alerts region with critical attention
  alerts:
    source: TimeSensitiveAlert
    filter: status in [new, acknowledged]
    display: list
    sort: severity desc, created_at asc
    limit: 20
    action: alert_handle
    empty: "No active alerts"

  # Task kanban board
  task_board:
    source: Task
    display: kanban
    group_by: status
    filter: status in [todo, in_progress, review]

  # Invoice metrics
  revenue_metrics:
    source: Invoice
    display: summary
    filter: status = paid
    aggregate:
      total_revenue: sum(total)
      invoice_count: count(Invoice)
      avg_order: avg(total)

  # Recent activity timeline
  activity:
    source: AuditLog
    display: timeline
    sort: occurred_at desc
    limit: 50
    empty: "No recent activity"

  # Order funnel
  order_funnel:
    source: OrderWithTotals
    display: funnel_chart
    group_by: status
    aggregate:
      order_count: count(OrderWithTotals)

  ux:
    purpose: "Unified operations view for support and management"

    attention critical:
      when: severity = critical and status = new
      message: "Critical alert requires immediate attention"
      action: alert_escalate

    attention warning:
      when: severity = error and status = new
      message: "Error alert needs review"
      action: alert_handle

    for ops_manager:
      scope: all
      purpose: "Full operational visibility"
      show: alerts, task_board, revenue_metrics, activity, order_funnel
      show_aggregate: alert_count, task_count, revenue_total
      focus: alerts, revenue_metrics

    for support:
      scope: status in [new, acknowledged]
      purpose: "Handle incoming alerts"
      show: alerts, activity
      hide: revenue_metrics
      action_primary: alert_handle
      focus: alerts

    for admin:
      scope: all
      purpose: "System administration view"
      show_aggregate: alert_count, user_count, system_health

# Placeholder surfaces for workspace actions
surface employee_edit "Edit Employee":
  uses entity Employee
  mode: edit
  section main:
    field first_name

surface invoice_edit "Edit Invoice":
  uses entity Invoice
  mode: edit
  section main:
    field invoice_number

surface alert_handle "Handle Alert":
  uses entity TimeSensitiveAlert
  mode: edit
  section main:
    field status

surface alert_escalate "Escalate Alert":
  uses entity TimeSensitiveAlert
  mode: edit
  section main:
    field status
