# Journey-bound stories for llm_ticket_classifier agent-first dogfood.
# LLM intents are the product differentiator — ticket hubs must surface
# classifications as related work, not leave agents on flat warehouse lists.

module llm_ticket_classifier.stories

story ST-001 "Support agent works the open ticket queue":
  status: accepted
  executed_by: surface.ticket_list
  persona: support_agent
  trigger: user_click
  entities: [Ticket]
  given:
    - "Support agent is on the ticket_management workspace"
    - "Open tickets exist in the queue"
  then:
    - "Agent sees tickets sorted by created_at with status filter"
    - "Opening a ticket row hops to the ticket detail hub"

story ST-002 "Support agent opens ticket hub with AI classifications":
  status: accepted
  executed_by: surface.ticket_detail
  persona: support_agent
  trigger: user_click
  entities: [Ticket, TicketClassification]
  given:
    - "Ticket exists and is readable"
  then:
    - "Ticket hub shows summary, lifecycle strip, and related AI classifications"
    - "Agent can edit status from the ticket context"

story ST-003 "Supervisor reviews classification trail":
  status: accepted
  executed_by: surface.classification_list
  persona: supervisor
  trigger: user_click
  entities: [TicketClassification, Ticket]
  given:
    - "Supervisor is on the support_dashboard workspace"
    - "TicketClassifications exist from LLM runs"
  then:
    - "Supervisor sees classifications sorted by classified_at"
    - "Opening a classification row hops to the parent Ticket hub"

story ST-004 "Support agent captures a new ticket for auto-classify":
  status: accepted
  executed_by: surface.ticket_create
  persona: support_agent
  trigger: form_submitted
  entities: [Ticket]
  given:
    - "Support agent has create permission on Ticket"
  then:
    - "New Ticket is saved with status open"
    - "classify_ticket LLM intent is eligible to run on entity created"

story ST-005 "Support agent transitions ticket lifecycle":
  status: accepted
  executed_by: surface.ticket_edit
  persona: support_agent
  trigger: form_submitted
  entities: [Ticket]
  given:
    - "Ticket.status is open or in_progress"
  then:
    - "Agent can update status on the lifecycle strip fields"
    - "Ticket remains reachable from the open queue until closed"

story ST-006 "Agent inspects a single classification run":
  status: accepted
  executed_by: surface.classification_detail
  persona: support_agent
  trigger: user_click
  entities: [TicketClassification]
  given:
    - "TicketClassification exists with category, priority, sentiment"
  then:
    - "Classification hub shows triage labels, confidence strip, and suggested response"
    - "llm_job_id remains visible for auditability"
