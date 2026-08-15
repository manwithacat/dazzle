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
  # Goal B org_structure (cycle 1847): department placement so manager People
  # desk shows Support / Escalations / Billing shape — not a flat role-only roster.
  department: str(50)
  # Goal B org_structure peer-pack (cycle 2056): support_tier_density —
  # Zendesk/Front route by L1 frontline vs L2 escalation vs L3 lead, not only
  # role+dept dual kanban (decorative Team desk clone refuse in peer pack).
  support_tier: enum[l1,l2,l3]=l1
  # Goal B media (cycle 1883): peer support tools (Zendesk / Intercom / Front)
  # put agent headshot thumbs on queue/ops homes — not name-only roster theater.
  photo_url: url
  is_active: bool = true
  created_at: datetime auto_add

  # Invariant: users must have valid role
  invariant: role != null

  fitness:
    # Cycle 1933 agent_acceptance: agent media shelves / people queues show
    # identity chips (name/role/dept) — not Photo Url / Email / Is Active
    # schema dump (peer simple_task 1925/1928, contact_manager 1931).
    # photo_url still media-injects; email/is_active stay on list/detail.
    # Cycle 2056: support_tier on chips for routing reassignment clarity.
    repr_fields: [name, role, department, support_tier]

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
  # Goal B command_density peer-pack (cycle 1913): Zendesk/Front/Intercom
  # manager dens surface first-response SLA pressure on work rows — not only
  # priority labels or a static readiness caption strip.
  sla_state: enum[on_track,at_risk,breached]=on_track
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
    # ticket_number first — queue/list identity (AAA-001) must survive fitness
    # projection and agent_console 1-hop scoping asserts (#1304 / cycle 1926).
    repr_fields: [ticket_number, title, status, priority, sla_state, category, assigned_to]

  index status, priority
  index sla_state
  index created_by
  index assigned_to

# Comment entity with internal note support
entity Comment "Comment":
  intent: "Enable threaded communication on tickets with internal notes for agents"
  domain: support
  patterns: audit_trail, messaging
  # Goal B: queue/timeline labels must show thread copy (not id/UUID theater)
  display_field: content

  id: uuid pk
  ticket: ref Ticket required
  author: ref User required
  content: text required pii(category=freeform)
  # Goal B conversation peer-pack (cycle 1902): Zendesk/Front/Intercom
  # trails surface customer tone so agents lean into frustrated/urgent speech.
  customer_tone: enum[neutral,frustrated,urgent,thankful]=neutral
  # Peer-pack upgrade (cycle 1907): channel + escalation on the trail —
  # agents see how the speech arrived and whether it was raised past SLA.
  channel: enum[portal,email,chat,phone]=portal
  escalation: enum[none,raised,critical]=none
  # Peer-pack upgrade (cycle 1922): Front / Intercom "needs reply" grain —
  # ball_in_court says who must speak next (not tone/channel meta alone).
  ball_in_court: enum[agent,customer,none]=none
  # Cycle 2036: denormalized ticket SLA pressure on the note so metrics/regions
  # can filter without dotted aggregate paths (ticket.sla_state unsupported in count).
  sla_pressure: enum[none,at_risk,breached]=none
  # Cycle 2040: denormalized ticket priority on the note so conversation metrics
  # can filter high/critical work waiting on agents without dotted Ticket.priority paths.
  case_priority: enum[low,medium,high,critical]=medium
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
    repr_fields: [ticket, author, content, customer_tone, channel, escalation, ball_in_court, sla_pressure, case_priority, is_internal]

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
    filter: role, department, is_active
    search: email, name
    empty: "No users found. Invite team members to get started."

  section main "Users":
    field photo_url "Photo"
    field email "Email"
    field name "Name"
    field role "Role"
    field department "Department"
    field support_tier "Tier"
    field is_active "Active"
    field created_at "Created"

surface user_detail "User Detail":
  uses entity User
  mode: view
  render: fragment

  section identity "Identity":
    field photo_url "Photo"
    field name "Name"
    field email "Email"
    field department "Department"
    field support_tier "Tier"

  section role "Role & access":
    layout: strip
    field role "Role"
    field is_active "Active"
    field created_at "Joined"

  # User hub pull queue (RelatedDisplayMode.QUEUE) — title-first triage roster,
  # not a warehouse table (cycle 1501 story_walk / ST-021 path).
  related tickets "Tickets":
    display: queue
    show: Ticket
    columns: title, status, priority, sla_state, assigned_to, created_at

  # Goal B conversation (cycle 1899 hub wave): user hub comments use
  # RelatedDisplayMode.conversation → Message/Bubble chrome (ticket hub
  # live_conversation parity). is_internal maps orientation only.
  related comments "Comments":
    display: conversation
    show: Comment
    columns: content, customer_tone, channel, escalation, ball_in_court, sla_pressure, case_priority, is_internal, created_at

