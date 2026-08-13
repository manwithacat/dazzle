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
    repr_fields: [name, role, department]

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
    repr_fields: [ticket, author, content, customer_tone, channel, escalation, ball_in_court, is_internal]

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
    columns: content, customer_tone, channel, escalation, ball_in_court, is_internal, created_at

surface user_create "Create User":
  uses entity User
  mode: create
  render: fragment

  section main "New User":
    field email "Email"
    field name "Name"
    field role "Role"
    field department "Department"
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
    columns: content, author, customer_tone, channel, escalation, ball_in_court, created_at, is_internal

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
  purpose: "Team headshots, needs-reply ball, hot tone/escalation speech, live trail, and SLA waiver documents"
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
  # `summary` is a metrics alias — keep one fleet consumer for coverage gate.
  # Cycle 1940 conversation peer-pack: tone/escalation heat (not ball-only).
  # Cycle 1955: awaiting_customer complements needs_reply (both ball sides).
  # Cycle 1958: thankful recovery complements hot_speech (warm closeout trail).
  # Cycle 1966: internal collab notes (is_internal) — non-channel peer grain.
  # Cycle 1969: critical escalations (escalation=critical) — P1 speech, not channel.
  # Cycle 1977: frustrated_speech (tone=frustrated only) — CSAT risk, not hot_speech OR.
  # Cycle 1979: urgent_speech (tone=urgent only) — SLA time-pressure, not hot_speech OR.
  # Cycle 1982: email_live (channel=email only) — async email path, not chat/phone re-stack.
  # Cycle 1984: portal_live (channel=portal only) — self-serve portal path, not email re-stack.
  # Cycle 1986: email_needs_reply — channel=email AND ball_in_court=agent (not full email_live).
  # Cycle 1988: portal_needs_reply — channel=portal AND ball_in_court=agent (not full portal_live).
  # Cycle 1990: chat_needs_reply — channel=chat AND ball_in_court=agent (not full chat_live).
  # Cycle 1992: phone_needs_reply — channel=phone AND ball_in_court=agent (not full phone_live).
  # Cycle 1994: frustrated_needs_reply — tone=frustrated AND ball_in_court=agent (not channel re-stack).
  queue_metrics:
    source: Ticket
    display: summary
    aggregate:
      total_open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      critical: count(Ticket where priority = critical and status != closed)
      conversation: count(Comment)
      needs_reply: count(Comment where ball_in_court = agent)
      awaiting_customer: count(Comment where ball_in_court = customer)
      hot_speech: count(Comment where (customer_tone = frustrated or customer_tone = urgent or escalation != none) and is_internal = false)
      critical_escalations: count(Comment where escalation = critical and is_internal = false)
      raised_escalations: count(Comment where escalation = raised and is_internal = false)
      frustrated_speech: count(Comment where customer_tone = frustrated and is_internal = false)
      frustrated_needs_reply: count(Comment where customer_tone = frustrated and ball_in_court = agent and is_internal = false)
      urgent_speech: count(Comment where customer_tone = urgent and is_internal = false)
      thankful_recovery: count(Comment where customer_tone = thankful and is_internal = false)
      chat_live: count(Comment where channel = chat and is_internal = false)
      chat_needs_reply: count(Comment where channel = chat and ball_in_court = agent and is_internal = false)
      phone_live: count(Comment where channel = phone and is_internal = false)
      phone_needs_reply: count(Comment where channel = phone and ball_in_court = agent and is_internal = false)
      email_live: count(Comment where channel = email and is_internal = false)
      email_needs_reply: count(Comment where channel = email and ball_in_court = agent and is_internal = false)
      portal_live: count(Comment where channel = portal and is_internal = false)
      portal_needs_reply: count(Comment where channel = portal and ball_in_court = agent and is_internal = false)
      internal_notes: count(Comment where is_internal = true)
      documents: count(SlaWaiver)
    tones:
      critical: destructive
      in_progress: accent
      conversation: accent
      needs_reply: warning
      awaiting_customer: accent
      hot_speech: destructive
      critical_escalations: destructive
      raised_escalations: warning
      frustrated_speech: destructive
      frustrated_needs_reply: destructive
      urgent_speech: warning
      thankful_recovery: positive
      chat_live: accent
      chat_needs_reply: warning
      phone_live: warning
      phone_needs_reply: warning
      email_live: accent
      email_needs_reply: warning
      portal_live: accent
      portal_needs_reply: warning
      internal_notes: accent
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

  # Peer-pack conversation upgrade (cycle 1955): Front / Intercom "waiting on
  # customer" — agent speech that kicked the ball back; do not re-thrash these
  # threads as open agent work (recipe awaiting_customer_trail).
  awaiting_customer:
    source: Comment
    filter: ball_in_court = customer and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "Nothing waiting on customers — every outbound note is closed or still on us"

  # Peer-pack conversation upgrade (cycle 1940): Zendesk/Front "heated" trail —
  # frustrated/urgent tone or raised/critical escalation, not ball_in_court alone
  # (recipe tone_escalation_heat; not needs_reply_ball re-stack).
  hot_speech:
    source: Comment
    filter: (customer_tone = frustrated or customer_tone = urgent or escalation != none) and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No heated customer speech — tone and escalation are quiet"

  # Peer-pack conversation upgrade (cycle 1977): Zendesk/Intercom CSAT-risk lean-in —
  # customer_tone=frustrated only (not urgent OR escalation umbrella in hot_speech)
  # (recipe frustrated_tone_trail; not hot_speech / escalation / channel re-stack).
  frustrated_speech:
    source: Comment
    filter: customer_tone = frustrated and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No frustrated customer speech — CSAT-risk notes land here when tone is frustrated"

  # Peer-pack conversation upgrade (cycle 1994): Intercom/Zendesk "angry and waiting
  # on you" — customer_tone=frustrated AND ball_in_court=agent (recipe
  # frustrated_needs_reply_trail; not full frustrated_speech or channel×ball re-stack).
  frustrated_needs_reply:
    source: Comment
    filter: customer_tone = frustrated and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No frustrated notes waiting on agents — CSAT-risk speech is closed or still on the customer"

  # Peer-pack conversation upgrade (cycle 1979): Zendesk/Intercom SLA time-pressure —
  # customer_tone=urgent only (not frustrated OR escalation umbrella in hot_speech)
  # (recipe urgent_tone_trail; not hot_speech / frustrated / channel / escalation re-stack).
  urgent_speech:
    source: Comment
    filter: customer_tone = urgent and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No urgent customer speech — SLA time-pressure notes land here when tone is urgent"

  # Peer-pack conversation upgrade (cycle 1969): Zendesk/Service Cloud P1 speech —
  # escalation=critical only so leads lean into ARR-risk / critical path notes
  # (recipe critical_escalation_trail; not hot_speech or channel re-stack).
  critical_escalations:
    source: Comment
    filter: escalation = critical and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No critical escalations — P1 customer speech lands here when raised to critical"

  # Peer-pack conversation upgrade (cycle 1972): Zendesk/Service Cloud L2 raised —
  # escalation=raised (not critical) so agents lean into tier-2 handoffs before P1
  # (recipe raised_escalation_trail; not critical_escalation or channel re-stack).
  raised_escalations:
    source: Comment
    filter: escalation = raised and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No raised escalations — L2 handoff notes land here before P1 critical"

  # Peer-pack conversation upgrade (cycle 1958): Intercom/Zendesk "warm recovery"
  # — thankful customer speech after a fix so agents lean into closeout wins
  # (recipe thankful_recovery_trail; not hot_speech re-stack).
  thankful_recovery:
    source: Comment
    filter: customer_tone = thankful and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No thankful recovery notes yet — closeout wins land here after a fix lands"

  # Peer-pack conversation upgrade (cycle 1960): Intercom/Front live chat path —
  # channel=chat public speech so agents lean into real-time channel grain
  # (recipe chat_channel_trail; not tone/ball re-stack).
  chat_live:
    source: Comment
    filter: channel = chat and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No live chat notes — portal/email/phone still carry the rest of the trail"

  # Peer-pack conversation upgrade (cycle 1990): Intercom/Front "chat waiting
  # on you" — channel=chat AND ball_in_court=agent (recipe chat_needs_reply_trail;
  # not full chat_live or ball-only needs_reply re-stack).
  chat_needs_reply:
    source: Comment
    filter: channel = chat and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No chat notes waiting on agents — live chat is closed or still on the customer"

  # Peer-pack conversation upgrade (cycle 1963): Zendesk phone path —
  # channel=phone public speech so agents lean into voice-channel grain
  # (recipe phone_channel_trail; not chat re-stack).
  phone_live:
    source: Comment
    filter: channel = phone and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No phone-channel notes — chat/portal/email still carry the rest of the trail"

  # Peer-pack conversation upgrade (cycle 1992): Zendesk/Front "phone waiting
  # on you" — channel=phone AND ball_in_court=agent (recipe phone_needs_reply_trail;
  # not full phone_live or ball-only needs_reply re-stack).
  phone_needs_reply:
    source: Comment
    filter: channel = phone and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No phone notes waiting on agents — voice intake is closed or still on the customer"

  # Peer-pack conversation upgrade (cycle 1982): Zendesk/Front email path —
  # channel=email public speech so agents lean into async email grain
  # (recipe email_channel_trail; not chat/phone/tone re-stack).
  email_live:
    source: Comment
    filter: channel = email and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No email-channel notes — chat/phone/portal still carry the rest of the trail"

  # Peer-pack conversation upgrade (cycle 1986): Front/Intercom "email waiting
  # on you" — channel=email AND ball_in_court=agent (recipe email_needs_reply_trail;
  # not full email_live or ball-only needs_reply re-stack).
  email_needs_reply:
    source: Comment
    filter: channel = email and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No email notes waiting on agents — outbound email is closed or still on the customer"

  # Peer-pack conversation upgrade (cycle 1984): Zendesk/Intercom portal path —
  # channel=portal public speech so agents lean into self-serve portal grain
  # (recipe portal_channel_trail; not email/chat/phone/tone re-stack).
  portal_live:
    source: Comment
    filter: channel = portal and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No portal-channel notes — email/chat/phone still carry the rest of the trail"

  # Peer-pack conversation upgrade (cycle 1988): Intercom/Zendesk "portal waiting
  # on you" — channel=portal AND ball_in_court=agent (recipe portal_needs_reply_trail;
  # not full portal_live or ball-only needs_reply re-stack).
  portal_needs_reply:
    source: Comment
    filter: channel = portal and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No portal notes waiting on agents — self-serve portal is closed or still on the customer"

  # Peer-pack conversation upgrade (cycle 1966): Zendesk/Front internal collab —
  # agent/manager side notes (is_internal) so triage stills show private handoff
  # grain, not another public channel filter (recipe internal_collab_trail).
  internal_notes:
    source: Comment
    filter: is_internal = true
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No internal collab notes — agent handoffs and side research land here"

  # Goal B conversation spine — newest notes as pull-to-open queue above the
  # ticket worklist so buyer stills show real thread copy (not empty timeline).
  # Hyperpart emitter dogfood: display: conversation → Message(.dz-message) + Bubble(.dz-bubble)
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
      - title: "Awaiting customer"
        caption: "Outbound notes with ball in customer court — park these; do not re-answer as open work"
        icon: "hourglass"
        state: accent
      - title: "Hot speech"
        caption: "Frustrated/urgent tone or raised escalation — lean into heat before the full trail"
        icon: "flame"
        state: destructive
      - title: "Critical escalations"
        caption: "P1 critical-path speech only — lean into ARR-risk notes before the mixed hot trail"
        icon: "siren"
        state: destructive
      - title: "Raised escalations"
        caption: "L2 raised handoffs (not P1) — lean into tier-2 notes before critical path"
        icon: "arrow-up"
        state: warning
      - title: "Thankful recovery"
        caption: "Warm closeout speech after a fix — lean into wins before the full trail"
        icon: "heart"
        state: positive
      - title: "Live chat"
        caption: "Chat-channel notes in real time — lean into Intercom-style live path before the full trail"
        icon: "messages-square"
        state: accent
      - title: "Phone path"
        caption: "Phone-channel notes from voice intake — lean into Zendesk phone grain before the full trail"
        icon: "phone"
        state: warning
      - title: "Phone needs reply"
        caption: "Phone notes with ball in agent court — answer voice waiting-on-you before the full phone trail"
        icon: "phone-call"
        state: warning
      - title: "Internal collab"
        caption: "Private agent/manager notes — lean into Zendesk internal handoffs before the public trail"
        icon: "lock"
        state: accent
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
      purpose: "Triage home — needs-reply + frustrated waiting-on-you"
      focus: media_shelf, queue_metrics, needs_reply, frustrated_needs_reply, phone_needs_reply, live_conversation
    as manager:
      purpose: "Triage home — needs-reply + frustrated waiting-on-you"
      focus: media_shelf, queue_metrics, needs_reply, frustrated_needs_reply, phone_needs_reply, live_conversation
    as admin:
      purpose: "Triage home — needs-reply + frustrated waiting-on-you"
      focus: media_shelf, queue_metrics, needs_reply, frustrated_needs_reply, phone_needs_reply, live_conversation


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
  purpose: "Multi-panel support ops — headshots, SLA breach pressure, dual queues, needs-reply ball, waiver documents, live conversation"
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
      critical_escalations: count(Comment where escalation = critical and is_internal = false)
      raised_escalations: count(Comment where escalation = raised and is_internal = false)
      frustrated_speech: count(Comment where customer_tone = frustrated and is_internal = false)
      frustrated_needs_reply: count(Comment where customer_tone = frustrated and ball_in_court = agent and is_internal = false)
      urgent_speech: count(Comment where customer_tone = urgent and is_internal = false)
      internal_notes: count(Comment where is_internal = true)
      documents: count(SlaWaiver)
    tones:
      critical_open: destructive
      unassigned: warning
      at_risk: warning
      breached: destructive
      resolved: positive
      in_progress: accent
      conversation: accent
      needs_reply: warning
      critical_escalations: destructive
      raised_escalations: warning
      frustrated_speech: destructive
      frustrated_needs_reply: destructive
      urgent_speech: warning
      internal_notes: accent
      documents: accent

  # Live SLA pressure (cycle 1913) — peer Zendesk/Front show breach risk rows
  # with sla_state grain, not only a static "4h breach" caption. Declared
  # before the readiness strip so buyer stills see work rows above fold.
  breach_risk:
    source: Ticket
    filter: (sla_state = at_risk or sla_state = breached) and status != closed
    sort: created_at asc
    limit: 4
    display: queue
    action: ticket_edit
    empty: "No at-risk or breached tickets — first-response SLA is on track"

  # Static readiness strip — pairs with sla TicketResponseTime commitment.
  sla_readiness:
    display: status_list
    entries:
      - title: "Ticket response SLA"
        caption: "Warning 2h · breach 4h · critical 8h (business hours)"
        icon: "clock"
        state: accent
      - title: "SLA breach pressure"
        caption: "At-risk and breached tickets surface in breach risk before priority-only queues"
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

  # Peer-pack critical_escalation_trail (cycle 1969) — P1 critical speech on ops.
  critical_escalations:
    source: Comment
    filter: escalation = critical and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No critical escalations for the team — P1 speech lands here"

  # Peer-pack raised_escalation_trail (cycle 1972) — L2 raised handoffs on ops.
  raised_escalations:
    source: Comment
    filter: escalation = raised and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No raised escalations for the team — L2 handoffs land here"

  # Peer-pack frustrated_tone_trail (cycle 1977) — pure frustrated CSAT-risk speech on ops.
  frustrated_speech:
    source: Comment
    filter: customer_tone = frustrated and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No frustrated customer speech for the team — CSAT-risk notes land here"

  # Peer-pack frustrated_needs_reply_trail (cycle 1994) — CSAT-risk speech still on agents.
  frustrated_needs_reply:
    source: Comment
    filter: customer_tone = frustrated and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No frustrated notes waiting on the team — CSAT-risk speech is closed or still on the customer"

  # Peer-pack urgent_tone_trail (cycle 1979) — pure urgent SLA time-pressure speech on ops.
  urgent_speech:
    source: Comment
    filter: customer_tone = urgent and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No urgent customer speech for the team — SLA time-pressure notes land here"

  # Peer-pack chat_channel_trail (cycle 1960) — live chat path on manager home.
  chat_live:
    source: Comment
    filter: channel = chat and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No live chat notes for the team — other channels still carry the trail"

  # Peer-pack chat_needs_reply_trail (cycle 1990) — chat still waiting on agents.
  chat_needs_reply:
    source: Comment
    filter: channel = chat and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No chat notes waiting on the team — live chat is closed or still on the customer"

  # Peer-pack phone_channel_trail (cycle 1963) — voice intake path.
  phone_live:
    source: Comment
    filter: channel = phone and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No phone-channel notes for the team — chat and email still carry the trail"

  # Peer-pack phone_needs_reply_trail (cycle 1992) — phone still waiting on agents.
  phone_needs_reply:
    source: Comment
    filter: channel = phone and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No phone notes waiting on the team — voice intake is closed or still on the customer"

  # Peer-pack email_channel_trail (cycle 1982) — async email intake path.
  email_live:
    source: Comment
    filter: channel = email and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No email-channel notes for the team — chat/phone/portal still carry the trail"

  # Peer-pack email_needs_reply_trail (cycle 1986) — email still waiting on agents.
  email_needs_reply:
    source: Comment
    filter: channel = email and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No email notes waiting on the team — outbound email is closed or still on the customer"

  # Peer-pack portal_channel_trail (cycle 1984) — self-serve portal intake path.
  portal_live:
    source: Comment
    filter: channel = portal and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No portal-channel notes for the team — email/chat/phone still carry the trail"

  # Peer-pack portal_needs_reply_trail (cycle 1988) — portal still waiting on agents.
  portal_needs_reply:
    source: Comment
    filter: channel = portal and ball_in_court = agent and is_internal = false
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No portal notes waiting on the team — self-serve portal is closed or still on the customer"

  # Peer-pack internal_collab_trail (cycle 1966) — private agent/manager handoffs
  # (is_internal) on the ops home; not another public channel filter.
  internal_notes:
    source: Comment
    filter: is_internal = true
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No internal collab notes for the team — side research and handoffs land here"

  # Goal B conversation spine AFTER dual attention + composition so manager
  # hero stills show pressure queues, documents, and Message/Bubble chrome.
  # display: conversation → MessageScroller (same path as ticket_queue live_conversation).
  live_conversation:
    source: Comment
    sort: created_at desc
    limit: 4
    display: conversation
    action: comment_detail
    empty: "No conversation yet — customer and agent notes appear here as cases move"

  ux:
    as manager:
      purpose: "Multi-panel support ops — SLA pressure, needs-reply, frustrated waiting-on-you, dual queues"
      focus: media_shelf, team_metrics, breach_risk, critical_queue, unassigned_queue, needs_reply, frustrated_needs_reply, live_conversation

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
  purpose: "Personal WIP board with both-ball conversation plus thankful recovery on claimed cases"
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

  # Peer-pack critical_escalation_trail (cycle 1969) — P1 critical speech on my plate.
  critical_escalations:
    source: Comment
    filter: escalation = critical and is_internal = false
    sort: created_at desc
    limit: 6
    display: conversation
    action: comment_detail
    empty: "No critical escalations on your plate — P1 speech lands here"

  # Peer-pack raised_escalation_trail (cycle 1972) — L2 raised handoffs on my plate.
  raised_escalations:
    source: Comment
    filter: escalation = raised and is_internal = false
    sort: created_at desc
    limit: 6
    display: conversation
    action: comment_detail
    empty: "No raised escalations on your plate — L2 handoffs land here"

  # Peer-pack frustrated_tone_trail (cycle 1977) — pure frustrated speech on my plate.
  frustrated_speech:
    source: Comment
    filter: customer_tone = frustrated and is_internal = false
    sort: created_at desc
    limit: 6
    display: conversation
    action: comment_detail
    empty: "No frustrated customer speech on your plate — CSAT-risk notes land here"

  # Peer-pack urgent_tone_trail (cycle 1979) — pure urgent SLA time-pressure on my plate.
  urgent_speech:
    source: Comment
    filter: customer_tone = urgent and is_internal = false
    sort: created_at desc
    limit: 6
    display: conversation
    action: comment_detail
    empty: "No urgent customer speech on your plate — SLA time-pressure notes land here"

  # Peer-pack awaiting_customer_trail (cycle 1955) — notes I (or the desk)
  # kicked back; park until the customer answers (not open agent thrash).
  awaiting_customer:
    source: Comment
    filter: ball_in_court = customer and is_internal = false
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "Nothing waiting on customers from this desk"

  # Peer-pack thankful_recovery_trail (cycle 1958) — warm closeout speech.
  thankful_recovery:
    source: Comment
    filter: customer_tone = thankful and is_internal = false
    sort: created_at desc
    limit: 6
    display: conversation
    action: comment_detail
    empty: "No thankful recovery notes on your plate yet"

  # Peer-pack internal_collab_trail (cycle 1966) — private notes on my plate.
  internal_notes:
    source: Comment
    filter: is_internal = true
    sort: created_at desc
    limit: 6
    display: conversation
    action: comment_detail
    empty: "No internal collab notes on your plate — handoffs and side research land here"

  # Conversation on my plate — queue of recent notes (Goal B conversation depth).
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
      purpose: "Personal WIP + needs-reply + urgent speech — no funnel theater"
      focus: my_assigned, needs_reply, urgent_speech, awaiting_customer, pending_resolution
    as manager:
      purpose: "Personal WIP + needs-reply + urgent speech — no funnel theater"
      focus: my_assigned, needs_reply, urgent_speech, awaiting_customer, pending_resolution

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

  agent_priority_queue:
    source: Ticket
    filter: assigned_to = current_context and status != closed
    sort: priority desc, created_at asc
    limit: 15
    display: queue
    action: ticket_edit
    empty: "No open tickets for this agent"

  agent_comment_trail:
    source: Comment
    filter: ticket.assigned_to = current_context
    sort: created_at desc
    limit: 15
    display: timeline
    action: comment_detail
    empty: "No comments on this agent's tickets"

  agent_ticket_cards:
    source: Ticket
    filter: assigned_to = current_context and status != closed
    sort: priority desc
    limit: 12
    display: queue
    action: ticket_detail
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

