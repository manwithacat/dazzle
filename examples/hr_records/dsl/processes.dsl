# Process priors from domain process_candidates (improve domain_lifecycle_priors).
# Candidate: assignment — manager acknowledges employment handoff (domain
# entity_hint "Department" is chrome; gold handoff is Employment on create).

module hr_records.processes

use hr_records.core

# Manager acknowledges a new employment row so team ownership is explicit —
# multi-persona handoff (hr_admin creates; manager owns the report).
# No status enum on Employment; trigger on created (grammar: created|status).
process employment_manager_assignment "Manager acknowledges new employment":
  # Domain process_candidate `assignment` re-grounded on Employment (Person
  # holds role via Employment; Department alone has no status lifecycle).
  trigger:
    when: entity Employment created

  input:
    employment_id: uuid required

  steps:
    - step manager_ack:
        human_task:
          title: "Acknowledge new team employment"
          assignee_role: manager
          form:
            acknowledged: bool required
            notes: text
          timeout: 4h

  timeout: 48h