surface user_create "Create User":
  uses entity User
  mode: create
  render: fragment

  section main "New User":
    field email "Email"
    field name "Name"
    field role "Role"
    field department "Department"
    field support_tier "Support Tier"
    field photo_url "Photo URL"

surface user_edit "Edit User":
  uses entity User
  mode: edit
  render: fragment

  section main "Edit User":
    field email "Email"
    field name "Name"
    field role "Role"
    field department "Department"
    field support_tier "Support Tier"
    field photo_url "Photo URL"
    # HM Switch — boolean settings / account on-off (hyperpart auto_seed drain)
    field is_active "Active" widget=switch

# ============================================================================
# TICKET SURFACES
# ============================================================================

surface ticket_list "Tickets":
  uses entity Ticket
  mode: list
  render: fragment
  # Triple open (journey_dogfood dig cycle 1591): ticket hub first for triage;
  # assignee hub for reassignment / load; creator hub for customer/context (ST-019/028).
  open: Ticket via id | User via assigned_to | User via created_by
  # Row peek opens the ticket in a slide-over drawer (HM drawer
  # Hyperpart) instead of the default inline expand — the queue keeps
  # its scan position while an agent glances at a ticket.
  peek: slide_over

  ux:
    purpose: "Triage and resolve incoming support tickets — open a row for the ticket, assignee, or creator hub"
    sort: created_at desc
    filter: status, priority, category, sla_state
    search: ticket_number, title
    empty: "No support tickets. All clear!"

  section main "Support Tickets":
    field ticket_number "Ticket #"
    field title "Title"
    field status "Status"
    field priority "Priority"
    field sla_state "SLA"
    field category "Category"
    field assigned_to "Assigned To"
    field created_by "Created By"
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
    field sla_state "SLA"
    field category "Category"

  section people "People":
    field created_by "Created By"
    field assigned_to "Assigned To"

  section resolution "Resolution":
    field resolution "Resolution"
    field created_at "Created"
    field updated_at "Updated"
    field resolved_at "Resolved"

  # Goal B conversation (cycle 1893): ticket hub discussion uses
  # RelatedDisplayMode.conversation → Message/Bubble chrome (workspace
  # live_conversation parity). is_internal maps orientation only — not
  # meta thrash (peer Zendesk/Front/Intercom content-first trail).
  related discussion "Discussion":
    display: conversation
    show: Comment
    # customer_tone + escalation → Bubble danger; channel labels the path;
    # ball_in_court shows who must reply next (Front / Intercom needs-reply).
    columns: content, author, customer_tone, channel, escalation, ball_in_court, sla_pressure, case_priority, created_at, is_internal

  # Goal B document: named SLA waivers / breach letters on the ticket hub
  # (peer Zendesk/Service Cloud document trail — not queue-only theater).
  related waivers "SLA waivers":
    display: queue
    show: SlaWaiver
    columns: breach_summary, status, signatory_name

  ux:
    purpose: "Ticket hub — Message-chrome discussion with tone, channel, escalation, needs-reply ball, and named SLA waiver documents"

surface ticket_create "Create Ticket":
  uses entity Ticket
  mode: create
  render: fragment

  section summary "Summary":
    field title "Title"
    field description "Description"

  section triage "Triage":
    field priority "Priority"
    field sla_state "SLA"
    field category "Category"
    field assigned_to "Assigned To"

  ux:
    as customer:
      hide: assigned_to, sla_state

surface ticket_edit "Edit Ticket":
  uses entity Ticket
  mode: edit
  render: fragment

  section summary "Summary":
    field title "Title"
    field description "Description"

  section triage "Triage":
    field priority "Priority"
    field sla_state "SLA"
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
  # Triple open (cycle 1604 story_walk): note hub + parent Ticket + author
  # User (ST-018/021/022 trail — agent sees who wrote the note).
  open: Comment via id | Ticket via ticket | User via author

  ux:
    purpose: "Scan recent comment activity — open hops to the note, parent ticket, or author"
    sort: created_at desc
    filter: is_internal, ball_in_court
    search: content
    empty: "No comments yet. Start the conversation."

  section main "Comments":
    field content "Comment"
    field author "Author"
    field customer_tone "Tone"
    field channel "Channel"
    field escalation "Escalation"
    field ball_in_court "Ball in court"
    field sla_pressure "SLA pressure"
    field case_priority "Case priority"
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
    field customer_tone "Tone"
    field channel "Channel"
    field escalation "Escalation"
    field ball_in_court "Ball in court"
    field sla_pressure "SLA pressure"
    field case_priority "Case priority"
    field is_internal "Internal"
    field created_at "Created"

