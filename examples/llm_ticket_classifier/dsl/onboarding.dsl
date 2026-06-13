module llm_ticket_classifier.guides

use llm_ticket_classifier

# Per-persona orientation for the LLM ticket-triage tool.
#   - support_agent: work the incoming ticket queue
#   - supervisor:    monitor how the AI is classifying tickets
# This app is view-centric (the AI does the triage on ticket creation),
# so these guides orient rather than drive actions. Targets are
# surfaces; concordance is enforced at `dazzle validate` time.

# ─── Support Agent journey ────────────────────────────────────────

guide support_agent_onboarding "Work the ticket queue":
  audience: persona = support_agent

  step your_queue:
    kind: spotlight
    target: surface.ticket_list
    title: "Your ticket queue"
    body: "Every incoming ticket lands here, newest first. Filter by status to focus on what's still open."
    placement: center
    complete_on: dismiss

  step open_ticket:
    kind: popover
    target: surface.ticket_detail
    title: "Open a ticket for the full picture"
    body: "The detail view shows the customer's message and where it stands — open one to start working it."
    placement: bottom
    complete_on: dismiss

  step_order: [your_queue, open_ticket]

  on_complete:
    redirect: surface.ticket_list

# ─── Supervisor journey ───────────────────────────────────────────

guide supervisor_onboarding "Monitor the AI's triage":
  audience: persona = supervisor

  step ai_read:
    kind: spotlight
    target: surface.classification_list
    title: "See how the AI triaged each ticket"
    body: "Every ticket is auto-classified by category, priority, and sentiment. Scan the latest to spot trends."
    placement: center
    complete_on: dismiss

  step balance_load:
    kind: inline_card
    target: surface.ticket_list
    title: "Keep an eye on the queue"
    body: "Cross-check the live ticket list against the AI's reads to balance the team's workload."
    complete_on: dismiss

  step_order: [ai_read, balance_load]

  on_complete:
    redirect: surface.classification_list
