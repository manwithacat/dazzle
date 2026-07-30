# Process densify from domain process_candidates (improve domain_lifecycle_priors).
# Candidate: triage — intake handoff before deep work (agent/manager → gold personas).

module llm_ticket_classifier.processes

use llm_ticket_classifier

# Supervisor reviews tickets that leave open and enter in_progress so triage is
# not an informal chat — multi-persona handoff (agent works; supervisor oversees).
process ticket_intake_triage "Supervisor reviews ticket intake":
  # Domain process_candidate `triage` on SupportTicket/Ticket; gold entity is Ticket.
  # Manager maps to supervisor; agent maps to support_agent.
  trigger:
    when: entity Ticket status -> in_progress

  input:
    ticket_id: uuid required

  steps:
    - step supervisor_triage:
        human_task:
          title: "Review in-progress ticket triage"
          assignee_role: supervisor
          form:
            triage_ok: bool required
            notes: text
          timeout: 4h

  timeout: 48h
