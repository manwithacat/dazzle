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
  # Journey: roster row → person overview (not a dead warehouse row)
  open: User via id

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

  section identity "Identity":
    field name "Name"
    field email "Email"

  section role "Role & access":
    layout: strip
    field role "Role"
    field is_active "Active"
    field created_at "Joined"

  related tickets "Tickets":
    display: table
    show: Ticket
    columns: title, status, priority, assigned_to, created_at

  related comments "Comments":
    display: table
    show: Comment
    columns: content, is_internal, created_at

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

surface ticket_list "Tickets":
  uses entity Ticket
  mode: list
  render: fragment
  # Primary drill: ticket context hub (warehouse lists alone are not the product)
  open: Ticket via id
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

  section summary "Summary":
    field ticket_number "Ticket #"
    field title "Title"
    field description "Description"

  section status "Status":
    layout: strip
    field status "Status"
    field priority "Priority"
    field category "Category"

  section people "People":
    field created_by "Created By"
    field assigned_to "Assigned To"

  section resolution "Resolution":
    field resolution "Resolution"
    field created_at "Created"
    field updated_at "Updated"
    field resolved_at "Resolved"

  related discussion "Discussion":
    display: table
    show: Comment
    columns: content, author, is_internal, created_at

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
  open: Ticket via ticket

  ux:
    purpose: "Scan recent comment activity — open hops to the parent ticket hub"
    sort: created_at desc
    filter: is_internal
    search: content
    empty: "No comments yet. Start the conversation."

  section main "Comments":
    field content "Comment"
    field author "Author"
    field is_internal "Internal"
    field ticket "Ticket"
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

# WI L: agent default landing — denser regions (cap 6).
workspace ticket_queue "Ticket Queue":
  purpose: "Agent workspace for managing incoming support tickets"
  stage: "scanner_table"
  access: persona(agent, manager, admin)

  # Job primary: at-a-glance pressure (tones on critical).
  # `summary` is a metrics alias — keep one fleet consumer for coverage gate.
  queue_metrics:
    source: Ticket
    display: summary
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

  critical_now:
    source: Ticket
    filter: priority = critical and status != closed
    sort: created_at asc
    limit: 12
    display: queue
    action: ticket_edit
    empty: "No critical tickets open"

  # Lifecycle board (secondary) — status columns for flow, not the primary worklist.
  ticket_board:
    source: Ticket
    filter: status != closed
    display: kanban
    group_by: status
    action: ticket_edit
    empty: "No open tickets"

  recent_comments:
    source: Comment
    sort: created_at desc
    limit: 12
    display: list
    action: comment_detail
    empty: "No recent comments"

  queue_readiness:
    display: status_list
    entries:
      - title: "Open queue"
        caption: "Work highest priority first — critical surfaces above the board"
        icon: "inbox"
        state: warning
      - title: "SLA clock"
        caption: "First response warning at 2h — see Manager Ops for team SLA strip"
        icon: "clock"
        state: accent


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

  # WI D: context family — recent ticket trail
  recent_trail:
    source: Ticket
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No tickets yet"

  # WI D: kanban family — open pipeline board
  open_board:
    source: Ticket
    filter: status != closed
    display: kanban
    group_by: status
    sort: priority desc
    action: ticket_edit
    empty: "No open tickets"

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