# Goal B org_structure (cycle 1847): peer support tools (Zendesk / Intercom /
# Freshdesk) show team by role and department so managers reassign without a
# flat warehouse roster. Filter staff only — customers are not org nodes.
workspace people_desk "People":
  purpose: "Org structure managers can parse — support staff by role and department before open load"
  stage: "command_center"
  access: persona(manager, agent)

  people_pulse:
    source: User
    display: metrics
    aggregate:
      people: count(User)
      active: count(User where is_active = true)
      open_tickets: count(Ticket where status = open)
      unassigned: count(Ticket where assigned_to = null and status = open)
    tones:
      active: positive
      open_tickets: warning
      unassigned: warning

  # Role board (agent / manager columns) — org authority for reassignment.
  # is_active keeps inactive accounts off the board; customers remain in
  # kanban only if seeded active (demo seeds keep customers off staff focus via
  # department External — manager reads Support/Escalations/Billing first).
  by_role:
    source: User
    filter: is_active = true
    display: kanban
    group_by: role
    sort: name asc
    limit: 40
    action: user_detail
    empty: "No support staff yet"

  # Department roster — Support / Escalations / Billing placement before flat list.
  by_department:
    source: User
    filter: is_active = true
    display: queue
    sort: department asc, name asc
    limit: 40
    action: user_detail
    empty: "No support staff yet"

  roster:
    source: User
    filter: is_active = true
    sort: department asc, name asc
    limit: 20
    display: queue
    action: user_detail
    empty: "No active support staff"

  # Open load after org shape — who still has unassigned work to claim.
  unassigned_work:
    source: Ticket
    filter: assigned_to = null and status = open
    sort: priority desc, created_at asc
    limit: 12
    display: queue
    action: ticket_edit
    empty: "Every open ticket has an assignee"

  # Assignee columns for Monday capacity after org shape (reassignment clarity).
  plate_by_person:
    source: Ticket
    filter: status != closed and assigned_to != null
    display: kanban
    group_by: assigned_to
    sort: priority desc
    action: ticket_edit
    empty: "No assigned open work"

  org_hint:
    display: status_list
    entries:
      - title: "By role board"
        caption: "Agent / Manager columns show who can take work at a glance"
        icon: "users"
        state: accent
      - title: "Department queue"
        caption: "Support, Escalations, Billing — place people before load dump"
        icon: "building"
        state: positive
      - title: "Plate by person"
        caption: "Assignee columns for reassignment after you read org shape"
        icon: "list-checks"
        state: warning

  ux:
    as manager:
      purpose: "See support staff by role and department before unassigned load"
      focus: people_pulse, by_role, by_department, roster
    as agent:
      purpose: "Read team placement and open load for handoff"
      focus: people_pulse, by_role, by_department, roster

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