surface comment_create "Create Comment":
  uses entity Comment
  mode: create
  render: fragment

  section main "New Comment":
    field ticket "Ticket"
    field content "Comment"
    field customer_tone "Customer tone"
    field channel "Channel"
    field escalation "Escalation"
    field ball_in_court "Ball in court"
    field sla_pressure "SLA pressure"
    field case_priority "Case priority"
    # HM Switch — internal note flag (settings-like boolean; not toggle mode press)
    field is_internal "Internal" widget=switch

  ux:
    as customer:
      hide: is_internal, escalation, ball_in_court

surface comment_edit "Edit Comment":
  uses entity Comment
  mode: edit
  render: fragment

  section main "Edit Comment":
    field content "Comment"
    field customer_tone "Customer tone"
    field channel "Channel"
    field escalation "Escalation"
    field ball_in_court "Ball in court"
    field sla_pressure "SLA pressure"
    field case_priority "Case priority"
    # HM Switch — internal note flag (settings-like boolean)
    field is_internal "Internal" widget=switch

  ux:
    as customer:
      hide: is_internal, escalation, ball_in_court

# =============================================================================
# WORKSPACES - Composed views with stages
# =============================================================================

# Story-driven compositions (docs/guides/story-to-composition.md):
#   agent  → ticket_queue  = metrics + queue + kanban  (ST-019–023)
#   manager → manager_ops  = metrics + SLA strip + focused queues (ST-027–029)
#   customer → my_tickets  = my metrics + open queue + history (ST-024–026)

workspace ticket_queue "Ticket Queue":
  # Goal B media (cycle 1883) + conversation + document: peer support tools
  # (Zendesk / Intercom / Front) put agent headshots, live thread copy, and
  # named waiver documents on the triage home — not only ticket rows.
  purpose: "Team headshots, needs-reply ball, live trail, and SLA waiver documents"
  stage: "scanner_table"
  access: persona(agent, manager, admin)

  # Goal B media FIRST — triage home is a people shelf (agent photo_url thumbs).
  # Sort newest first so seed-only roster (non-STABLE #1630) with placehold
  # headshots win the fold — STABLE mirror users skip User.jsonl re-seed.
  media_shelf:
    source: User
    # Department-placed staff only — drops trial-parent seed noise and bare
    # auth shells without org placement (Goal B media shelf is a people desk).
    filter: is_active = true and department != null
    display: grid
    sort: created_at desc
    limit: 4
    action: user_detail
    empty: "No agent headshots yet — add photo URLs on team users"

  # Job primary: at-a-glance pressure (tones on critical).
  # Cycle 2077 distill: keep needs_reply + live_conversation (Goal C honest grain).
  queue_metrics:
    source: Ticket
    display: summary
    aggregate:
      total_open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      critical: count(Ticket where priority = critical and status != closed)
      conversation: count(Comment)
      needs_reply: count(Comment where ball_in_court = agent)
      documents: count(SlaWaiver)
    tones:
      in_progress: accent
      critical: destructive
      conversation: accent
      needs_reply: warning
      documents: accent
  # Peer-pack needs_reply_ball (cycle 1922): Front / Intercom "waiting on you"
  # — customer speech that still needs an agent reply, above the live trail.
  needs_reply:
    source: Comment
    filter: ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "Nothing waiting on agents — every customer note has a reply path"
  live_conversation:
    source: Comment
    sort: created_at desc
    limit: 10
    display: conversation
    action: comment_detail
    empty: "No conversation yet — customer and agent notes appear here as the case moves"

  # Goal B document composition — named waiver / breach titles above the fold
  # (display_field: breach_summary), not UUID shells or empty document chrome.
  composition:
    source: SlaWaiver
    filter: status = draft or status = sent
    sort: breach_summary asc
    limit: 8
    display: queue
    action: sla_waiver_detail
    empty: "No open SLA waivers — draft a named waiver after a response-time breach"

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

  # Work-surface utility: dated comment stream → timeline (time_order), not row list.
  recent_comments:
    source: Comment
    sort: created_at desc
    limit: 12
    display: timeline
    action: comment_detail
    empty: "No recent comments"
  queue_readiness:
    display: status_list
    entries:
      - title: "Needs reply"
        caption: "Customer notes with ball in agent court — answer before the rest of the trail"
        icon: "reply"
        state: warning
      - title: "Live conversation"
        caption: "Newest customer and agent notes — open a row for the note, ticket, or author"
        icon: "message-square"
        state: accent
      - title: "Open queue"
        caption: "Work highest priority first — critical surfaces above the board"
        icon: "inbox"
        state: warning
      - title: "SLA clock"
        caption: "First response warning at 2h — see Manager Ops for team SLA strip"
        icon: "clock"
        state: accent
  ux:
    as agent:
      purpose: "Triage home — needs-reply ball + live trail"
      focus: media_shelf, queue_metrics, needs_reply, live_conversation
    as manager:
      purpose: "Triage home — needs-reply ball + live trail"
      focus: media_shelf, queue_metrics, needs_reply, live_conversation
    as admin:
      purpose: "Triage home — needs-reply ball + live trail"
      focus: media_shelf, queue_metrics, needs_reply, live_conversation


