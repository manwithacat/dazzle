# DAZZLE v0.2 Examples
# Demonstrating UX Semantic Layer Features

# =============================================================================
# Example 1: Simple Task Manager with UX Enhancements
# =============================================================================

module examples.simple_task_v2

app SimpleTaskV2 "Simple Task Manager v2"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  done: bool = false
  priority: enum[Low, Medium, High] = Medium
  due_date: date
  created_at: datetime auto_add
  updated_at: datetime auto_update

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field done "Status"
    field priority "Priority"
    field due_date "Due Date"

  ux:
    purpose: "Track personal tasks and todos"

    # Information needs
    show: title, done, priority, due_date
    sort: done asc, priority desc, due_date asc
    filter: done, priority
    search: title, description
    empty: "No tasks yet. Add your first task to get started!"

    # Attention signals
    attention warning:
      when: due_date < today and done = false
      message: "Overdue"
      action: task_edit

    attention notice:
      when: priority = High and done = false
      message: "High priority"

surface task_create "New Task":
  uses entity Task
  mode: create

  section main "Task Details":
    field title required=true
    field description
    field priority
    field due_date

  ux:
    purpose: "Add a new task to your list"

# Simple workspace for task overview
workspace my_tasks "My Tasks":
  purpose: "Personal task management hub"

  active_tasks:
    source: Task
    filter: done = false
    sort: priority desc, due_date asc
    limit: 20
    action: task_edit
    empty: "All tasks complete!"

  task_metrics:
    aggregate:
      total: count(Task)
      completed: count(Task where done = true)
      overdue: count(Task where due_date < today and done = false)
      completion_rate: round(count(Task where done = true) * 100 / count(Task))

# =============================================================================
# Example 2: Support Ticket System with Personas
# =============================================================================

module examples.support_v2

app SupportSystemV2 "Support Ticket System v2"

entity Customer "Customer":
  id: uuid pk
  email: email required unique
  name: str(100) required
  company: str(100)
  tier: enum[Free, Basic, Pro, Enterprise] = Free
  created_at: datetime auto_add

entity Ticket "Support Ticket":
  id: uuid pk
  ticket_number: str(20) unique auto_add
  customer: ref Customer required
  subject: str(200) required
  description: text required
  status: enum[New, Open, Pending, Resolved, Closed] = New
  priority: enum[Low, Normal, High, Urgent] = Normal
  assigned_to: ref Agent
  category: enum[Bug, Feature, Question, Other] = Other
  created_at: datetime auto_add
  updated_at: datetime auto_update
  resolved_at: datetime

entity Agent "Support Agent":
  id: uuid pk
  email: email required unique
  name: str(100) required
  team: enum[Support, Engineering, Sales] = Support
  is_available: bool = true

entity Comment "Comment":
  id: uuid pk
  ticket: ref Ticket required
  author_agent: ref Agent
  author_customer: ref Customer
  content: text required
  is_internal: bool = false
  created_at: datetime auto_add

surface ticket_list "Tickets":
  uses entity Ticket
  mode: list

  section main:
    field ticket_number "Ticket #"
    field subject "Subject"
    field customer "Customer"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assigned"
    field created_at "Created"

  ux:
    purpose: "Manage and track customer support tickets"

    sort: priority desc, created_at asc
    filter: status, priority, assigned_to, category
    search: subject, description, ticket_number
    empty: "No tickets found. Check your filters or wait for new tickets."

    # Priority-based attention signals
    attention critical:
      when: priority = Urgent and status != Resolved
      message: "Urgent - respond immediately"
      action: ticket_respond

    attention warning:
      when: status = New and days_since(created_at) > 1
      message: "Unassigned for >24h"
      action: ticket_assign

    attention notice:
      when: status = Pending and days_since(updated_at) > 3
      message: "Follow up needed"
      action: ticket_view

    # Different views for different roles
    for agent:
      scope: assigned_to = current_user or status = New
      purpose: "Your ticket queue"
      show: ticket_number, subject, status, priority, created_at
      action_primary: ticket_respond

    for manager:
      scope: all
      purpose: "Team ticket oversight"
      show_aggregate: new_count, urgent_count, avg_resolution_time
      action_primary: ticket_assign

    for customer:
      scope: customer = current_user
      purpose: "Your support requests"
      hide: assigned_to, is_internal
      show: ticket_number, subject, status, created_at
      action_primary: ticket_view
      read_only: true

surface ticket_view "View Ticket":
  uses entity Ticket
  mode: view

  section header:
    field ticket_number
    field subject
    field status
    field priority

  section details:
    field description
    field category
    field customer
    field assigned_to

  section timeline:
    field created_at
    field updated_at
    field resolved_at

  ux:
    purpose: "View and manage ticket details"

    for customer:
      hide: assigned_to, internal_notes
      read_only: true

# Agent workspace
workspace agent_dashboard "Agent Dashboard":
  purpose: "Support agent daily workflow"

  my_urgent:
    source: Ticket
    filter: assigned_to = current_user and priority = Urgent and status != Resolved
    sort: created_at asc
    limit: 5
    display: list
    action: ticket_respond
    empty: "No urgent tickets!"

  my_queue:
    source: Ticket
    filter: assigned_to = current_user and status in [Open, Pending]
    sort: priority desc, created_at asc
    limit: 10
    action: ticket_respond
    empty: "Queue clear!"

  unassigned:
    source: Ticket
    filter: assigned_to is null and status = New
    sort: created_at asc
    limit: 5
    action: ticket_assign
    empty: "All tickets assigned"

  my_stats:
    aggregate:
      resolved_today: count(Ticket where assigned_to = current_user and resolved_at = today)
      avg_response_time: avg(Ticket.first_response_minutes where assigned_to = current_user)
      satisfaction: avg(Ticket.satisfaction_score where assigned_to = current_user)

  ux:
    for agent:
      purpose: "Your personal support queue and metrics"

