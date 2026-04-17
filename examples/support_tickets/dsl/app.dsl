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

app support_tickets "Support Tickets":
  security_profile: basic

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
  display_field: name
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

  fitness:
    repr_fields: [name, email, role, is_active]

# Ticket entity with full business logic
entity Ticket "Support Ticket":
  display_field: title
  # Note: extends archetype field merging is planned but not yet implemented
  # extends: Timestamped
  intent: "Track customer issues through resolution with SLA awareness"
  domain: support
  patterns: lifecycle, workflow, audit_trail

  id: uuid pk
  ticket_number: str(20) unique
  title: str(200) required
  description: text required
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
  category: enum[bug,feature,inquiry,other]=other
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

  # Lifecycle: progress evaluator ordering + evidence predicates (ADR-0020)
  lifecycle:
    status_field: status
    states:
      - open        (order: 0)
      - in_progress (order: 1)
      - resolved    (order: 2)
      - closed      (order: 3)
    transitions:
      - from: open
        to: in_progress
        evidence: assigned_to != null
        role: agent
      - from: in_progress
        to: resolved
        evidence: resolution != null
        role: agent
      - from: resolved
        to: closed
        evidence: true
        role: agent

  # Invariants for data integrity
  invariant: status != resolved or resolution != null
  invariant: status != closed or resolution != null

  # Access control
  permit:
    list: role(customer) or role(agent) or role(manager)
    read: role(customer) or role(agent) or role(manager)
    create: role(customer) or role(agent) or role(manager)
    update: role(agent) or role(manager)
    delete: role(manager)

  scope:
    list: created_by = current_user
      for: customer
    list: all
      for: agent, manager

  fitness:
    repr_fields: [title, status, priority, category, assigned_to]

  index status, priority
  index created_by
  index assigned_to

# Comment entity with internal note support
entity Comment "Comment":
  intent: "Enable threaded communication on tickets with internal notes for agents"
  domain: support
  patterns: audit_trail, messaging

  id: uuid pk
  ticket: ref Ticket required
  author: ref User required
  content: text required
  is_internal: bool = false
  created_at: datetime auto_add

  # Access control
  permit:
    list: role(customer) or role(agent) or role(manager)
    read: role(customer) or role(agent) or role(manager)
    create: role(customer) or role(agent) or role(manager)
    update: role(agent) or role(manager)
    delete: role(manager)

  scope:
    list: all
      for: agent, manager, customer

  fitness:
    repr_fields: [ticket, author, content, is_internal]

# ============================================================================
# USER SURFACES
# ============================================================================

surface user_list "User List":
  uses entity User
  mode: list

  ux:
    purpose: "Browse and manage team members across the support organisation"
    sort: name asc
    filter: role, is_active
    search: email, name
    empty: "No users found. Invite team members to get started."

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

  related tickets "Tickets":
    display: table
    show: Ticket

  related comments "Comments":
    display: table
    show: Comment

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

  ux:
    purpose: "Triage and resolve incoming support tickets across the queue"
    sort: created_at desc
    filter: status, priority, category
    search: ticket_number, title
    empty: "No support tickets. All clear!"

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

  section summary "Summary":
    field title "Title"
    field description "Description"

  section triage "Triage":
    field priority "Priority"
    field category "Category"
    field assigned_to "Assigned To"

surface ticket_edit "Edit Ticket":
  uses entity Ticket
  mode: edit

  section summary "Summary":
    field title "Title"
    field description "Description"

  section triage "Triage":
    field priority "Priority"
    field category "Category"
    field assigned_to "Assigned To"

  section status_section "Status & Resolution":
    field status "Status"
    field resolution "Resolution"

# ============================================================================
# COMMENT SURFACES
# ============================================================================

surface comment_list "Comment List":
  uses entity Comment
  mode: list

  ux:
    purpose: "Scan recent comment activity across all tickets for context and follow-up"
    sort: created_at desc
    filter: is_internal
    search: content
    empty: "No comments yet. Start the conversation."

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

  ticket_board:
    source: Ticket
    filter: status != closed
    display: kanban
    group_by: status
    action: ticket_edit
    empty: "No open tickets"

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

  activity_timeline:
    source: Comment
    sort: created_at desc
    limit: 30
    display: timeline
    action: comment_detail
    empty: "No activity yet"

  ticket_history:
    source: Ticket
    sort: updated_at desc
    limit: 20
    display: timeline
    action: ticket_detail
    empty: "No tickets logged yet"

  recent_comments:
    source: Comment
    sort: created_at desc
    limit: 10
    display: list
    action: comment_detail
    empty: "No recent comments"

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

  # Comment activity feed — live-updating stream
  comment_activity:
    source: Comment
    display: activity_feed
    sort: created_at desc
    limit: 20
    empty: "No recent comments"

  # Resolution progress — funnel of tickets through lifecycle stages
  resolution_funnel:
    source: Ticket
    display: funnel_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No tickets"

  # Stage progress for the current ticket backlog
  backlog_progress:
    source: Ticket
    display: progress
    group_by: status
    empty: "No backlog"