workspace manager_ops "Manager Ops":
  # ST-027 team performance + SLA narrative; critical/unassigned queues for
  # ST-028/029. TR-52 moved managers off empty personal assigned lists — this
  # is the metrics-first home that matches the story.
  # Goal B media (cycle 1883): agent headshot shelf first — peer Zendesk /
  # Intercom / Front put faces on the ops home before pressure tiles.
  # Goal B conversation (cycle 1720): live thread volume on the command home.
  # Goal B command_density (cycle 1727): dual attention (critical + unassigned)
  # shares the fold with capped conversation — peer Zendesk/Intercom manager
  # homes are multi-panel pressure, not conversation-only above the fold.
  # Goal B document (cycle 1798): named SLA waiver composition after dual
  # attention, before conversation — peer Service Cloud breach-letter trail.
  # Goal B command_density peer upgrade (cycle 1913): live sla_state pressure
  # (at_risk / breached) on metrics + a breach_risk queue — not static caption
  # theater alone (recipe sla_breach_pressure; not headshot_shelf).
  # Goal B command_density peer upgrade (cycle 2054): split combined breach_risk
  # into soft at-risk vs hard breached stage queues (recipe sla_stage_density;
  # peer Zendesk/Front SLA stage boards — not one mixed pressure list, not
  # critical/unassigned dual_attention re-stack alone, not conversation tile thrash).
  # Goal B command_density peer upgrade (cycle 2070): exclusive open vs
  # in_progress lifecycle stage boards (recipe status_stage_density; peer
  # Zendesk/Front status views — not sla_stage_density re-stack, not
  # critical/unassigned dual_attention alone, not conversation trail thrash).
  purpose: "Multi-panel support ops — headshots, status/SLA stages, dual queues, needs-reply ball, waiver documents, live conversation"
  stage: "command_center"
  access: persona(manager)

  # Goal B media FIRST — manager home is a people shelf (agent photo_url thumbs).
  # Newest-first so non-STABLE seeded agents (Riley/Sam/Jordan + placeholds)
  # outrank STABLE auth-mirrored rows that skip User.jsonl photo_url (#1630).
  media_shelf:
    source: User
    # Department-placed staff only — drops trial-parent seed noise and bare
    # auth shells without org placement (Goal B media shelf is a people desk).
    # Cap 3 (cycle 1913): leave fold share for SLA breach pressure + dual queues.
    filter: is_active = true and department != null
    display: grid
    sort: created_at desc
    limit: 3
    action: user_detail
    empty: "No agent headshots yet — add photo URLs on team users"

  team_metrics:
    source: Ticket
    display: metrics
    aggregate:
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      critical_open: count(Ticket where priority = critical and status != closed)
      unassigned: count(Ticket where assigned_to = null and status = open)
      at_risk: count(Ticket where sla_state = at_risk and status != closed)
      breached: count(Ticket where sla_state = breached and status != closed)
      resolved: count(Ticket where status = resolved)
      conversation: count(Comment)
      needs_reply: count(Comment where ball_in_court = agent)
      documents: count(SlaWaiver)
    tones:
      in_progress: accent
      critical_open: destructive
      unassigned: warning
      at_risk: warning
      breached: destructive
      resolved: positive
      conversation: accent
      needs_reply: warning
      documents: accent
  # Live status stage density (cycle 2070) — peer Zendesk/Front put exclusive
  # open (intake) vs in_progress (active work) boards before SLA stages and
  # priority dual attention (recipe status_stage_density; not sla_stage_density
  # re-stack, not critical/unassigned dual_attention alone). Caps keep stage
  # panels + dual queues + composition sharing the fold.
  open_stage_queue:
    source: Ticket
    filter: status = open
    sort: priority desc, created_at asc
    limit: 4
    display: queue
    action: ticket_edit
    empty: "No open tickets — intake is empty or everything is already in progress"

  in_progress_stage_queue:
    source: Ticket
    filter: status = in_progress
    sort: priority desc, created_at asc
    limit: 4
    display: queue
    action: ticket_edit
    empty: "No in-progress tickets — nothing is actively owned yet"

  # Live SLA stage density (cycle 2054) — peer Zendesk/Front put soft at-risk
  # vs hard breached as separate boards before priority dual attention (not one
  # mixed breach_risk list; recipe sla_stage_density). Caps keep stage panels
  # + critical/unassigned + composition sharing the fold.
  at_risk_queue:
    source: Ticket
    filter: sla_state = at_risk and status != closed
    sort: created_at asc
    limit: 4
    display: queue
    action: ticket_edit
    empty: "No at-risk tickets — first-response SLA is still on track"

  breached_queue:
    source: Ticket
    filter: sla_state = breached and status != closed
    sort: created_at asc
    limit: 4
    display: queue
    action: ticket_edit
    empty: "No breached tickets — response-time failures land here for waiver / recovery"

  # Static readiness strip — pairs with sla TicketResponseTime commitment.
  sla_readiness:
    display: status_list
    entries:
      - title: "Ticket response SLA"
        caption: "Warning 2h · breach 4h · critical 8h (business hours)"
        icon: "clock"
        state: accent
      - title: "Status stage density"
        caption: "Open intake vs in-progress active work as exclusive stage boards before SLA pressure"
        icon: "layout-list"
        state: accent
      - title: "SLA stage density"
        caption: "Soft at-risk vs hard breached queues surface before priority dual attention"
        icon: "timer"
        state: warning
      - title: "Critical open"
        caption: "Priority critical tickets must stay assigned and progressing"
        icon: "triangle-alert"
        state: warning
      - title: "Unassigned open"
        caption: "Open tickets with no assignee block first response"
        icon: "user"
        state: warning
      - title: "SLA waiver documents"
        caption: "Named breach letters and credit memos live in composition — open a row for the waiver hub"
        icon: "file-text"
        state: accent

  # Dual attention (ST-028/029) — cap for fold share with conversation.
  # Unbounded queues + row hx-preload storm browser under pilot scroll.
  critical_queue:
    source: Ticket
    filter: priority = critical and status != closed
    sort: created_at asc
    limit: 4
    display: queue
    action: ticket_edit
    empty: "No critical tickets open"

  unassigned_queue:
    source: Ticket
    filter: assigned_to = null and status = open
    sort: priority desc, created_at asc
    limit: 4
    display: queue
    action: ticket_edit
    empty: "Every open ticket has an assignee"

  # Goal B document composition AFTER dual attention — named waiver titles
  # (breach_summary) so manager stills show document body, not only queues.
  composition:
    source: SlaWaiver
    filter: status = draft or status = sent
    sort: breach_summary asc
    limit: 4
    display: queue
    action: sla_waiver_detail
    empty: "No open SLA waivers — draft a named waiver after a response-time breach"

  # Peer-pack needs_reply_ball (cycle 1922) — manager sees who is waiting on
  # agents before the mixed conversation trail (Front / Intercom grain).
  needs_reply:
    source: Comment
    filter: ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No customer notes waiting on agents"
  live_conversation:
    source: Comment
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No conversation yet — customer and agent notes appear here as cases move"

  ux:
    as manager:
      purpose: "Multi-panel support ops — status/SLA stages, dual queues, needs-reply, live conversation"
      focus: media_shelf, team_metrics, open_stage_queue, in_progress_stage_queue, at_risk_queue, breached_queue, critical_queue, unassigned_queue, needs_reply, live_conversation

  # Goal B empty_region_honesty (cycle 1850) + acceptance dig 20260810:
  # funnel_chart + ticket timeline below the fold still lazy-fetched every
  # Manager Ops load and stacked with dual queues / composition / conversation
  # under pilot scroll → browser ERR_INSUFFICIENT_RESOURCES + htmx Failed to
  # fetch (recommend=unclear, ownership=harness). Peer manager homes (Zendesk /
  # Intercom) keep pressure panels above the fold — not status funnel theater
  # or a second ticket trail after live_conversation. Lifecycle kanban stays
  # on agent_dashboard; funnel_chart coverage lives on agent_console.


