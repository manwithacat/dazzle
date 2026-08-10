# LLM Ticket Classifier - Example App
# Demonstrates LLM Jobs as First-Class Events (Issue #33)
#
# This example shows how to:
# 1. Define LLM models with provider, tier, and cost configuration
# 2. Configure global LLM settings (artifact store, logging, rate limits)
# 3. Create LLM intents for classification tasks
# 4. Use retry and PII policies for production readiness

module llm_ticket_classifier
app ticket_classifier "Support Ticket Classifier":
  security_profile: basic

persona admin "Administrator":
  default_workspace: _platform_admin

# =============================================================================
# LLM Model Definitions
# =============================================================================

# Fast model for simple classifications
llm_model claude_haiku "Claude Haiku (Fast)":
  provider: anthropic
  model_id: claude-3-haiku-20240307
  tier: fast
  max_tokens: 1024

# Balanced model for most tasks
llm_model claude_sonnet "Claude Sonnet (Balanced)":
  provider: anthropic
  model_id: claude-3-5-sonnet-20241022
  tier: balanced
  max_tokens: 4096

# Alternative provider for comparison
llm_model gpt4o_mini "GPT-4o Mini":
  provider: openai
  model_id: gpt-4o-mini
  tier: fast
  max_tokens: 2048

# Vertex AI / Gemini (GCP ADC — same contract as Badger Vertex smoke).
# Requires: gcloud ADC, aiplatform API, roles/aiplatform.user, google-genai.
# llm_model gemini_flash "Gemini Flash (Vertex)":
#   provider: google
#   model_id: gemini-2.5-flash
#   project: my-gcp-project
#   location: global
#   tier: fast
#   max_tokens: 2048

# OpenAI-compatible local server (Ollama / vLLM / LiteLLM proxy).
# llm_model ollama_local "Local Ollama":
#   provider: openai
#   model_id: llama3.2
#   base_url: "http://localhost:11434/v1"


# =============================================================================
# LLM Configuration
# =============================================================================

llm_config:
  default_model: claude_sonnet
  artifact_store: local
  logging:
    log_prompts: true
    log_completions: true
    redact_pii: true
  rate_limits:
    claude_haiku: 100
    claude_sonnet: 60
    gpt4o_mini: 50
  concurrency:
    claude_haiku: 10
    claude_sonnet: 5
    gpt4o_mini: 3


# =============================================================================
# LLM Intents (Job Definitions)
# =============================================================================

# Simple category classification — auto-triggers on new tickets
llm_intent classify_ticket "Classify Support Ticket":
  model: claude_haiku
  prompt: "Classify this support ticket into exactly one category: billing, technical, feature_request, account, or other.\n\nTicket:\n$description\n\nRespond with only the category name."
  timeout: 15
  trigger:
    on_entity: Ticket
    on_event: created
    input_map:
      description: entity.description
  pii:
    scan: true
    action: redact

# Priority assessment with structured output
llm_intent assess_priority "Assess Ticket Priority":
  model: claude_sonnet
  prompt: "Assess the priority of this support ticket. Consider urgency, business impact, and customer sentiment.\n\nTicket:\n$description\n\nRespond with JSON: {\"priority\": \"low|medium|high|critical\", \"reasoning\": \"brief explanation\"}"
  output_schema: PriorityAssessment
  timeout: 30
  retry:
    max_attempts: 3
    backoff: exponential
  pii:
    scan: true
    action: redact

# Sentiment analysis
llm_intent analyze_sentiment "Analyze Customer Sentiment":
  model: claude_haiku
  prompt: "Analyze the customer sentiment in this support ticket.\n\nTicket:\n$description\n\nRespond with JSON: {\"sentiment\": \"positive|neutral|negative|frustrated\", \"confidence\": 0.0-1.0}"
  timeout: 10
  pii:
    scan: true
    action: redact