# WI L: customer default landing — denser regions (cap 6).
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

  waiting_on_us:
    source: Ticket
    filter: created_by = current_user and status = in_progress
    sort: updated_at desc
    limit: 10
    display: queue
    action: ticket_detail
    empty: "Nothing currently in progress"

  all_cases:
    source: Ticket
    filter: created_by = current_user
    sort: created_at desc
    display: list
    action: ticket_detail
    empty: "You have not submitted any tickets yet"

  resolved_recent:
    source: Ticket
    filter: created_by = current_user and status = resolved
    sort: updated_at desc
    limit: 10
    display: list
    action: ticket_detail
    empty: "No resolved tickets yet"

  how_it_works:
    display: status_list
    entries:
      - title: "Submit a ticket"
        caption: "Describe the issue — agents pick it up from the open queue"
        icon: "plus-circle"
        state: accent
      - title: "Track status"
        caption: "Open and in-progress cases stay on this desk until closed"
        icon: "list-checks"
        state: positive
      - title: "Replies"
        caption: "Open a case to read agent comments and updates"
        icon: "message-square"
        state: warning

  # WI D: context family — recent updates on my cases
  my_trail:
    source: Ticket
    filter: created_by = current_user
    sort: updated_at desc
    limit: 12
    display: timeline
    action: ticket_detail
    empty: "You have not submitted any tickets yet"

  # WI D: chart family — my tickets by status
  my_status_mix:
    source: Ticket
    filter: created_by = current_user
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "You have not submitted any tickets yet"

  # WI D: grid family — open cases as cards
  open_cards:
    source: Ticket
    filter: created_by = current_user and status != closed
    sort: updated_at desc
    limit: 12
    display: grid
    action: ticket_detail
    empty: "You have no open tickets"


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

  # WI D: queue family — high-priority tickets for selected agent
  agent_priority_queue:
    source: Ticket
    filter: assigned_to = current_context and status != closed
    sort: priority desc, created_at asc
    limit: 15
    display: queue
    action: ticket_edit
    empty: "No open tickets for this agent"

  # WI D: context family — comment trail for selected agent
  agent_comment_trail:
    source: Comment
    filter: ticket.assigned_to = current_context
    sort: created_at desc
    limit: 15
    display: timeline
    action: comment_detail
    empty: "No comments on this agent's tickets"

  # WI D: grid family — open tickets as cards
  agent_ticket_cards:
    source: Ticket
    filter: assigned_to = current_context and status != closed
    sort: priority desc
    limit: 12
    display: grid
    action: ticket_detail
    empty: "No open tickets for this agent"

# Sixth product desk (WI D): 3 lists floor dens ~0.38 with 5 full desks — need 6.
workspace resolution_ops "Resolution Ops":
  purpose: "Resolution pressure — recently resolved and closed tickets without warehouse CRUD"
  access: persona(agent, manager, admin)

  resolution_pulse:
    source: Ticket
    display: metrics
    aggregate:
      resolved: count(Ticket where status = resolved)
      closed: count(Ticket where status = closed)
      open: count(Ticket where status = open or status = in_progress)
    tones:
      resolved: positive
      closed: accent
      open: warning

  # WI D: queue family — resolved awaiting close
  resolved_queue:
    source: Ticket
    filter: status = resolved
    sort: updated_at desc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No tickets in resolved state"

  # WI D: grid family — recently closed cards
  closed_grid:
    source: Ticket
    filter: status = closed
    sort: updated_at desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No closed tickets yet"

  # WI D: context family — resolution trail
  resolution_trail:
    source: Ticket
    filter: status = resolved or status = closed
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No resolved or closed tickets"

  # WI D: chart family — terminal status mix
  status_mix:
    source: Ticket
    filter: status = resolved or status = closed
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No terminal tickets to chart"

# Seventh product desk (WI D): 3 lists floor dens ~0.33 with 6 full desks — need 7.
workspace priority_ops "Priority Ops":
  purpose: "High and critical open ticket pressure without warehouse CRUD"
  access: persona(agent, manager, admin)

  priority_pulse:
    source: Ticket
    display: metrics
    aggregate:
      critical: count(Ticket where priority = critical and status != closed)
      high: count(Ticket where priority = high and status != closed)
      open: count(Ticket where status != closed)
    tones:
      critical: destructive
      high: warning
      open: accent

  # WI D: queue family — critical open first
  critical_queue:
    source: Ticket
    filter: priority = critical and status != closed
    sort: created_at asc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No open critical tickets"

  # WI D: grid family — high-priority cards
  high_grid:
    source: Ticket
    filter: priority = high and status != closed
    sort: created_at asc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open high-priority tickets"

  # WI D: context family — recent priority trail
  priority_trail:
    source: Ticket
    filter: (priority = high or priority = critical) and status != closed
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No high or critical open tickets"

  # WI D: chart family — open work by priority
  priority_mix:
    source: Ticket
    filter: status != closed
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Ticket)
    empty: "No open tickets to chart"

