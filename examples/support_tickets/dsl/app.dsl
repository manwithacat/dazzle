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

# User entity with role-based access.
#
# Tutorial-only: permit:/scope: blocks intentionally omitted on User —
# this app's primary access surface is on Ticket / Comment (which DO
# declare full permit + scope rules). Adding permit/scope here would
# also require deciding whether end-users can list/edit other users,
# which is out of scope for the support-flow demo. Production DSL
# would declare these — see `docs/reference/rbac-scope.md` (#1123)
# and `examples/simple_task/`'s User entity for the canonical shape.
entity User "User":
  display_field: name
  intent: "Authenticate users and define their access level for ticket operations"
  domain: identity
  patterns: authentication, authorization

  id: uuid pk
  # pii() feeds `dazzle compliance privacy` → docs/privacy/* (privacy notice,
  # cookie policy, ROPA) and analytics PII stripping. Contact/identity are the
  # load-bearing demo annotations for a data-protection-aware SaaS example.
  email: str(255) required unique pii(category=contact)
  name: str(200) required pii(category=identity)
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
  description: text required pii(category=freeform)
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
      as: customer
    list: all
      as: agent, manager
    read: created_by = current_user
      as: customer
    read: all
      as: agent, manager
    # v0.71.19 (#1123): customers can read but not update their own
    # tickets (filed-and-forget model). Agents/managers update any
    # ticket. Delete is manager-only (matches permit). Customer creates
    # are allowed; create-time scope deferred (#1124).
    create: all
      as: customer, agent, manager
    update: all
      as: agent, manager
    delete: all
      as: manager

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
  content: text required pii(category=freeform)
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
    list: is_internal = false
      as: customer
    list: all
      as: agent, manager
    read: is_internal = false
      as: customer
    read: all
      as: agent, manager
    # v0.71.19 (#1123): customers never see internal-note rows
    # (list/read scope blocks them); on the write side, customers can
    # still create comments (no internal-flag enforcement on insert
    # yet — that's the create-time scope work deferred to #1124).
    # Agents/managers update any comment; manager-only deletes.
    create: all
      as: customer, agent, manager
    update: all
      as: agent, manager
    delete: all
      as: manager

  fitness:
    repr_fields: [ticket, author, content, is_internal]

# ============================================================================
# USER SURFACES
# ============================================================================

surface user_list "User List":
  uses entity User
  mode: list
  render: fragment

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
  render: fragment

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
  render: fragment

  section main "New User":
    field email "Email"
    field name "Name"
    field role "Role"

surface user_edit "Edit User":
  uses entity User
  mode: edit
  render: fragment

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
  render: fragment
  # Row peek opens the ticket in a slide-over drawer (HM drawer
  # Hyperpart) instead of the default inline expand — the queue keeps
  # its scan position while an agent glances at a ticket.
  peek: slide_over

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
  render: fragment

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
  render: fragment

  section summary "Summary":
    field title "Title"
    field description "Description"

  section triage "Triage":
    field priority "Priority"
    field category "Category"
    field assigned_to "Assigned To"

  ux:
    as customer:
      hide: assigned_to

surface ticket_edit "Edit Ticket":
  uses entity Ticket
  mode: edit
  render: fragment

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
  render: fragment

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
  render: fragment

  section main "Comment Details":
    field ticket "Ticket"
    field author "Author"
    field content "Comment"
    field is_internal "Internal"
    field created_at "Created"

surface comment_create "Create Comment":
  uses entity Comment
  mode: create
  render: fragment

  section main "New Comment":
    field ticket "Ticket"
    field content "Comment"
    field is_internal "Internal"

  ux:
    as customer:
      hide: is_internal

surface comment_edit "Edit Comment":
  uses entity Comment
  mode: edit
  render: fragment

  section main "Edit Comment":
    field content "Comment"
    field is_internal "Internal"

  ux:
    as customer:
      hide: is_internal

# =============================================================================
# WORKSPACES - Composed views with stages
# =============================================================================

# Story-driven compositions (docs/guides/story-to-composition.md):
#   agent  → ticket_queue  = metrics + queue + kanban  (ST-019–023)
#   manager → manager_ops  = metrics + SLA strip + focused queues (ST-027–029)
#   customer → my_tickets  = my metrics + open queue + history (ST-024–026)