# Generate response suggestion
llm_intent suggest_response "Suggest Response":
  model: claude_sonnet
  prompt: "Based on this support ticket and its classification, suggest a helpful response template.\n\nTicket:\n$description\n\nCategory: $category\nPriority: $priority\n\nProvide a professional, empathetic response template."
  timeout: 45
  retry:
    max_attempts: 2
    backoff: linear
    initial_delay_ms: 500
  pii:
    scan: true
    action: warn


# =============================================================================
# Entities
# =============================================================================

entity Ticket "Support Ticket":
  display_field: subject
  id: uuid pk
  subject: str(200) required
  description: text required pii(category=freeform)
  customer_email: str(100) required pii(category=contact)
  status: enum[open, in_progress, resolved, closed] = open
  # domain_lifecycle_priors: status enum had no transitions (status∄t residual)
  transitions:
    open -> in_progress
    in_progress -> resolved
    resolved -> closed
    in_progress -> open
    resolved -> in_progress
    closed -> open: role(supervisor) or role(admin)
  created_at: datetime auto_add
  updated_at: datetime auto_update

entity TicketClassification "Ticket Classification":
  # Goal B conversation: queue title is the AI suggested reply (buyer-readable
  # thread line), not a bare category enum shell.
  display_field: suggested_response
  id: uuid pk
  ticket: ref Ticket required
  category: enum[billing, technical, feature_request, account, other]
  priority: enum[low, medium, high, critical]
  sentiment: enum[positive, neutral, negative, frustrated]
  confidence: decimal(3,2)
  suggested_response: text
  classified_at: datetime auto_add
  llm_job_id: str(100)  # Reference to LLM job for auditability

  fitness:
    repr_fields: [ticket, category, priority, sentiment, confidence, suggested_response, classified_at]

entity PriorityAssessment "Priority Assessment Result":
  id: uuid pk
  priority: str(20) required
  reasoning: str(500)

# Goal B org_structure (cycle 1869): peer support tools (Zendesk / Intercom /
# Freshdesk / Gorgias) show agents by title and department so supervisors place
# people and load — not a flat ticket-only roster with no staff hierarchy.
entity SupportStaff "Support Staff":
  intent: "Support org row — department and job title so the Team desk shows staffing shape before ticket load"
  domain: support
  patterns: org_structure, directory
  display_field: name
  id: uuid pk
  name: str(120) required
  email: email required pii(category=contact)
  role: enum[support_agent, supervisor, admin]=support_agent
  department: str(50)
  job_title: str(80)
  status: enum[active, onboarding, offboarded]=active
  created_at: datetime auto_add

  permit:
    list: role(admin) or role(supervisor) or role(support_agent)
    read: role(admin) or role(supervisor) or role(support_agent)
    create: role(admin) or role(supervisor)
    update: role(admin) or role(supervisor)

  scope:
    list: all
      as: admin, supervisor, support_agent
    read: all
      as: admin, supervisor, support_agent
    create: all
      as: admin, supervisor
    update: all
      as: admin, supervisor

  fitness:
    repr_fields: [name, email, role, department, job_title, status]


# =============================================================================
# Surfaces
# =============================================================================

surface ticket_list "Tickets":
  uses entity Ticket
  mode: list
  # Primary drill: ticket hub (queue + AI classifications), not a warehouse list
  open: Ticket via id
  section main:
    field subject "Subject"
    field customer_email "Customer"
    field status "Status"
    field created_at "Created"
  ux:
    purpose: "Work the open ticket queue — open a row for the ticket + AI hub"
    sort: created_at desc
    filter: status
    search: subject, customer_email
    empty: "No tickets in the queue."

surface ticket_create "New Ticket":
  uses entity Ticket
  mode: create
  section main:
    field subject "Subject"
    field description "Description"
    field customer_email "Customer Email"
  ux:
    purpose: "Capture a new support ticket for LLM classification on create"