# Eighth product desk (WI D): 3 lists floor dens ~0.30 with 7 full desks — need 8.
workspace progress_ops "Progress Ops":
  purpose: "In-progress pressure — work actively being handled without warehouse CRUD"
  access: persona(agent, manager, admin)

  progress_pulse:
    source: Ticket
    display: metrics
    aggregate:
      in_progress: count(Ticket where status = in_progress)
      open: count(Ticket where status = open)
      resolved: count(Ticket where status = resolved)
    tones:
      in_progress: accent
      open: warning
      resolved: positive

  # WI D: queue family — in-progress first
  progress_queue:
    source: Ticket
    filter: status = in_progress
    sort: priority desc, updated_at asc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No tickets in progress"

  # WI D: grid family — open backlog cards
  open_grid:
    source: Ticket
    filter: status = open
    sort: priority desc, created_at asc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open tickets waiting claim"

  # WI D: context family — recent progress trail
  progress_trail:
    source: Ticket
    filter: status = in_progress or status = open
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No progress activity yet"

  # WI D: chart family — open pipeline status mix
  status_mix:
    source: Ticket
    filter: status != closed
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No open tickets to chart"

# Ninth product desk (WI D): skip invoice_ops desk-cap; densify support_tickets.
workspace open_ops "Open Ops":
  purpose: "Intake pressure — unclaimed open tickets without warehouse CRUD"
  access: persona(agent, manager, admin)

  open_pulse:
    source: Ticket
    display: metrics
    aggregate:
      open: count(Ticket where status = open)
      critical: count(Ticket where priority = critical and status = open)
      high: count(Ticket where priority = high and status = open)
    tones:
      open: warning
      critical: destructive
      high: accent

  # WI D: queue family — open tickets first
  open_queue:
    source: Ticket
    filter: status = open
    sort: priority desc, created_at asc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No open tickets waiting claim"

  # WI D: grid family — open cards
  open_grid:
    source: Ticket
    filter: status = open
    sort: priority desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open tickets waiting claim"

  # WI D: context family — recent open intake trail
  open_trail:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No open intake activity yet"

  # WI D: chart family — priority mix among open
  priority_mix:
    source: Ticket
    filter: status = open
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Ticket)
    empty: "No open tickets to chart"

# Tenth product desk (WI D): skip invoice_ops desk-cap; densify support_tickets.
workspace resolved_ops "Resolved Ops":
  purpose: "Close-out pressure — resolved tickets awaiting final close without warehouse CRUD"
  access: persona(agent, manager, admin)

  resolved_pulse:
    source: Ticket
    display: metrics
    aggregate:
      resolved: count(Ticket where status = resolved)
      closed: count(Ticket where status = closed)
      open: count(Ticket where status = open)
    tones:
      resolved: positive
      closed: muted
      open: warning

  # WI D: queue family — resolved first
  resolved_queue:
    source: Ticket
    filter: status = resolved
    sort: updated_at desc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No resolved tickets waiting close-out"

  # WI D: grid family — resolved cards
  resolved_grid:
    source: Ticket
    filter: status = resolved
    sort: priority desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No resolved tickets waiting close-out"

  # WI D: context family — recent resolve trail
  resolved_trail:
    source: Ticket
    filter: status = resolved or status = closed
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No resolve activity yet"

  # WI D: chart family — priority mix among resolved
  priority_mix:
    source: Ticket
    filter: status = resolved
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Ticket)
    empty: "No resolved tickets to chart"


