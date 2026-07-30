# Process densify from domain process_candidates (improve domain_lifecycle_priors).
# Candidate: escalation — agent/manager handoff when SLA risk or critical work.

module support_tickets.processes

use support_tickets.core

# Manager reviews critical tickets that enter the queue — multi-persona handoff
# that status transitions alone do not encode (agent works, manager oversees).
process critical_ticket_escalation "Escalate ticket start to manager":
  # Domain process_candidate `escalation`: agent works the queue; manager
  # acknowledges when work starts (entity triggers only allow status/created —
  # priority field triggers are not in the grammar yet).
  trigger:
    when: entity Ticket status -> in_progress

  input:
    ticket_id: uuid required

  steps:
    - step manager_review:
        human_task:
          title: "Review in-progress ticket"
          assignee_role: manager
          form:
            acknowledged: bool required
            notes: text
          timeout: 4h

  timeout: 24h
