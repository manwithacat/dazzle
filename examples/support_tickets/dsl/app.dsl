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
  ticket_number: str(20) unique
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
      scope: role = agent
      purpose: "View team"
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
      when: priority = high and status = open
      message: "High priority - needs attention"
      action: ticket_edit

    attention notice:
      when: status = open
      message: "Open ticket"
      action: ticket_edit

    # Persona-specific views
    for customer:
      scope: created_by = current_user
      purpose: "Your support requests"
      show: ticket_number, title, status, created_at, updated_at
      hide: assigned_to
      action_primary: ticket_create

    for agent:
      scope: all
      purpose: "Your ticket queue"
      show: ticket_number, title, status, priority, created_by, created_at
      action_primary: ticket_edit

    for manager:
      scope: all
      purpose: "Team ticket oversight"
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
      hide: assigned_to
      action_primary: comment_create

    for agent:
      scope: all
      action_primary: comment_create

surface ticket_create "Create Ticket":
  uses entity Ticket
  mode: create

  section main "New Ticket":
    field title "Title"
    field description "Description"
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
      scope: all

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
    field content "Comment"
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

  # Critical tickets needing attention
  urgent_queue:
    source: Ticket
    filter: priority = critical and status != resolved
    sort: priority desc, created_at asc
    limit: 5
    display: list
    action: ticket_edit
    empty: "No urgent tickets!"

  # Main work queue
  my_tickets:
    source: Ticket
    filter: status = open
    sort: updated_at desc
    limit: 10
    display: list
    action: ticket_detail
    empty: "No open tickets"

  # Stats
  stats:
    source: Ticket
    aggregate:
      total: count(Ticket)
      open: count(Ticket where status = open)
      resolved: count(Ticket where status = resolved)

  ux:
    for agent:
      purpose: "Manage your support queue efficiently"

# Manager workspace - team oversight
workspace manager_dashboard "Manager Dashboard":
  purpose: "Team performance monitoring"

  # Critical issues
  critical_tickets:
    source: Ticket
    filter: priority = critical and status != resolved
    sort: created_at asc
    limit: 10
    display: list
    action: ticket_edit
    empty: "No critical tickets!"

  # High priority tickets
  high_priority:
    source: Ticket
    filter: priority = high and status != resolved
    sort: created_at asc
    limit: 10
    display: list
    action: ticket_edit
    empty: "No high priority tickets"

  # Team metrics
  metrics:
    source: Ticket
    aggregate:
      total: count(Ticket)
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      resolved: count(Ticket where status = resolved)

  ux:
    for manager:
      purpose: "Monitor team performance"

# Customer workspace - self-service portal
workspace customer_portal "My Support":
  purpose: "View and manage your support requests"

  # Active tickets
  active_tickets:
    source: Ticket
    filter: status != closed
    sort: updated_at desc
    limit: 10
    display: list
    action: ticket_detail
    empty: "No active tickets"

  # Closed tickets
  closed_tickets:
    source: Ticket
    filter: status = closed
    sort: updated_at desc
    limit: 10
    display: list
    action: ticket_detail
    empty: "No closed tickets"

  ux:
    for customer:
      purpose: "Track your support requests"
      action_primary: ticket_create