# Eleventh product desk (WI D): skip invoice/fieldtest/acme soft-cap; densify support_tickets.
workspace critical_ops "Critical Ops":
  purpose: "Critical/high priority pressure without warehouse CRUD"
  access: persona(agent, manager, admin)

  critical_pulse:
    source: Ticket
    display: metrics
    aggregate:
      critical: count(Ticket where priority = critical)
      high: count(Ticket where priority = high)
      open: count(Ticket where status = open or status = in_progress)
    tones:
      critical: warning
      high: accent
      open: muted

  # WI D: queue family — critical/high first
  critical_queue:
    source: Ticket
    filter: priority = critical or priority = high
    sort: priority desc, updated_at desc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No high-priority tickets"

  # WI D: grid family — critical cards
  critical_grid:
    source: Ticket
    filter: priority = critical or priority = high
    sort: priority desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No high-priority tickets"

  # WI D: context family — recent critical trail
  critical_trail:
    source: Ticket
    filter: priority = critical or priority = high
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No high-priority activity yet"

  # WI D: chart family — status mix among high priority
  status_mix:
    source: Ticket
    filter: priority = critical or priority = high
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No high-priority tickets to chart"


# Twelfth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify support_tickets.
workspace unassigned_ops "Unassigned Ops":
  purpose: "Assignment pressure — open tickets without an owner without warehouse CRUD"
  access: persona(agent, manager, admin)

  unassigned_pulse:
    source: Ticket
    display: metrics
    aggregate:
      unassigned: count(Ticket where assigned_to = null and status = open)
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
    tones:
      unassigned: warning
      open: accent
      in_progress: muted

  # WI D: queue family — unassigned open first
  unassigned_queue:
    source: Ticket
    filter: assigned_to = null and status = open
    sort: priority desc, updated_at desc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No unassigned open tickets"

  # WI D: grid family — unassigned cards
  unassigned_grid:
    source: Ticket
    filter: assigned_to = null and status = open
    sort: priority desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No unassigned open tickets"

  # WI D: context family — recent unassigned trail
  unassigned_trail:
    source: Ticket
    filter: assigned_to = null and status = open
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No unassigned activity yet"

  # WI D: chart family — priority mix among unassigned
  priority_mix:
    source: Ticket
    filter: assigned_to = null and status = open
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Ticket)
    empty: "No unassigned tickets to chart"


# Thirteenth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify support_tickets.
workspace bug_ops "Bug Ops":
  purpose: "Bug-category pressure — open defects without warehouse CRUD"
  access: persona(agent, manager, admin)

  bug_pulse:
    source: Ticket
    display: metrics
    aggregate:
      bugs: count(Ticket where category = bug and status != closed)
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
    tones:
      bugs: warning
      open: accent
      in_progress: muted

  # WI D: queue family — open bugs first
  bug_queue:
    source: Ticket
    filter: category = bug and status != closed
    sort: priority desc, updated_at desc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No open bug tickets"

  # WI D: grid family — bug cards
  bug_grid:
    source: Ticket
    filter: category = bug and status != closed
    sort: priority desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open bug tickets"

  # WI D: context family — recent bug trail
  bug_trail:
    source: Ticket
    filter: category = bug and status != closed
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No bug activity yet"

  # WI D: chart family — priority mix among bugs
  priority_mix:
    source: Ticket
    filter: category = bug and status != closed
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Ticket)
    empty: "No bug tickets to chart"


# Fourteenth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify support_tickets.
workspace feature_ops "Feature Ops":
  purpose: "Feature-request pressure — open feature tickets without warehouse CRUD"
  access: persona(agent, manager, admin)

  feature_pulse:
    source: Ticket
    display: metrics
    aggregate:
      features: count(Ticket where category = feature and status != closed)
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
    tones:
      features: accent
      open: warning
      in_progress: muted

  # WI D: queue family — open features first
  feature_queue:
    source: Ticket
    filter: category = feature and status != closed
    sort: priority desc, updated_at desc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No open feature tickets"

  # WI D: grid family — feature cards
  feature_grid:
    source: Ticket
    filter: category = feature and status != closed
    sort: priority desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open feature tickets"

  # WI D: context family — recent feature trail
  feature_trail:
    source: Ticket
    filter: category = feature and status != closed
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No feature activity yet"

  # WI D: chart family — priority mix among features
  priority_mix:
    source: Ticket
    filter: category = feature and status != closed
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Ticket)
    empty: "No feature tickets to chart"


