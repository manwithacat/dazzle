# LLM Ticket Classifier - Example App
# Demonstrates LLM Jobs as First-Class Events (Issue #33)
#
# This example shows how to:
# 1. Define LLM models with provider, tier, and cost configuration
# 2. Configure global LLM settings (artifact store, logging, rate limits)
# 3. Create LLM intents for classification tasks
# 4. Use retry and PII policies for production readiness

module llm_ticket_classifier
app ticket_classifier "Support Ticket Classifier"


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


# =============================================================================
# LLM Intents (Job Definitions)
# =============================================================================

# Simple category classification
llm_intent classify_ticket "Classify Support Ticket":
  model: claude_haiku
  prompt: "Classify this support ticket into exactly one category: billing, technical, feature_request, account, or other.\n\nTicket:\n{{ input.description }}\n\nRespond with only the category name."
  timeout: 15

# Priority assessment with structured output
llm_intent assess_priority "Assess Ticket Priority":
  model: claude_sonnet
  prompt: "Assess the priority of this support ticket. Consider urgency, business impact, and customer sentiment.\n\nTicket:\n{{ input.description }}\n\nRespond with JSON: {\"priority\": \"low|medium|high|critical\", \"reasoning\": \"brief explanation\"}"
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
  prompt: "Analyze the customer sentiment in this support ticket.\n\nTicket:\n{{ input.description }}\n\nRespond with JSON: {\"sentiment\": \"positive|neutral|negative|frustrated\", \"confidence\": 0.0-1.0}"
  timeout: 10

# Generate response suggestion
llm_intent suggest_response "Suggest Response":
  model: claude_sonnet
  prompt: "Based on this support ticket and its classification, suggest a helpful response template.\n\nTicket:\n{{ input.description }}\n\nCategory: {{ input.category }}\nPriority: {{ input.priority }}\n\nProvide a professional, empathetic response template."
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
  id: uuid pk
  subject: str(200) required
  description: text required
  customer_email: str(100) required
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
  section main:
    field subject "Subject"
    field customer_email "Customer"
    field status "Status"
    field created_at "Created"

surface ticket_detail "Ticket Detail":
  uses entity Ticket
  mode: view
  section info:
    field subject "Subject"
    field description "Description"
    field customer_email "Customer Email"
    field status "Status"
  section timestamps:
    field created_at "Created"
    field updated_at "Updated"

surface classification_list "Classifications":
  uses entity TicketClassification
  mode: list
  section main:
    field ticket "Ticket"
    field category "Category"
    field priority "Priority"
    field sentiment "Sentiment"
    field classified_at "Classified At"


# =============================================================================
# Workspaces
# =============================================================================

workspace support_dashboard "Support Dashboard":
  purpose: "Monitor and classify support tickets"

  tickets:
    source: Ticket
    filter: status = open
    sort: created_at desc
    limit: 20
    display: list
    empty: "No open tickets"

  classifications:
    source: TicketClassification
    sort: classified_at desc
    limit: 20
    display: list
    empty: "No classifications yet"

workspace ticket_management "Ticket Management":
  purpose: "Manage individual tickets"

  all_tickets:
    source: Ticket
    sort: created_at desc
    display: list
    action: ticket_detail
    empty: "No tickets in the system"


# =============================================================================
# Personas
# =============================================================================

persona support_agent "Support Agent":
  description: "Handle support tickets and view AI classifications"
  goals: "View and manage tickets", "Review AI classifications", "Update ticket status"
  proficiency: intermediate
  default_workspace: ticket_management
  default_route: "/tickets"

persona supervisor "Support Supervisor":
  description: "Monitor ticket flow and AI classification accuracy"
  goals: "Monitor ticket classifications", "Review AI accuracy", "Manage team workload"
  proficiency: expert
  default_workspace: support_dashboard
  default_route: "/dashboard"


# =============================================================================
# Scenarios - demo states for the Dazzle Bar
# =============================================================================

scenario empty "Empty State":
  description: "Fresh install with no tickets - test onboarding"

  for persona support_agent:
    start_route: "/tickets"

  for persona supervisor:
    start_route: "/dashboard"

scenario active_tickets "Active Tickets":
  description: "Several tickets awaiting classification"

  for persona support_agent:
    start_route: "/tickets"

  for persona supervisor:
    start_route: "/dashboard"

  demo:
    Ticket:
      - subject: "Cannot login to my account", description: "I forgot my password and reset link is not working", customer_email: "user1@example.com", status: open
      - subject: "Billing question", description: "Why was I charged twice this month?", customer_email: "user2@example.com", status: open
      - subject: "Feature request for dark mode", description: "Would love to have a dark mode option in the app", customer_email: "user3@example.com", status: open