surface ticket_edit "Edit Ticket":
  uses entity Ticket
  mode: edit
  section summary "Summary":
    field subject "Subject"
    field description "Description"
    field customer_email "Customer Email"
  section lifecycle "Lifecycle":
    layout: strip
    field status "Status"
  ux:
    purpose: "Update ticket body and transition status through the queue"

surface ticket_detail "Ticket Detail":
  uses entity Ticket
  mode: view
  section summary "Summary":
    field subject "Subject"
    field description "Description"
    field customer_email "Customer Email"
  section lifecycle "Lifecycle":
    layout: strip
    field status "Status"
    field created_at "Created"
    field updated_at "Updated"

  # Ticket hub AI trail — suggested reply first (Goal B conversation), then
  # triage badges — ST-002 support-agent hub path (cycle 1504 journey_dogfood).
  related classifications "AI Classifications":
    display: queue
    show: TicketClassification
    columns: suggested_response, category, priority, sentiment, classified_at

  ux:
    purpose: "Ticket hub — lifecycle strip and AI reply trail with triage labels"

surface classification_list "Classifications":
  uses entity TicketClassification
  mode: list
  # Dual open (cycle 1540 agent_acceptance): primary = classification hub for
  # ST-006 inspect run; secondary = parent Ticket hub for ST-003 trail review.
  open: TicketClassification via id | Ticket via ticket
  section main:
    field ticket "Ticket"
    field category "Category"
    field priority "Priority"
    field sentiment "Sentiment"
    field classified_at "Classified At"
  ux:
    purpose: "Review AI classifications — open a row for the classification hub or parent ticket hub"
    sort: classified_at desc
    filter: category, priority, sentiment
    search: suggested_response, llm_job_id
    empty: "No classifications yet. Submit tickets to generate AI classifications."

surface classification_detail "Classification Detail":
  uses entity TicketClassification
  mode: view
  section triage "Triage":
    field ticket "Ticket"
    field category "Category"
    field priority "Priority"
    field sentiment "Sentiment"
  section confidence "Model output":
    layout: strip
    field confidence "Confidence"
    field classified_at "Classified At"
    field llm_job_id "LLM Job"
  section suggestion "Suggested response":
    field suggested_response "Suggested Response"
  ux:
    purpose: "Classification hub — triage labels, confidence strip, suggested reply"

surface staff_list "Team roster":
  uses entity SupportStaff
  mode: list
  open: SupportStaff via id
  section main:
    field name "Name"
    field email "Email"
    field role "Role"
    field job_title "Job Title"
    field department "Department"
    field status "Status"
  ux:
    purpose: "Browse support staff by title and department"
    sort: department asc, name asc
    filter: department, job_title, role, status
    search: name, email, department, job_title
    empty: "No support staff in the roster yet"

surface staff_detail "Team member":
  uses entity SupportStaff
  mode: view
  section identity "Identity":
    field name "Name"
    field email "Email"
    field role "Role"
    field job_title "Job Title"
    field department "Department"
  section lifecycle "Lifecycle":
    layout: strip
    field status "Status"
    field created_at "Joined"
  ux:
    purpose: "Team member — org placement and role for staffing decisions"

surface staff_create "Add Team Member":
  uses entity SupportStaff
  mode: create
  section identity:
    field name "Name"
    field email "Email"
    field role "Role"
    field job_title "Job Title"
    field department "Department"
    field status "Status"
  ux:
    purpose: "Add a support staff row with title and department placement"


# =============================================================================
# Workspaces
# =============================================================================

