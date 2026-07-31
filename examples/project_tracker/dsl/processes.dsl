# Process seeds from domain process_candidates (improve domain_lifecycle_priors).
# Candidate: escalation — member work escalates to manager at review gate.

module project_tracker.processes

use project_tracker.core

# Manager reviews tasks that leave in_progress and enter the review queue —
# multi-persona handoff that status transitions alone do not encode.
process task_review_escalation "Manager review of tasks in review":
  # Domain process_candidate `escalation`: worker escalates to manager;
  # gold Task lifecycle uses review as the manager gate (no blocked status).
  trigger:
    when: entity Task status -> review

  input:
    task_id: uuid required

  steps:
    - step manager_review:
        human_task:
          title: "Review task ready for acceptance"
          assignee_role: manager
          form:
            accepted: bool required
            notes: text
          timeout: 4h

  timeout: 48h