workspace ticket_queue "Ticket Queue":
  purpose: "Agent workspace for managing incoming support tickets"
  stage: "scanner_table"
  access: persona(agent, manager)

  # Job primary: at-a-glance pressure (tones on critical).
  queue_metrics:
    source: Ticket
    display: metrics
    aggregate:
      total_open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      critical: count(Ticket where priority = critical and status != closed)
    tones:
      critical: destructive
      in_progress: accent

  # ST-019 worklist — review queue with inline status transitions, not a CRUD table.
  # date_range: fleet dogfood for the date-range Hyperpart (filters created_at).
  open_queue:
    source: Ticket
    filter: status != closed
    sort: priority desc, created_at asc
    display: queue
    date_range
    date_field: created_at
    action: ticket_edit
    empty: "No open tickets"

  # Lifecycle board (secondary) — status columns for flow, not the primary worklist.
  ticket_board:
    source: Ticket
    filter: status != closed
    display: kanban
    group_by: status
    action: ticket_edit
    empty: "No open tickets"

workspace manager_ops "Manager Ops":
  # ST-027 team performance + SLA narrative; critical/unassigned queues for
  # ST-028/029. TR-52 moved managers off empty personal assigned lists — this
  # is the metrics-first home that matches the story.
  purpose: "Team performance, SLA readiness, and escalations"
  stage: "command_center"
  access: persona(manager)

  team_metrics:
    source: Ticket
    display: metrics
    aggregate:
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      critical_open: count(Ticket where priority = critical and status != closed)
      resolved: count(Ticket where status = resolved)
    tones:
      critical_open: destructive
      resolved: positive
      in_progress: accent

  # Static readiness strip — pairs with sla TicketResponseTime commitment.
  sla_readiness:
    display: status_list
    entries:
      - title: "Ticket response SLA"
        caption: "Warning 2h · breach 4h · critical 8h (business hours)"
        icon: "clock"
        state: accent
      - title: "Critical open"
        caption: "Priority critical tickets must stay assigned and progressing"
        icon: "triangle-alert"
        state: warning
      - title: "Unassigned open"
        caption: "Open tickets with no assignee block first response"
        icon: "user"
        state: warning
      - title: "Resolved pending close"
        caption: "Resolved tickets await customer confirmation or agent close"
        icon: "circle-check"
        state: positive

  critical_queue:
    source: Ticket
    filter: priority = critical and status != closed
    sort: created_at asc
    display: queue
    action: ticket_edit
    empty: "No critical tickets open"

  unassigned_queue:
    source: Ticket
    filter: assigned_to = null and status = open
    sort: priority desc, created_at asc
    display: queue
    action: ticket_edit
    empty: "Every open ticket has an assignee"

  resolution_funnel:
    source: Ticket
    display: funnel_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No tickets"

workspace agent_dashboard "Agent Dashboard":
  # Personal agent view (assigned work + activity). Manager team home is
  # manager_ops; agents keep this for "my WIP" after claiming from the queue.
  purpose: "Personal dashboard for support agents"
  stage: "dual_pane_flow"
  access: persona(agent, manager)

  # ── Work first: assigned + pending tickets ──────────────────────────
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

  # ── Lifecycle / SLA signal ──────────────────────────────────────────
  resolution_funnel:
    source: Ticket
    display: funnel_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No tickets"

  backlog_progress:
    source: Ticket
    display: progress
    group_by: status
    empty: "No backlog"

  ticket_history:
    source: Ticket
    sort: updated_at desc
    limit: 20
    display: timeline
    action: ticket_detail
    empty: "No tickets logged yet"

  # ── Activity last (comment noise) ───────────────────────────────────
  recent_comments:
    source: Comment
    sort: created_at desc
    limit: 10
    display: list
    action: comment_detail
    empty: "No recent comments"

  comment_activity:
    source: Comment
    display: activity_feed
    sort: created_at desc
    limit: 20
    empty: "No recent comments"

  activity_timeline:
    source: Comment
    sort: created_at desc
    limit: 30
    display: timeline
    action: comment_detail
    empty: "No activity yet"

workspace my_tickets "My Tickets":
  purpose: "Customer view of their submitted tickets"
  stage: "simple_list"
  access: persona(customer)

  # ST-025 rollup — scope rules already limit counts to the current customer.
  my_summary:
    source: Ticket
    display: metrics
    aggregate:
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      resolved: count(Ticket where status = resolved)
    tones:
      open: accent
      resolved: positive

  # Active cases as a queue (story-shaped), not agent triage chrome.
  open_cases:
    source: Ticket
    filter: created_by = current_user and status != closed
    sort: updated_at desc
    display: queue
    action: ticket_detail
    empty: "You have no open tickets"

  all_cases:
    source: Ticket
    filter: created_by = current_user
    sort: created_at desc
    display: list
    action: ticket_detail
    empty: "You have not submitted any tickets yet"

