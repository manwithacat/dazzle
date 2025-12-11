# DAZZLE Support Ticket System
# Demonstrates v0.7.1+ LLM Cognition Features:
# - Entity archetypes for reusable patterns
# - Intent declarations for semantic clarity
# - Domain/pattern tags for classification
# - State machine for ticket lifecycle
# - Computed fields for metrics
# - Invariants with error messages
# - Role-based access control
# - Workspace with scanner_table stage

module support_tickets.core

app support_tickets "Support Tickets"

# =============================================================================
# ARCHETYPES - Reusable entity patterns
# =============================================================================

archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype Auditable:
  created_by: ref User
  updated_by: ref User

# =============================================================================
# ENTITIES
# =============================================================================

# User entity with role-based access
entity User "User":
  intent: "Authenticate users and define their access level for ticket operations"
  domain: identity
  patterns: authentication, authorization

  id: uuid pk
  email: str(255) required unique
  name: str(200) required
  role: enum[customer,agent,manager]=customer
  is_active: bool = true
  created_at: datetime auto_add

  # Invariant: users must have valid role
  invariant: role != null

# Ticket entity with full business logic
entity Ticket "Support Ticket":
  # Note: extends archetype field merging is planned but not yet implemented
  # extends: Timestamped
  intent: "Track customer issues through resolution with SLA awareness"
  domain: support
  patterns: lifecycle, workflow, audit

  id: uuid pk
  ticket_number: str(20) unique
  title: str(200) required
  description: text required
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
  category: enum[bug,feature,question,other]=other
  created_by: ref User required
  assigned_to: ref User
  resolution: text
  created_at: datetime auto_add
  updated_at: datetime auto_update
  resolved_at: datetime

  # Computed field: days since ticket was opened
  days_open: computed days_since(created_at)

  # State machine: ticket status transitions
  transitions:
    open -> in_progress: requires assigned_to
    in_progress -> resolved: requires resolution
    in_progress -> open
    resolved -> closed
    resolved -> in_progress
    closed -> open: role(manager)

  # Invariants for data integrity
  invariant: status != resolved or resolution != null
  invariant: status != closed or resolution != null

  # Access control: customers see own tickets, agents see all
  access:
    read: created_by = current_user or role(agent) or role(manager)
    write: role(agent) or role(manager)

  index status, priority
  index created_by
  index assigned_to

# Comment entity with internal note support
entity Comment "Comment":
  intent: "Enable threaded communication on tickets with internal notes for agents"
  domain: support
  patterns: audit, messaging

  id: uuid pk
  ticket: ref Ticket required
  author: ref User required
  content: text required
  is_internal: bool = false
  created_at: datetime auto_add

  # Access: internal comments only visible to agents/managers
  access:
    read: is_internal = false or role(agent) or role(manager)
    write: role(agent) or role(manager)

# ============================================================================
# USER SURFACES
# ============================================================================

surface user_list "User List":
  uses entity User
  mode: list

  section main "Users":
    field email "Email"
    field name "Name"
    field role "Role"
    field is_active "Active"
    field created_at "Created"

surface user_detail "User Detail":
  uses entity User
  mode: view

  section main "User Details":
    field email "Email"
    field name "Name"
    field role "Role"
    field is_active "Active"
    field created_at "Created"

surface user_create "Create User":
  uses entity User
  mode: create

  section main "New User":
    field email "Email"
    field name "Name"
    field role "Role"

surface user_edit "Edit User":
  uses entity User
  mode: edit

  section main "Edit User":
    field email "Email"
    field name "Name"
    field role "Role"
    field is_active "Active"

# ============================================================================
# TICKET SURFACES
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
    field assigned_to "Assigned To"
    field created_at "Created"

surface ticket_detail "Ticket Detail":
  uses entity Ticket
  mode: view

  section main "Ticket Details":
    field ticket_number "Ticket #"
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field category "Category"
    field created_by "Created By"
    field assigned_to "Assigned To"
    field resolution "Resolution"
    field created_at "Created"
    field updated_at "Updated"
    field resolved_at "Resolved"

surface ticket_create "Create Ticket":
  uses entity Ticket
  mode: create

  section main "New Ticket":
    field title "Title"
    field description "Description"
    field priority "Priority"
    field category "Category"
    field assigned_to "Assigned To"

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

# ============================================================================
# COMMENT SURFACES
# ============================================================================

surface comment_list "Comment List":
  uses entity Comment
  mode: list

  section main "Comments":
    field content "Comment"
    field author "Author"
    field is_internal "Internal"
    field created_at "Created"

surface comment_detail "Comment Detail":
  uses entity Comment
  mode: view

  section main "Comment Details":
    field ticket "Ticket"
    field author "Author"
    field content "Comment"
    field is_internal "Internal"
    field created_at "Created"

surface comment_create "Create Comment":
  uses entity Comment
  mode: create

  section main "New Comment":
    field ticket "Ticket"
    field content "Comment"
    field is_internal "Internal"

surface comment_edit "Edit Comment":
  uses entity Comment
  mode: edit

  section main "Edit Comment":
    field content "Comment"
    field is_internal "Internal"

# =============================================================================
# WORKSPACES - Composed views with stages
# =============================================================================

workspace ticket_queue "Ticket Queue":
  purpose: "Agent workspace for managing incoming support tickets"
  stage: "scanner_table"

  queue_metrics:
    source: Ticket
    display: summary
    aggregate:
      total_open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      critical: count(Ticket where priority = critical and status != closed)

  ticket_table:
    source: Ticket
    filter: status != closed
    sort: priority desc, created_at asc
    display: list
    action: ticket_edit
    empty: "No open tickets"

workspace agent_dashboard "Agent Dashboard":
  purpose: "Personal dashboard for support agents"
  stage: "dual_pane_flow"

  my_assigned:
    source: Ticket
    filter: assigned_to = current_user and status = in_progress
    sort: priority desc
    limit: 10
    display: list
    action: ticket_edit
    empty: "No tickets assigned to you"

  pending_resolution:
    source: Ticket
    filter: assigned_to = current_user and status = resolved
    sort: updated_at desc
    limit: 5
    display: list
    action: ticket_detail
    empty: "No tickets pending closure"