# Story-driven (docs/guides/story-to-composition.md): supervisor metrics +
# open queue first; agent ticket_management is a review queue not CRUD list.
# Goal B command_density (cycle 1791): peer Zendesk/Intercom AI supervisor
# homes put high-severity triage + open pressure above the AI reply trail —
# multi-panel attention, not conversation-only / flat queue thrash above fold.
workspace support_dashboard "Support Dashboard":
  # Goal B empty_region_honesty (cycle 1800): peer AI triage homes (Zendesk AI /
  # Intercom Fin) keep multi-panel attention + AI reply trail — not a second
  # open-board kanban and status bar chart that restate metrics as empty theater.
  purpose: "Multi-panel AI triage — metrics, dual attention, live AI replies, readiness"
  stage: "command_center"
  access: persona(supervisor, support_agent, admin)

  classification_metrics:
    source: Ticket
    display: metrics
    aggregate:
      open: count(Ticket where status = open)
      high_severity: count(TicketClassification where priority = high or priority = critical)
      classified: count(TicketClassification)
      in_progress: count(Ticket where status = in_progress)
      conversation: count(TicketClassification)
    tones:
      open: warning
      high_severity: destructive
      classified: positive
      in_progress: accent
      conversation: accent

  # Dual attention (fold share with capped AI reply trail).
  high_severity:
    source: TicketClassification
    filter: priority = high or priority = critical
    sort: classified_at desc
    limit: 4
    display: queue
    action: classification_detail
    empty: "No high-severity classifications — triage is quiet"

  open_attention:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 4
    display: queue
    action: ticket_detail
    empty: "No open tickets"

  # Goal B conversation spine AFTER dual attention — Message/Bubble chrome
  # for AI suggested replies (display_field: suggested_response).
  live_ai_replies:
    source: TicketClassification
    sort: classified_at desc
    limit: 4
    display: conversation
    action: classification_detail
    empty: "No AI replies yet — classify a ticket to draft the thread"

  # One utility strip after the fold job — not twin dumps of the open queue.
  in_progress_queue:
    source: Ticket
    filter: status = in_progress
    sort: created_at desc
    limit: 8
    display: queue
    action: ticket_detail
    empty: "Nothing in progress"

  # Work-surface utility: dated AI classification stream → timeline.
  classifications:
    source: TicketClassification
    sort: classified_at desc
    limit: 10
    display: timeline
    empty: "No classifications yet"

  triage_readiness:
    display: status_list
    entries:
      - title: "Open queue"
        caption: "Clear open tickets before they age out of SLA — dual attention above"
        icon: "inbox"
        state: warning
      - title: "AI classifications"
        caption: "Review confidence before routing — live replies above"
        icon: "sparkles"
        state: accent
      - title: "In progress"
        caption: "Claimed work sits in the utility queue — not a second status board"
        icon: "loader"
        state: positive

  ux:
    as supervisor:
      purpose: "Multi-panel AI triage — dual attention and AI replies, no empty chart theater"
      focus: classification_metrics, high_severity, open_attention, live_ai_replies, triage_readiness
    as support_agent:
      purpose: "Multi-panel AI triage — dual attention and AI replies, no empty chart theater"
      focus: classification_metrics, high_severity, open_attention, live_ai_replies, triage_readiness
    as admin:
      purpose: "Multi-panel AI triage — dual attention and AI replies, no empty chart theater"
      focus: classification_metrics, high_severity, open_attention, live_ai_replies, triage_readiness

