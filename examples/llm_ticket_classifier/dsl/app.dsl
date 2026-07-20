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
  created_at: datetime auto_add
  updated_at: datetime auto_update

entity TicketClassification "Ticket Classification":
  id: uuid pk
  ticket: ref Ticket required
  category: enum[billing, technical, feature_request, account, other]
  priority: enum[low, medium, high, critical]
  sentiment: enum[positive, neutral, negative, frustrated]
  confidence: decimal(3,2)
  suggested_response: text
  classified_at: datetime auto_add
  llm_job_id: str(100)  # Reference to LLM job for auditability

entity PriorityAssessment "Priority Assessment Result":
  id: uuid pk
  priority: str(20) required
  reasoning: str(500)


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

  related classifications "AI Classifications":
    display: table
    show: TicketClassification

  ux:
    purpose: "Ticket hub — lifecycle strip and related LLM classification runs"

surface classification_list "Classifications":
  uses entity TicketClassification
  mode: list
  open: Ticket via ticket
  section main:
    field ticket "Ticket"
    field category "Category"
    field priority "Priority"
    field sentiment "Sentiment"
    field classified_at "Classified At"
  ux:
    purpose: "Review AI classifications — open a row for the parent ticket hub"
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


# =============================================================================
# Workspaces
# =============================================================================

# Story-driven (docs/guides/story-to-composition.md): supervisor metrics +
# open queue first; agent ticket_management is a review queue not CRUD list.
# WI L: denser landing regions (cap 6) on supervisor default.
workspace support_dashboard "Support Dashboard":
  purpose: "Monitor and classify support tickets"
  access: persona(supervisor, support_agent, admin)

  classification_metrics:
    source: Ticket
    display: metrics
    aggregate:
      open: count(Ticket where status = open)
      classified: count(TicketClassification)
      in_progress: count(Ticket where status = in_progress)
      priorities: count(PriorityAssessment)
    tones:
      open: warning
      classified: positive
      in_progress: accent

  open_queue:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 20
    display: queue
    action: ticket_detail
    empty: "No open tickets"

  in_progress_queue:
    source: Ticket
    filter: status = in_progress
    sort: created_at desc
    limit: 15
    display: queue
    action: ticket_detail
    empty: "Nothing in progress"

  classifications:
    source: TicketClassification
    sort: classified_at desc
    limit: 20
    display: list
    empty: "No classifications yet"

  priority_strip:
    source: PriorityAssessment
    sort: priority desc
    limit: 12
    display: list
    empty: "No priority assessments yet"

  triage_readiness:
    display: status_list
    entries:
      - title: "Open queue"
        caption: "Clear open tickets before they age out of SLA"
        icon: "inbox"
        state: warning
      - title: "AI classifications"
        caption: "Review confidence before routing"
        icon: "sparkles"
        state: accent
      - title: "Priority assessments"
        caption: "High-severity items surface on the priority desk"
        icon: "alert-triangle"
        state: positive

  # WI D: kanban family — open pipeline board
  open_board:
    source: Ticket
    filter: status != closed
    display: kanban
    group_by: status
    sort: created_at desc
    action: ticket_detail
    empty: "No open tickets"

  # WI D: chart family — ticket status mix
  status_mix:
    source: Ticket
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No tickets yet"

# WI L: agent default landing — aim for ≥5–6 regions.
workspace ticket_management "Ticket Management":
  purpose: "Manage individual tickets"
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

  ticket_queue:
    source: Ticket
    filter: status != closed
    sort: created_at desc
    limit: 20
    display: queue
    action: ticket_detail
    empty: "No open tickets in the system"

  open_only:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 15
    display: queue
    action: ticket_detail
    empty: "No brand-new open tickets"

  # WI D: kanban family — pipeline board (not list pad)
  pipeline_board:
    source: Ticket
    filter: status != closed
    display: kanban
    group_by: status
    sort: created_at desc
    action: ticket_detail
    empty: "No open tickets"

  # WI D: context family — classification trail
  classification_trail:
    source: TicketClassification
    sort: classified_at desc
    limit: 15
    display: timeline
    empty: "No classifications yet"

  # WI D: chart family — priority assessment mix
  priority_mix:
    source: PriorityAssessment
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(PriorityAssessment)
    empty: "No priority assessments yet"

# Third product workspace (WI density D): classification-first desk so list
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

  latest:
    source: TicketClassification
    sort: classified_at desc
    limit: 25
    display: queue
    empty: "No classifications yet"

  # WI D: grid family for open ticket cards
  open_tickets:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open tickets"

  # WI D: context family — classification timeline
  class_trail:
    source: TicketClassification
    sort: classified_at desc
    limit: 15
    display: timeline
    empty: "No classifications yet"

  # WI D: chart family — open ticket status mix
  open_status_mix:
    source: Ticket
    filter: status != closed
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No open tickets"