workspace agent_dashboard "Agent Dashboard":
  # Personal agent view (assigned work + conversation). Manager team home is
  # manager_ops; agents keep this for "my WIP" after claiming from the queue.
  # Goal B empty_region_honesty (cycle 1812): peer agent homes (Zendesk /
  # Intercom) lead with WIP board + close-out + one comment trail — not funnel
  # / progress chart theater or triple comment streams that render as voids.
  purpose: "Personal WIP board with needs-reply ball and awaiting-customer park on claimed cases"
  stage: "dual_pane_flow"
  access: persona(agent, manager)

  # ── Work first: personal WIP board + close-out queue ────────────────
  # HMC-065 / work_surface_utility: stage movement is the agent job after
  # claim — kanban (group_by status) beats a single-status list for
  # state_progress. Filter spans open lifecycle (not only in_progress) so
  # columns are non-empty; closed stays off-board.
  my_assigned:
    source: Ticket
    filter: assigned_to = current_user and status != closed
    sort: priority desc
    limit: 24
    display: kanban
    group_by: status
    action: ticket_edit
    empty: "No tickets assigned to you"

  # Peer-pack needs_reply_ball — my plate of customer speech waiting on me.
  needs_reply:
    source: Comment
    filter: ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No customer notes waiting on you — clear the ball before new claims"
  awaiting_customer:
    source: Comment
    filter: ball_in_court = customer and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "Nothing waiting on customers from this desk"
  my_conversation:
    source: Comment
    sort: created_at desc
    limit: 8
    display: queue
    action: comment_detail
    empty: "No notes on the trail yet — replies land here as customers write back"

  # Resolved-only close-out — urgency/next-action, not multi-stage ceremony.
  pending_resolution:
    source: Ticket
    filter: assigned_to = current_user and status = resolved
    sort: updated_at desc
    limit: 8
    display: queue
    action: ticket_detail
    empty: "No tickets pending closure"

  # Single comment trail (no empty chart theater / triple activity dumps).
  recent_comments:
    source: Comment
    sort: created_at desc
    limit: 10
    display: timeline
    action: comment_detail
    empty: "No recent comments"

  ux:
    as agent:
      purpose: "Personal WIP + needs-reply + awaiting customer — no funnel theater"
      focus: my_assigned, needs_reply, awaiting_customer, pending_resolution
    as manager:
      purpose: "Personal WIP + needs-reply + awaiting customer — no funnel theater"
      focus: my_assigned, needs_reply, awaiting_customer, pending_resolution