workspace ticket_management "Ticket Management":
  # Goal B empty_region_honesty: one open worklist + AI trail — not open_only twin
  # queue, pipeline kanban, and priority bar chart restating the same rows.
  purpose: "Agent ticket desk — AI replies, open worklist, classification trail"
  access: persona(support_agent, supervisor, admin)

  agent_pulse:
    source: Ticket
    display: metrics
    aggregate:
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      classified: count(TicketClassification)
      priorities: count(PriorityAssessment)
    tones:
      open: warning
      in_progress: accent
      classified: positive

  # Goal B conversation on the agent default desk — draft replies first.
  live_ai_replies:
    source: TicketClassification
    sort: classified_at desc
    limit: 10
    display: queue
    action: ticket_detail
    empty: "No AI replies yet — classify a ticket to draft the thread"

  ticket_queue:
    source: Ticket
    filter: status != closed
    sort: created_at desc
    limit: 15
    display: queue
    action: ticket_detail
    empty: "No open tickets in the system"

  classification_trail:
    source: TicketClassification
    sort: classified_at desc
    limit: 12
    display: timeline
    empty: "No classifications yet"

  desk_readiness:
    display: status_list
    entries:
      - title: "AI draft replies"
        caption: "Suggested responses lead the desk — open a row for the ticket hub"
        icon: "sparkles"
        state: accent
      - title: "Open worklist"
        caption: "Non-closed tickets only — no twin open-only dump or status board"
        icon: "inbox"
        state: warning

  ux:
    as support_agent:
      purpose: "AI replies and open worklist — no twin queues or empty priority chart"
      focus: agent_pulse, live_ai_replies, ticket_queue, classification_trail, desk_readiness
    as supervisor:
      purpose: "AI replies and open worklist — no twin queues or empty priority chart"
      focus: agent_pulse, live_ai_replies, ticket_queue, classification_trail, desk_readiness
    as admin:
      purpose: "AI replies and open worklist — no twin queues or empty priority chart"
      focus: agent_pulse, live_ai_replies, ticket_queue, classification_trail, desk_readiness

# Third product workspace: classification-first desk so list
# surfaces no longer dominate vs job shells (AI triage is the product value).
workspace classification_desk "Classifications":
  purpose: "Review AI ticket classifications and confidence before hand-off"
  access: persona(supervisor, support_agent, admin)

  class_pulse:
    source: TicketClassification
    display: metrics
    aggregate:
      classifications: count(TicketClassification)
      tickets: count(Ticket)
    tones:
      classifications: accent

  # Goal B conversation composition: suggested replies are the desk body.
  live_ai_replies:
    source: TicketClassification
    sort: classified_at desc
    limit: 15
    display: queue
    action: ticket_detail
    empty: "No AI replies yet — classify a ticket to draft the thread"

  latest:
    source: TicketClassification
    sort: classified_at desc
    limit: 20
    display: queue
    empty: "No classifications yet"

  # Work-surface utility: open tickets are a pull queue (attention_rank).
  open_tickets:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 15
    display: queue
    action: ticket_detail
    empty: "No open tickets"

  class_trail:
    source: TicketClassification
    sort: classified_at desc
    limit: 15
    display: timeline
    empty: "No classifications yet"

  open_status_mix:
    source: Ticket
    filter: status != closed
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No open tickets"

workspace priority_desk "Priorities":
  purpose: "Priority assessment trail — severity signals next to open work"
  access: persona(supervisor, support_agent, admin)

  priority_pulse:
    source: PriorityAssessment
    display: metrics
    aggregate:
      assessments: count(PriorityAssessment)
      open: count(Ticket where status = open)
      classified: count(TicketClassification)
    tones:
      open: warning
      assessments: accent

  recent_assessments:
    source: PriorityAssessment
    sort: priority desc
    limit: 25
    display: queue
    empty: "No priority assessments yet"

  # Work-surface utility: open work is a pull queue, not a grid inventory.
  open_work:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 15
    display: queue
    action: ticket_detail
    empty: "No open tickets"

  assessment_trail:
    source: PriorityAssessment
    sort: priority desc
    limit: 15
    display: timeline
    empty: "No priority assessments yet"

  priority_mix:
    source: PriorityAssessment
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(PriorityAssessment)
    empty: "No priority assessments yet"

  severity_hint:
    display: status_list
    entries:
      - title: "Severity first"
        caption: "Pair AI priority with open queue before reassignment"
        icon: "gauge"
        state: accent
      - title: "Classifications"
        caption: "Category tags live on the Classifications desk"
        icon: "tags"
        state: positive