# Fourth product workspace (WI D): priority assessment desk.
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

  # WI D: grid family for open work cards
  open_work:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open tickets"

  # WI D: context family — assessment trail
  assessment_trail:
    source: PriorityAssessment
    sort: priority desc
    limit: 15
    display: timeline
    empty: "No priority assessments yet"

  # WI D: chart family — priority distribution
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

# Fifth product desk (WI D): 2 lists floor dens ~0.33 with 4 full desks — need 5.
workspace category_ops "Category Ops":
  purpose: "Category pressure — AI category mix and open work without warehouse CRUD"
  access: persona(supervisor, support_agent, admin)

  category_pulse:
    source: TicketClassification
    display: metrics
    aggregate:
      classifications: count(TicketClassification)
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
    tones:
      open: warning
      classifications: accent
      in_progress: positive

  # WI D: queue family — latest classifications first
  class_queue:
    source: TicketClassification
    sort: classified_at desc
    limit: 20
    display: queue
    empty: "No classifications yet"

  # WI D: grid family — active ticket cards
  active_grid:
    source: Ticket
    filter: status = open or status = in_progress
    sort: updated_at desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No active tickets"

  # WI D: context family — classification trail
  category_trail:
    source: TicketClassification
    sort: classified_at desc
    limit: 15
    display: timeline
    empty: "No classifications yet"

  # WI D: chart family — category mix
  category_mix:
    source: TicketClassification
    display: bar_chart
    group_by: category
    aggregate:
      count: count(TicketClassification)
    empty: "No classifications to chart"

# Sixth product desk (WI D): skip invoice_ops desk-cap; densify llm_ticket_classifier.
workspace sentiment_ops "Sentiment Ops":
  purpose: "Sentiment pressure — frustrated and negative classifications without warehouse CRUD"
  access: persona(supervisor, support_agent, admin)

  sentiment_pulse:
    source: TicketClassification
    display: metrics
    aggregate:
      classifications: count(TicketClassification)
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
    tones:
      open: warning
      classifications: accent
      in_progress: positive

  # WI D: queue family — latest classifications first
  class_queue:
    source: TicketClassification
    sort: classified_at desc
    limit: 20
    display: queue
    empty: "No classifications yet"

  # WI D: grid family — open ticket cards
  open_grid:
    source: Ticket
    filter: status = open or status = in_progress
    sort: updated_at desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No active tickets"

  # WI D: context family — classification trail
  sentiment_trail:
    source: TicketClassification
    sort: classified_at desc
    limit: 15
    display: timeline
    empty: "No classifications yet"

  # WI D: chart family — sentiment mix
  sentiment_mix:
    source: TicketClassification
    display: bar_chart
    group_by: sentiment
    aggregate:
      count: count(TicketClassification)
    empty: "No classifications to chart"

# Seventh product desk (WI D): skip invoice_ops desk-cap; densify llm_ticket_classifier.
workspace open_ops "Open Ops":
  purpose: "Intake pressure — open tickets awaiting AI classification without warehouse CRUD"
  access: persona(supervisor, support_agent, admin)

  open_pulse:
    source: Ticket
    display: metrics
    aggregate:
      open: count(Ticket where status = open)
      in_progress: count(Ticket where status = in_progress)
      classified: count(TicketClassification)
    tones:
      open: warning
      in_progress: accent
      classified: positive

  # WI D: queue family — open tickets first
  open_queue:
    source: Ticket
    filter: status = open
    sort: updated_at desc
    limit: 20
    display: queue
    action: ticket_detail
    empty: "No open tickets"

  # WI D: grid family — open cards
  open_grid:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 15
    display: grid
    action: ticket_detail
    empty: "No open tickets"

  # WI D: context family — recent open trail
  open_trail:
    source: Ticket
    filter: status = open or status = in_progress
    sort: updated_at desc
    limit: 15
    display: timeline
    action: ticket_detail
    empty: "No active ticket activity yet"

  # WI D: chart family — ticket status mix
  status_mix:
    source: Ticket
    filter: status != closed
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Ticket)
    empty: "No open tickets to chart"


# =============================================================================
# Personas
# =============================================================================

persona support_agent "Support Agent":
  description: "Handle support tickets and view AI classifications"
  goals: "View and manage tickets", "Review AI classifications", "Update ticket status"
  proficiency: intermediate
  default_workspace: ticket_management
  default_route: "/tickets"
  # WI N: job desks first — not auto entity-list soup
  uses nav agent_nav

persona supervisor "Support Supervisor":
  description: "Monitor ticket flow and AI classification accuracy"
  goals: "Monitor ticket classifications", "Review AI accuracy", "Manage team workload"
  proficiency: expert
  default_workspace: support_dashboard
  default_route: "/dashboard"
  uses nav supervisor_nav

# Curated sidebars: workspace destinations only (WI N).
nav agent_nav:
  group "My work":
    ticket_management
    classification_desk
    priority_desk
    category_ops
    sentiment_ops
    open_ops
    support_dashboard

nav supervisor_nav:
  group "Oversight":
    support_dashboard
    classification_desk
    priority_desk
    category_ops
    sentiment_ops
    open_ops
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