# Fifteenth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify support_tickets.
workspace inquiry_ops "Inquiry Ops":
  purpose: "Inquiry-category pressure — open questions without warehouse CRUD"
  access: persona(agent, manager, admin)

  inquiry_pulse:
    source: Ticket
    display: metrics
    aggregate:
      inquiries: count(Ticket where category = inquiry and status != closed)
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
    tones:
      inquiries: accent
      open: warning
      in_progress: muted

  # WI D: queue family — open inquiries first
  inquiry_queue:
    source: Ticket
    filter: category = inquiry and status != closed
    sort: priority desc, updated_at desc
    limit: 20
    display: queue
    action: ticket_edit
    empty: "No open inquiry tickets"

  # WI D: grid family — inquiry cards
  inquiry_grid:
    source: Ticket
    filter: category = inquiry and status != closed
    sort: priority desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open inquiry tickets"

  # WI D: context family — recent inquiry trail
  inquiry_trail:
    source: Ticket
    filter: category = inquiry and status != closed
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No inquiry activity yet"

  # WI D: chart family — priority mix among inquiries
  priority_mix:
    source: Ticket
    filter: category = inquiry and status != closed
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Ticket)
    empty: "No inquiry tickets to chart"

# =============================================================================
# PERSONAS - User archetypes for testing
# =============================================================================

persona admin "Administrator":
  # Product admin lands on the work queue — not framework platform chrome (#1626).
  default_workspace: ticket_queue
  uses nav admin_nav

persona customer "Customer":
  description: "End user submitting support requests and tracking their status"
  goals: "Submit new tickets easily", "Track ticket status and updates", "Receive timely responses from support"
  proficiency: novice
  default_workspace: my_tickets
  # WI N: job desks first — not auto entity-list soup
  uses nav customer_nav

persona agent "Support Agent":
  description: "First-line support handling incoming tickets"
  goals: "Process tickets efficiently", "Maintain SLA compliance", "Escalate complex issues to managers"
  proficiency: intermediate
  default_workspace: ticket_queue
  uses nav agent_nav

persona manager "Support Manager":
  description: "Team lead monitoring performance and handling escalations"
  goals: "Monitor team metrics and performance", "Identify bottlenecks in ticket flow", "Ensure quality and customer satisfaction"
  proficiency: expert
  # Metrics-first team home (ST-027). Team work queue remains accessible via
  # ticket_queue access: persona(agent, manager). Avoids TR-52 empty personal list.
  default_workspace: manager_ops
  uses nav manager_nav

# Curated sidebars: workspace destinations only (WI primary N).
# Names must match workspace ids — validate warns on orphans.
nav admin_nav:
  group "Ops":
    ticket_queue
    agent_console
    resolution_ops
    priority_ops
    progress_ops
    open_ops
    resolved_ops
    critical_ops
    unassigned_ops
    bug_ops
    feature_ops
    inquiry_ops

nav customer_nav:
  group "My support":
    my_tickets

nav agent_nav:
  group "Work":
    ticket_queue
    agent_dashboard
    agent_console
    resolution_ops
    priority_ops
    progress_ops
    open_ops
    resolved_ops
    critical_ops
    unassigned_ops
    bug_ops
    feature_ops
    inquiry_ops

nav manager_nav:
  group "Lead":
    manager_ops
    ticket_queue
    agent_console
    agent_dashboard
    resolution_ops
    priority_ops
    progress_ops
    open_ops
    resolved_ops
    critical_ops
    unassigned_ops
    bug_ops
    feature_ops
    inquiry_ops

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