# Goal B org_structure (cycle 1869): peer AI support tools (Zendesk / Intercom /
# Freshdesk / Gorgias) show agents by title and department before a flat people
# dump — supervisors reassign and agents find owners from org shape, not a
# ticket-only roster with no staffing hierarchy.
workspace team_desk "Team":
  purpose: "Org structure for support — title and department before flat roster and ticket load"
  access: persona(supervisor, support_agent, admin)

  team_pulse:
    source: SupportStaff
    display: metrics
    aggregate:
      people: count(SupportStaff)
      open: count(Ticket where status = open)
      classified: count(TicketClassification)
    tones:
      people: accent
      open: warning
      classified: positive

  # Title board — Support Agent / Escalation Lead / Billing Specialist / …
  by_title:
    source: SupportStaff
    display: kanban
    group_by: job_title
    sort: name asc
    limit: 40
    action: staff_detail
    empty: "No titled support staff yet"

  # Department placement — Frontline Support / Escalations / Billing Ops / AI Ops.
  by_department:
    source: SupportStaff
    display: queue
    sort: department asc, name asc
    limit: 40
    action: staff_detail
    empty: "No staff placed in departments yet"

  # Secondary flat roster (after hierarchy).
  people:
    source: SupportStaff
    display: queue
    sort: department asc, name asc
    limit: 25
    action: staff_detail
    empty: "No support staff yet"

  # Ticket load after org shape — who carries open work, not before hierarchy.
  ticket_load:
    source: Ticket
    filter: status != closed
    sort: created_at desc
    limit: 15
    display: queue
    action: ticket_detail
    empty: "No open tickets"

  org_hint:
    display: status_list
    entries:
      - title: "By title board"
        caption: "Escalation Lead / Billing Specialist / AI Ops Reviewer columns show who can act"
        icon: "users"
        state: accent
      - title: "Department queue"
        caption: "Frontline Support / Escalations / Billing Ops / AI Ops before flat roster"
        icon: "building-2"
        state: positive
      - title: "Ticket load last"
        caption: "Open work after you read org shape"
        icon: "inbox"
        state: warning

  ux:
    as supervisor:
      purpose: "See support staff by title and department before ticket load"
      focus: team_pulse, by_title, by_department, people
    as support_agent:
      purpose: "Org structure for the floor — role board then department"
      focus: team_pulse, by_title, by_department, people
    as admin:
      purpose: "Read support org shape before open queue pressure"
      focus: team_pulse, by_title, by_department, people

persona support_agent "Support Agent":
  description: "Handle support tickets and view AI classifications"
  goals: "View and manage tickets", "Review AI classifications", "Update ticket status"
  proficiency: intermediate
  default_workspace: ticket_management
  default_route: "/tickets"
  uses nav agent_nav

persona supervisor "Support Supervisor":
  description: "Monitor ticket flow and AI classification accuracy"
  goals: "Monitor ticket classifications", "Review AI accuracy", "Manage team workload"
  proficiency: expert
  default_workspace: support_dashboard
  default_route: "/dashboard"
  uses nav supervisor_nav

nav agent_nav:
  group "My work":
    ticket_management
    classification_desk
    priority_desk
    team_desk
    support_dashboard

nav supervisor_nav:
  group "Oversight":
    support_dashboard
    team_desk
    classification_desk
    priority_desk
    ticket_management


# =============================================================================
# Scenarios - demo states for dev mode
# =============================================================================

scenario empty "Empty State":
  description: "Fresh install with no tickets - test onboarding"

  as persona support_agent:
    start_route: "/tickets"

  as persona supervisor:
    start_route: "/dashboard"

scenario active_tickets "Active Tickets":
  description: "Several tickets awaiting classification"

  as persona support_agent:
    start_route: "/tickets"

  as persona supervisor:
    start_route: "/dashboard"

  demo:
    Ticket:
      - subject: "Cannot login to my account", description: "I forgot my password and reset link is not working", customer_email: "user1@example.com", status: open
      - subject: "Billing question", description: "Why was I charged twice this month?", customer_email: "user2@example.com", status: open
      - subject: "Feature request for dark mode", description: "Would love to have a dark mode option in the app", customer_email: "user3@example.com", status: open