# Manager workspace
workspace manager_dashboard "Manager Dashboard":
  purpose: "Support team performance and SLA monitoring"

  sla_violations:
    source: Ticket
    filter: priority = Urgent and status != Resolved and hours_since(created_at) > 4
    sort: created_at asc
    display: list
    action: ticket_escalate
    empty: "All SLAs met!"

  team_performance:
    aggregate:
      total_open: count(Ticket where status in [New, Open, Pending])
      urgent_count: count(Ticket where priority = Urgent and status != Resolved)
      avg_resolution_hours: avg(Ticket.resolution_hours)
      tickets_per_agent: count(Ticket) / count(distinct Ticket.assigned_to)
      customer_satisfaction: avg(Ticket.satisfaction_score)

  agent_leaderboard:
    source: Agent
    sort: tickets_resolved_this_week desc
    limit: 10
    display: list

  trending_issues:
    source: Ticket
    filter: created_at > 7_days_ago
    group_by: category
    aggregate:
      count: count(*)
      avg_resolution: avg(resolution_hours)
    sort: count desc
    limit: 5
    display: grid

  ux:
    for manager:
      purpose: "Real-time team performance and SLA compliance"

# =============================================================================
# Example 3: Urban Forest Management with Maps
# =============================================================================

module examples.urban_forest_v2

app UrbanForestV2 "Urban Forest Management v2"

entity Tree "Tree":
  id: uuid pk
  species: str(100) required
  location_lat: decimal(9,6) required
  location_lng: decimal(9,6) required
  health: enum[Excellent, Good, Fair, Poor, Dead] = Good
  diameter_cm: int
  height_m: decimal(4,1)
  planted_date: date
  last_inspection: datetime
  notes: text

entity Caretaker "Caretaker":
  id: uuid pk
  name: str(100) required
  email: email required unique
  phone: str(20)
  certification: enum[None, Basic, Advanced, Arborist] = None
  assigned_zone: str(50)

surface tree_map "Tree Map":
  uses entity Tree
  mode: list

  section main:
    field species
    field health
    field location_lat
    field location_lng

  ux:
    purpose: "Visualize urban forest health and distribution"

    display: map

    attention critical:
      when: health = Dead
      message: "Removal needed"
      action: schedule_removal

    attention warning:
      when: health = Poor
      message: "Treatment required"
      action: schedule_treatment

    attention notice:
      when: days_since(last_inspection) > 365
      message: "Annual inspection due"
      action: schedule_inspection

workspace forest_overview "Forest Overview":
  purpose: "Urban forest health monitoring and management"

  tree_map:
    source: Tree
    display: map
    filter: health != Dead

  health_summary:
    aggregate:
      total_trees: count(Tree)
      excellent_pct: round(count(Tree where health = Excellent) * 100 / count(Tree))
      good_pct: round(count(Tree where health = Good) * 100 / count(Tree))
      fair_pct: round(count(Tree where health = Fair) * 100 / count(Tree))
      poor_pct: round(count(Tree where health = Poor) * 100 / count(Tree))
      dead_count: count(Tree where health = Dead)

  needs_attention:
    source: Tree
    filter: health in [Poor, Dead] or days_since(last_inspection) > 365
    sort: health asc, last_inspection asc
    limit: 20
    action: tree_edit

  recent_plantings:
    source: Tree
    filter: planted_date > 30_days_ago
    sort: planted_date desc
    display: timeline
    limit: 10

  ux:
    for arborist:
      purpose: "Professional tree health management"
      show_aggregate: treatment_queue, removal_queue

    for volunteer:
      scope: assigned_zone = current_user.zone
      purpose: "Community tree care coordination"

# =============================================================================
# Example 4: E-commerce with Complex Aggregates
# =============================================================================

module examples.ecommerce_v2

app EcommerceV2 "E-commerce Platform v2"

entity Product "Product":
  id: uuid pk
  sku: str(50) unique required
  name: str(200) required
  price: decimal(10,2) required
  stock: int = 0
  category: str(50)
  is_featured: bool = false

entity Order "Order":
  id: uuid pk
  order_number: str(20) unique auto_add
  customer_email: email required
  status: enum[Pending, Paid, Shipped, Delivered, Cancelled] = Pending
  total: decimal(10,2) required
  created_at: datetime auto_add

workspace sales_dashboard "Sales Dashboard":
  purpose: "Real-time sales and inventory monitoring"

  todays_metrics:
    aggregate:
      orders_today: count(Order where created_at = today)
      revenue_today: sum(Order.total where created_at = today)
      avg_order_value: avg(Order.total where created_at = today)
      conversion_rate: round(count(Order where created_at = today) * 100 / count(Session where date = today))

  top_products:
    source: Product
    sort: units_sold_today desc
    limit: 5
    display: grid

  low_stock:
    source: Product
    filter: stock < 10 and stock > 0
    sort: stock asc
    limit: 10
    action: reorder_product
    empty: "All products sufficiently stocked"

  recent_orders:
    source: Order
    sort: created_at desc
    limit: 20
    display: timeline

  revenue_trend:
    aggregate:
      today: sum(Order.total where created_at = today)
      yesterday: sum(Order.total where created_at = yesterday)
      week_ago: sum(Order.total where created_at = 7_days_ago)
      month_ago: sum(Order.total where created_at = 30_days_ago)

  ux:
    for manager:
      purpose: "Store performance and inventory management"

    for warehouse:
      purpose: "Fulfillment and stock management"
      hide: revenue_today, conversion_rate