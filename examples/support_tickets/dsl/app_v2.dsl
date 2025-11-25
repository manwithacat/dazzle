# DAZZLE v0.2 - Support Ticket System with UX Semantic Layer
# Enhanced version demonstrating personas, attention signals, and workspaces

module support_tickets.core

app support_tickets "Support Tickets"

# User entity - enhanced with role for persona support
entity User "User":
  id: uuid pk
  email: str(255) required unique
  name: str(200) required
  role: enum[customer,agent,manager,admin]=customer
  team: str(50)
  is_active: bool = true
  created_at: datetime auto_add

# Ticket entity - enhanced with SLA and resolution tracking
entity Ticket "Support Ticket":
  id: uuid pk
  ticket_number: str(20) unique auto_add
  title: str(200) required
  description: text required
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
  category: enum[bug,feature,question,billing,other]=other
  created_by: ref User required
  assigned_to: ref User
  resolution: text
  satisfaction_score: int
  created_at: datetime auto_add
  updated_at: datetime auto_update
  first_response_at: datetime
  resolved_at: datetime

  index status, priority
  index created_by
  index assigned_to

# Comment entity - enhanced with internal flag
entity Comment "Comment":
  id: uuid pk
  ticket: ref Ticket required
  author: ref User required
  content: text required
  is_internal: bool = false  # Internal notes vs customer-visible
  created_at: datetime auto_add

# ============================================================================
# USER SURFACES WITH UX
# ============================================================================

surface user_list "User List":
  uses entity User
  mode: list

  section main "Users":
    field email "Email"
    field name "Name"
    field role "Role"
    field team "Team"
    field is_active "Active"
    field created_at "Created"

  ux:
    purpose: "Manage system users and their roles"

    show: email, name, role, team, is_active
    sort: role asc, name asc
    filter: role, team, is_active
    search: email, name
    empty: "No users found. Add team members to get started."

    attention warning:
      when: is_active = false
      message: "Inactive user"

    for manager:
      scope: all
      purpose: "User administration"
      action_primary: user_create

    for agent:
      scope: role in [agent, customer]
      purpose: "View team and customers"
      read_only: true

# ============================================================================
# TICKET SURFACES WITH UX
# ============================================================================

surface ticket_list "Ticket List":
  uses entity Ticket
  mode: list

  section main "Support Tickets":
    field ticket_number "Ticket #"
    field title "Title"
    field status "Status"
    field priority "Priority"
    field category "Category"
    field created_by "Customer"
    field assigned_to "Agent"
    field created_at "Created"
    field updated_at "Updated"

  ux:
    purpose: "Track and manage customer support tickets"

    sort: priority desc, created_at asc
    filter: status, priority, category, assigned_to
    search: title, description, ticket_number
    empty: "No tickets found. Adjust filters or wait for new tickets."

    # SLA-based attention signals
    attention critical:
      when: priority = critical and status != resolved
      message: "Critical - respond within 1 hour"
      action: ticket_edit

    attention warning:
      when: priority = high and hours_since(created_at) > 4 and status = open
      message: "High priority SLA breach"
      action: ticket_edit

    attention notice:
      when: status = open and assigned_to is null
      message: "Unassigned"
      action: ticket_edit

    # Persona-specific views
    for customer:
      scope: created_by = current_user
      purpose: "Your support requests"
      show: ticket_number, title, status, created_at, updated_at
      hide: assigned_to, is_internal
      action_primary: ticket_create

    for agent:
      scope: assigned_to = current_user or status = open
      purpose: "Your ticket queue"
      show: ticket_number, title, status, priority, created_by, created_at
      show_aggregate: my_open_count, unassigned_count
      action_primary: ticket_edit

    for manager:
      scope: all
      purpose: "Team ticket oversight"
      show_aggregate: open_count, critical_count, avg_response_time, sla_violations
      action_primary: ticket_list

surface ticket_detail "Ticket Detail":
  uses entity Ticket
  mode: view

  section header "Ticket Information":
    field ticket_number "Ticket #"
    field title "Title"
    field status "Status"
    field priority "Priority"
    field category "Category"

  section details "Details":
    field description "Description"
    field created_by "Customer"
    field assigned_to "Assigned Agent"
    field resolution "Resolution"

  section timeline "Timeline":
    field created_at "Created"
    field first_response_at "First Response"
    field resolved_at "Resolved"
    field updated_at "Last Updated"

  section satisfaction "Feedback":
    field satisfaction_score "Satisfaction Score"

  ux:
    purpose: "View complete ticket information and history"

    attention critical:
      when: priority = critical and status != resolved
      message: "Critical priority - requires immediate attention"

    for customer:
      scope: created_by = current_user
      hide: assigned_to, is_internal
      action_primary: comment_create

    for agent:
      scope: assigned_to = current_user or role = agent
      show_aggregate: comment_count, internal_note_count
      action_primary: comment_create

surface ticket_create "Create Ticket":
  uses entity Ticket
  mode: create

  section main "New Ticket":
    field title "Title" required=true
    field description "Description" required=true
    field category "Category"
    field priority "Priority"

  ux:
    purpose: "Submit a new support request"

    for customer:
      defaults:
        created_by: current_user
        status: open

surface ticket_edit "Edit Ticket":
  uses entity Ticket
  mode: edit

  section main "Edit Ticket":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field category "Category"
    field assigned_to "Assigned To"
    field resolution "Resolution"

  ux:
    purpose: "Update ticket details and assignment"

    for agent:
      scope: assigned_to = current_user or role = agent

    for manager:
      scope: all