workspace my_tickets "My Tickets":
  # Goal B empty_region_honesty (cycle 1812): customer portal peers show
  # status counts + open cases + one history — not bar-chart theater or
  # duplicate open/timeline dumps that leave large empty voids.
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

  # One chronological case history — not twin timelines + bar chart theater.
  all_cases:
    source: Ticket
    filter: created_by = current_user
    sort: created_at desc
    display: timeline
    action: ticket_detail
    empty: "You have not submitted any tickets yet"

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

  ux:
    as customer:
      purpose: "Open cases and one history — no bar-chart theater or twin dumps"
      focus: my_summary, open_cases, waiting_on_us, all_cases, how_it_works


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
    # Goal B empty_region_honesty (cycle 2086): recipe agent_only_selector —
    # Zendesk/Front inspector pickers list frontline staff, not customer
    # requesters. `role = …` is reserved for role() checks; staff grain is
    # department != External (same as People desk). L1 so the name-sorted
    # default is Alex Agent's filled plate, not Admin's empty one.
    filter: support_tier = l1 and department != External

  # 1-hop: tickets directly assigned to the selected agent.
  # Work-surface utility: assigned open work is a pull queue ranked by priority.
  agent_tickets:
    source: Ticket
    filter: assigned_to = current_context
    sort: priority desc
    display: queue
    action: ticket_detail
    empty: "No tickets assigned to this agent"

  # 2-hop dotted (the #1304 case): comments on tickets assigned to the
  # selected agent — Comment -> ticket -> assigned_to.
  # Work-surface utility: dated comment stream → timeline (time_order).
  agent_ticket_comments:
    source: Comment
    filter: ticket.assigned_to = current_context
    sort: created_at desc
    display: timeline
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

  # Open work pull queue (product surface). #1304 keeps agent_tickets (all
  # statuses) for 1-hop e2e; this open-only edit queue is the manager/agent
  # desk — not a twin card dump of the same open plate.
  agent_priority_queue:
    source: Ticket
    filter: assigned_to = current_context and status != closed
    sort: priority desc, created_at asc
    limit: 15
    display: queue
    action: ticket_edit
    empty: "No open tickets for this agent"

  # Framework artefact coverage dogfood (cycle 1813): display: progress +
  # activity_feed live under context_selector scope — not on agent_dashboard
  # hero (empty_region honesty). Proves GROUP BY / feed re-scope with
  # current_context like the #1305 bar charts above.
  agent_lifecycle_progress:
    source: Ticket
    filter: assigned_to = current_context
    display: progress
    group_by: status
    empty: "No tickets for this agent"

  agent_comment_activity:
    source: Comment
    filter: ticket.assigned_to = current_context
    display: activity_feed
    sort: created_at desc
    limit: 15
    empty: "No comments for this agent"

  # Cycle 1850: host display: funnel_chart here after pruning Manager Ops
  # status-funnel theater (empty_region honesty + pilot resource storm).
  # Same current_context re-scope pattern as progress / bar charts above.
  agent_status_funnel:
    source: Ticket
    filter: assigned_to = current_context
    display: funnel_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No tickets for this agent"

  # Goal B empty_region_honesty (cycle 2067): recipe agent_console_twin_queue_prune
  # — drop twin open-ticket cards + twin comment timeline (agent_ticket_cards /
  # agent_comment_trail). Peer Zendesk/Front agent inspectors show one open
  # plate + one trail under the people selector, not triple ticket dumps or
  # dual timelines that scroll as empty theater. #1304/#1305 keep agent_tickets
  # + agent_ticket_comments + bar/progress/funnel coverage below fold.
  # Cycle 2086 agent_only_selector: L1 + not External so the default first
  # option is a frontline plate (not Trial parent / Admin voids).
  ux:
    as manager:
      purpose: "One open plate + one comment trail under agent selector — no twin dumps"
      focus: agent_priority_queue, agent_ticket_comments, agent_lifecycle_progress, agent_category_chart
    as agent:
      purpose: "One open plate + one comment trail under agent selector — no twin dumps"
      focus: agent_priority_queue, agent_ticket_comments, agent_lifecycle_progress, agent_category_chart
    as admin:
      purpose: "One open plate + one comment trail under agent selector — no twin dumps"
      focus: agent_priority_queue, agent_ticket_comments, agent_lifecycle_progress, agent_category_chart