workspace my_tickets "My Tickets":
  purpose: "Customer view of their submitted tickets"
  stage: "simple_list"

  customer_tickets:
    source: Ticket
    filter: created_by = current_user
    sort: created_at desc
    display: list
    action: ticket_detail
    empty: "You have not submitted any tickets yet"

# =============================================================================
# PERSONAS - User archetypes for testing
# =============================================================================

persona admin "Administrator":
  default_workspace: _platform_admin

persona customer "Customer":
  description: "End user submitting support requests and tracking their status"
  goals: "Submit new tickets easily", "Track ticket status and updates", "Receive timely responses from support"
  proficiency: novice
  default_workspace: my_tickets

persona agent "Support Agent":
  description: "First-line support handling incoming tickets"
  goals: "Process tickets efficiently", "Maintain SLA compliance", "Escalate complex issues to managers"
  proficiency: intermediate
  default_workspace: ticket_queue

persona manager "Support Manager":
  description: "Team lead monitoring performance and handling escalations"
  goals: "Monitor team metrics and performance", "Identify bottlenecks in ticket flow", "Ensure quality and customer satisfaction"
  proficiency: expert
  default_workspace: agent_dashboard

# =============================================================================
# SCENARIOS - Testing contexts with demo data
# =============================================================================

scenario happy_path "Happy Path":
  description: "Normal ticket flow - customer submits, agent resolves, customer satisfied"
  persona_entries:
    customer: start_route="/tickets/new"
    agent: start_route="/queue"

scenario escalation "Escalation Flow":
  description: "Critical issue requiring manager attention and oversight"
  persona_entries:
    customer: start_route="/tickets"
    agent: start_route="/queue?priority=critical"
    manager: start_route="/dashboard"

scenario backlog "Backlog Scenario":
  description: "High volume testing with many open tickets"
  seed_data_path: "fixtures/backlog.json"
  persona_entries:
    agent: start_route="/queue"
    manager: start_route="/dashboard"

# =============================================================================
# TOP-LEVEL ENUM — shared severity vocabulary
# =============================================================================

enum Severity "Severity":
  blocker
  high
  medium
  low

# =============================================================================
# SLA — response-time commitments on open tickets
# =============================================================================

sla TicketResponseTime "Ticket Response SLA":
  entity: Ticket
  starts_when: status -> open
  completes_when: status -> in_progress
  tiers:
    warning: 2 hours
    breach: 4 hours
    critical: 8 hours
  business_hours:
    schedule: "Mon-Fri 09:00-17:00"
    timezone: "Europe/London"
  on_breach:
    notify: manager

# =============================================================================
# APPROVAL — manager approval for closing critical tickets
# =============================================================================

approval CriticalClose "Critical Ticket Close Approval":
  entity: Ticket
  trigger: status -> closed
  approver_role: manager
  quorum: 1
  threshold: priority = critical
  outcomes:
    approved -> closed
    rejected -> resolved

# =============================================================================
# WEBHOOK — outbound notification on ticket lifecycle events
# =============================================================================

webhook TicketNotify "Ticket Lifecycle Webhook":
  entity: Ticket
  events: [created, updated]
  url: config("TICKET_WEBHOOK_URL")
  auth:
    method: hmac_sha256
    secret: config("TICKET_WEBHOOK_SECRET")
  payload:
    include: [id, ticket_number, status, priority]
    format: json
  retry:
    max_attempts: 3
    backoff: exponential

# =============================================================================
# RHYTHM — agent daily triage cadence
# =============================================================================

rhythm agent_daily "Agent Daily Triage":
  persona: agent

  phase morning:
    scene review "Review Queue":
      on: ticket_list

  phase midday:
    scene resolve "Resolve Active":
      on: ticket_queue

# =============================================================================
# ISLAND — lightweight interactive widget for ticket composer
# =============================================================================

island ticket_composer "Ticket Composer":
  fallback: "Loading composer..."

# =============================================================================
# FEEDBACK WIDGET — in-app feedback capture
# =============================================================================

feedback_widget: enabled
  position: bottom-right
  shortcut: backtick
  categories: [bug, ux, visual, enhancement, other]
  severities: [blocker, annoying, minor]