# ============================================================================
# COMMENT SURFACES WITH UX
# ============================================================================

surface comment_list "Comments":
  uses entity Comment
  mode: list

  section main "Comments":
    field author "Author"
    field content "Content"
    field is_internal "Internal"
    field created_at "Posted"

  ux:
    purpose: "View ticket conversation history"

    sort: created_at desc
    empty: "No comments yet."

    for customer:
      scope: is_internal = false
      hide: is_internal

surface comment_create "Add Comment":
  uses entity Comment
  mode: create

  section main "New Comment":
    field content "Comment" required=true
    field is_internal "Internal Note"

  ux:
    purpose: "Add response or internal note to ticket"

    for customer:
      hide: is_internal
      defaults:
        author: current_user
        is_internal: false

    for agent:
      defaults:
        author: current_user

# ============================================================================
# WORKSPACES
# ============================================================================

# Agent workspace - daily workflow
workspace agent_dashboard "Agent Dashboard":
  purpose: "Support agent daily workflow and queue management"

  # Critical tickets needing immediate attention
  urgent_queue:
    source: Ticket
    filter: (assigned_to = current_user or assigned_to is null) and priority in [critical, high] and status != resolved
    sort: priority desc, created_at asc
    limit: 5
    display: list
    action: ticket_edit
    empty: "No urgent tickets!"

  # Main work queue
  my_tickets:
    source: Ticket
    filter: assigned_to = current_user and status in [open, in_progress]
    sort: updated_at desc
    limit: 10
    display: list
    action: ticket_detail
    empty: "No assigned tickets"

  # Unassigned tickets to pick up
  available_tickets:
    source: Ticket
    filter: assigned_to is null and status = open
    sort: priority desc, created_at asc
    limit: 5
    display: list
    action: ticket_edit
    empty: "All tickets assigned"

  # Personal metrics
  my_metrics:
    aggregate:
      open_tickets: count(Ticket where assigned_to = current_user and status in [open, in_progress])
      resolved_today: count(Ticket where assigned_to = current_user and resolved_at = today)
      avg_resolution_time: avg(Ticket.resolution_hours where assigned_to = current_user)
      satisfaction: avg(Ticket.satisfaction_score where assigned_to = current_user and satisfaction_score is not null)

  # Recent activity
  recent_comments:
    source: Comment
    filter: ticket.assigned_to = current_user
    sort: created_at desc
    limit: 10
    display: timeline
    empty: "No recent comments"

  ux:
    for agent:
      purpose: "Manage your support queue efficiently"

# Manager workspace - team oversight
workspace manager_dashboard "Manager Dashboard":
  purpose: "Team performance monitoring and SLA compliance"

  # SLA violations and critical issues
  sla_violations:
    source: Ticket
    filter: (priority = critical and hours_since(created_at) > 1 and status != resolved) or (priority = high and hours_since(created_at) > 4 and status != resolved)
    sort: priority desc, created_at asc
    display: list
    action: ticket_edit
    empty: "All SLAs met!"

  # Team performance metrics
  team_metrics:
    aggregate:
      total_open: count(Ticket where status in [open, in_progress])
      critical_count: count(Ticket where priority = critical and status != resolved)
      high_count: count(Ticket where priority = high and status != resolved)
      unassigned: count(Ticket where assigned_to is null and status = open)
      avg_response_time_hours: avg(Ticket.first_response_hours)
      avg_resolution_time_hours: avg(Ticket.resolution_hours)
      tickets_created_today: count(Ticket where created_at = today)
      tickets_resolved_today: count(Ticket where resolved_at = today)
      satisfaction_avg: avg(Ticket.satisfaction_score where satisfaction_score is not null)

  # Agent performance
  agent_performance:
    source: User
    filter: role = agent and is_active = true
    aggregate:
      assigned_tickets: count(Ticket where assigned_to = this)
      resolved_this_week: count(Ticket where assigned_to = this and resolved_at >= 7_days_ago)
      avg_resolution_time: avg(Ticket.resolution_hours where assigned_to = this)
      satisfaction: avg(Ticket.satisfaction_score where assigned_to = this)
    sort: resolved_this_week desc
    display: grid

  # Category breakdown
  issue_breakdown:
    source: Ticket
    filter: created_at >= 30_days_ago
    group_by: category
    aggregate:
      count: count(*)
      avg_resolution: avg(resolution_hours)
      critical_pct: count(where priority = critical) * 100 / count(*)
    sort: count desc
    display: grid

  # Trending issues (last 7 days)
  trending:
    source: Ticket
    filter: created_at >= 7_days_ago
    sort: created_at desc
    limit: 20
    display: timeline

  ux:
    for manager:
      purpose: "Monitor team performance and identify bottlenecks"

# Customer workspace - self-service portal
workspace customer_portal "My Support":
  purpose: "View and manage your support requests"

  # Active tickets
  my_tickets:
    source: Ticket
    filter: created_by = current_user and status not in [closed]
    sort: updated_at desc
    display: list
    action: ticket_detail
    empty: "No active tickets. Need help? Create a new ticket."

  # Ticket history
  history:
    source: Ticket
    filter: created_by = current_user and status = closed
    sort: resolved_at desc
    limit: 10
    display: list
    action: ticket_detail
    empty: "No resolved tickets yet."

  # Recent updates
  updates:
    source: Comment
    filter: ticket.created_by = current_user and is_internal = false
    sort: created_at desc
    limit: 10
    display: timeline
    empty: "No recent updates"

  ux:
    for customer:
      purpose: "Track your support requests and responses"
      action_primary: ticket_create