# Goal B org_structure (cycle 1847 + 2056): peer support tools (Zendesk /
# Front / Intercom) show L1 frontline vs L2 escalation people density for
# routing reassignment, then department placement — not a flat warehouse
# roster or decorative role+dept-only Team desk clone (peer pack refuse).
workspace people_desk "People":
  # Cycle 2052 empty_region: people_desk_roster_twin_prune (no third flat roster).
  # Cycle 2056 org_structure peer-pack: recipe support_tier_density —
  # exclusive L1 frontline vs L2 escalation people queues above fold.
  # Cycle 2073 org_structure peer-pack: recipe l3_lead_density — exclusive L3
  # lead queue paired with L1 above fold (Zendesk/Front/Service Cloud ladder;
  # not L1/L2-only re-stack, not department kanban alone, not twin roster).
  # Cycle 2093 org_structure peer-pack: recipe billing_escalations_seat —
  # exclusive Billing vs Escalations routing groups above fold (Zendesk group
  # queues). Not another L1/L2/L3 restack; not a decorative Team desk clone.
  purpose: "Org structure managers can parse — Billing vs Escalations routing groups, then L1/L2/L3 ladder and department placement"
  stage: "command_center"
  access: persona(manager, agent)

  people_pulse:
    source: User
    display: metrics
    aggregate:
      people: count(User)
      active: count(User where is_active = true)
      l1: count(User where is_active = true and support_tier = l1 and department != External)
      l2: count(User where is_active = true and support_tier = l2 and department != External)
      l3: count(User where is_active = true and support_tier = l3 and department != External)
      open_tickets: count(Ticket where status = open)
      unassigned: count(Ticket where assigned_to = null and status = open)
    tones:
      active: positive
      l1: accent
      l2: warning
      l3: positive
      open_tickets: warning
      unassigned: warning

  # Cycle 2093 billing_escalations_seat — Zendesk/Front route billing vs
  # escalations as exclusive groups, not mixed into the L1 dump.
  billing_staff:
    source: User
    filter: is_active = true and department = Billing
    sort: name asc
    limit: 3
    display: queue
    action: user_detail
    empty: "No billing specialists — seed department = Billing on staff"

  escalations_staff:
    source: User
    filter: is_active = true and department = Escalations
    sort: name asc
    limit: 3
    display: queue
    action: user_detail
    empty: "No escalation specialists — seed department = Escalations on staff"

  # Open load next to routing groups — tickets with no owner.
  unassigned_work:
    source: Ticket
    filter: assigned_to = null and status = open
    sort: priority desc, created_at asc
    limit: 4
    display: queue
    action: ticket_edit
    empty: "Every open ticket has an assignee"

  # L1 frontline — first-response agents managers reassign soft work to
  # (exclusive support_tier = l1; customers never appear).
  l1_frontline:
    source: User
    filter: is_active = true and support_tier = l1 and department != External
    sort: name asc
    limit: 3
    display: queue
    action: user_detail
    empty: "No L1 frontline agents — seed support_tier = l1 on staff"

  # L3 lead — managers / leads for final escalation (exclusive L3; cycle 2073
  # recipe l3_lead_density — paired with L1 above fold; not L1/L2 dual re-stack).
  l3_lead:
    source: User
    filter: is_active = true and support_tier = l3 and department != External
    sort: name asc
    limit: 3
    display: queue
    action: user_detail
    empty: "No L3 leads — seed support_tier = l3 on managers"

  # L2 escalation — specialists for raised/critical handoff (exclusive L2).
  l2_escalation:
    source: User
    filter: is_active = true and support_tier = l2 and department != External
    sort: name asc
    limit: 3
    display: queue
    action: user_detail
    empty: "No L2 escalation specialists — seed support_tier = l2 on staff"

  # Role board (agent / manager columns) — org authority under tier density.
  # Staff only: department != External keeps customers off org boards.
  by_role:
    source: User
    filter: is_active = true and department != External
    display: kanban
    group_by: role
    sort: name asc
    limit: 24
    action: user_detail
    empty: "No support staff yet"

  # Department placement — Support / Escalations / Billing columns.
  by_department:
    source: User
    filter: is_active = true and department != External
    display: kanban
    group_by: department
    sort: name asc
    limit: 24
    action: user_detail
    empty: "No support staff yet"

  # Assignee columns for Monday capacity after org shape (reassignment clarity).
  plate_by_person:
    source: Ticket
    filter: status != closed and assigned_to != null
    display: kanban
    group_by: assigned_to
    sort: priority desc
    limit: 24
    action: ticket_edit
    empty: "No assigned open work"

  org_hint:
    display: status_list
    entries:
      - title: "Billing vs Escalations"
        caption: "Exclusive department routing groups — not mixed into L1 dump"
        icon: "building"
        state: accent
      - title: "L1 / L2 / L3 tier ladder"
        caption: "Frontline + lead + escalation people queues after routing groups"
        icon: "users"
        state: positive
      - title: "Unassigned + plate"
        caption: "Open load next to routing groups — no twin staff roster"
        icon: "list-checks"
        state: warning

  ux:
    as manager:
      purpose: "Route via Billing vs Escalations groups + unassigned load - no twin roster dump"
      focus: people_pulse, billing_staff, escalations_staff, unassigned_work
    as agent:
      purpose: "Read Billing vs Escalations groups for handoff - no twin roster dump"
      focus: people_pulse, billing_staff, escalations_staff, unassigned_work

persona admin "Administrator":
  # Product admin lands on the work queue — not framework platform chrome (#1626).
  default_workspace: ticket_queue
  uses nav admin_nav

persona customer "Customer":
  description: "End user submitting support requests and tracking their status"
  goals: "Submit new tickets easily", "Track ticket status and updates", "Receive timely responses from support"
  proficiency: novice
  default_workspace: my_tickets
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

nav customer_nav:
  group "My support":
    my_tickets

nav agent_nav:
  group "Work":
    ticket_queue
    agent_dashboard
    agent_console
    # Agents may open People for reassignment context (read org shape).
    people_desk

nav manager_nav:
  group "Lead":
    manager_ops
    people_desk
    ticket_queue
    agent_console
    agent_dashboard

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
