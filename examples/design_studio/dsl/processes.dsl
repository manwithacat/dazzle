# Process densify from domain process_candidates (improve domain_lifecycle_priors).
# Candidate: assignment — campaign activation hands work to a designer.

module design_studio.processes

use design_studio.core

# Designer confirms ownership when a Campaign leaves planning and goes active —
# multi-persona handoff that status transitions alone do not encode.
process campaign_activation_assignment "Designer claims active campaign":
  # Domain process_candidate `assignment`: manager/worker assignment maps here
  # to designer (no member persona); trigger on planning→active.
  trigger:
    when: entity Campaign status -> active

  input:
    campaign_id: uuid required

  steps:
    - step designer_claim:
        human_task:
          title: "Confirm designer ownership for active campaign"
          assignee_role: designer
          form:
            ownership_confirmed: bool required
            notes: text
          timeout: 4h

  timeout: 48h