# =============================================================================
# CONTEXT-SELECTOR SCENARIO (#1304 verification)
# Pick an agent from the selector; both regions re-scope to that agent.
# Exercises: workspace `context_selector` + a 1-hop `current_context` filter
# (`assigned_to = current_context`) and a 2-hop dotted one
# (`ticket.assigned_to = current_context`, Comment -> ticket -> assigned_to).
# Backed by the deterministic backend gate (tests/) + an INTERACTION_WALK
# gesture that drives the <select> and asserts the regions re-scope.
# =============================================================================

workspace agent_console "Agent Console":
  purpose: "Pick an agent to see the tickets assigned to them and the comments on those tickets"
  stage: "simple_list"
  access: persona(admin, manager, agent)

  context_selector:
    entity: User
    display_field: name

  # 1-hop: tickets directly assigned to the selected agent.
  agent_tickets:
    source: Ticket
    filter: assigned_to = current_context
    sort: priority desc
    display: list
    action: ticket_detail
    empty: "No tickets assigned to this agent"

  # 2-hop dotted (the #1304 case): comments on tickets assigned to the
  # selected agent — Comment -> ticket -> assigned_to.
  agent_ticket_comments:
    source: Comment
    filter: ticket.assigned_to = current_context
    sort: created_at desc
    display: list
    action: comment_detail
    empty: "No comments on this agent's tickets"

  # 1-hop aggregate (the #1305 case): category distribution of the selected
  # agent's tickets. A bar_chart with group_by + aggregate must re-scope by
  # current_context exactly as the list region above does — pre-#1305 the
  # current_context predicate reached the list fetch but NOT the GROUP BY.
  agent_category_chart:
    source: Ticket
    filter: assigned_to = current_context
    display: bar_chart
    group_by: category
    aggregate:
      count: count(Ticket)
    empty: "No tickets for this agent"

  # 2-hop dotted aggregate (the #1305 core, parallel to #1304's 2-hop list):
  # count of the selected agent's ticket comments, bucketed. The dotted
  # current_context path (Comment -> ticket -> assigned_to) must scope the
  # aggregate query — proving the FK-path `__in_subquery` filter survives the
  # GROUP BY path, not just the list path.
  agent_comment_chart:
    source: Comment
    filter: ticket.assigned_to = current_context
    display: bar_chart
    group_by: is_internal
    aggregate:
      count: count(Comment)
    empty: "No comments for this agent"

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
  # Metrics-first team home (ST-027). Team work queue remains accessible via
  # ticket_queue access: persona(agent, manager). Avoids TR-52 empty personal list.
  default_workspace: manager_ops

# =============================================================================
# SCENARIOS - Testing contexts with demo data
# =============================================================================

scenario happy_path "Happy Path":
  description: "Normal ticket flow - customer submits, agent resolves, customer satisfied"
  as persona customer:
    start_route: "/tickets/new"
  as persona agent:
    start_route: "/queue"

scenario escalation "Escalation Flow":
  description: "Critical issue requiring manager attention and oversight"
  as persona customer:
    start_route: "/tickets"
  as persona agent:
    start_route: "/queue?priority=critical"
  as persona manager:
    # ST-027: metrics-first manager ops (critical queue on the same surface)
    start_route: "/app/workspaces/manager_ops"

scenario backlog "Backlog Scenario":
  description: "High volume testing with many open tickets"
  seed_script: "fixtures/backlog.json"
  as persona agent:
    start_route: "/queue"
  as persona manager:
    start_route: "/app/workspaces/manager_ops"

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
  cadence: "daily"

  # Triage — start of shift: work the open queue, take ownership.
  phase triage:
    kind: active
    cadence: "start of each shift"

    scene scan_queue "Scan the open queue":
      on: ticket_queue
      action: browse
      entity: Ticket
      story: ST-019
      expects: "The unresolved queue is visible and filterable, critical work surfaced first"

    scene pick_up "Pick up a ticket":
      on: ticket_detail
      action: submit
      entity: Ticket
      story: ST-020
      expects: "Agent takes ownership of an open ticket and it moves to in_progress"

  # Resolve — work a ticket to completion, then close it out.
  phase resolve:
    kind: active
    depends_on: triage

    scene review_detail "Read the ticket and its history":
      on: ticket_detail
      action: review
      entity: Ticket
      story: ST-021
      expects: "Full ticket detail with the complete comment history is legible in one place"

    scene add_note "Add an internal note":
      on: comment_create
      action: submit
      entity: Comment
      story: ST-022
      expects: "Agent records an internal working note against the ticket"

    scene resolve_ticket "Resolve the ticket":
      on: ticket_detail
      action: approve
      entity: Ticket
      story: ST-023
      expects: "Agent moves an in_progress ticket to resolved once the fix is confirmed"

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
