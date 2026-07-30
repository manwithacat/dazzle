# Process densify from domain process_candidates (improve domain_lifecycle_priors).
# Candidate: assignment — manager assigns active devices to field testers.

module fieldtest_hub.processes

use fieldtest_hub.core

# Manager confirms tester ownership when a device leaves prototype and becomes
# field-ready. Status transitions alone do not encode the multi-persona handoff
# (engineer promotes firmware readiness; manager owns field assignment).
process device_tester_assignment "Assign active device to field tester":
  # Domain process_candidate `assignment`: manager assigns Device to a worker
  # (tester). Entity triggers allow status/created only — not assigned_tester_id.
  trigger:
    when: entity Device status -> active

  input:
    device_id: uuid required

  steps:
    - step manager_assign:
        human_task:
          title: "Assign field tester for active device"
          assignee_role: manager
          form:
            assignment_confirmed: bool required
            notes: text
          timeout: 4h

  timeout: 48h
