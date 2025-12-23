# Temporal Processes for Team Task Manager
# Demonstrates DAZZLE durable workflow capabilities
#
# Processes enable:
# - Long-running workflows with durability
# - Automatic retries and error handling
# - Human-in-the-loop tasks
# - Scheduled background jobs

module simple_task.processes

# =============================================================================
# Task Auto-Assignment Process
# =============================================================================

process task_auto_assignment "Auto-Assign High Priority Tasks":
  trigger:
    when: entity Task created

  input:
    task_id: uuid required

  steps:
    - step find_candidate:
        service: auto_assign_task
        timeout: 30s
        retry:
          max_attempts: 3
          backoff: exponential

    - step notify_assignee:
        channel: notifications
        message: TaskAssignmentNotification

  timeout: 5m

# =============================================================================
# Task Escalation Process
# =============================================================================

process task_escalation "Escalate Overdue Task":
  trigger:
    when: signal task_overdue

  input:
    task_id: uuid required

  steps:
    - step level_1_notify:
        service: send_overdue_reminder
        timeout: 30s

    - step wait_for_action:
        wait: 24h

    - step level_2_escalate:
        service: escalate_overdue_task
        timeout: 1m

  timeout: 72h

# =============================================================================
# Human Task: Approval Flow
# =============================================================================

process urgent_task_approval "Urgent Task Approval":
  trigger:
    when: entity Task created

  input:
    task_id: uuid required

  steps:
    - step request_approval:
        human_task:
          title: "Approve Urgent Task"
          assignee_role: manager
          form:
            approved: bool required
            notes: text
          timeout: 4h

    - step notify_decision:
        channel: notifications
        message: TaskCompletedNotification

  timeout: 24h

# =============================================================================
# Daily Overdue Check Schedule
# =============================================================================

schedule daily_overdue_check "Daily Overdue Task Check":
  cron: "0 9 * * *"

  steps:
    - step find_overdue:
        service: find_overdue_tasks
        timeout: 1m

    - step escalate_tasks:
        service: escalate_overdue_task
        timeout: 30s

  timeout: 30m

# =============================================================================
# Weekly Report Schedule
# =============================================================================

schedule weekly_team_report "Weekly Team Report":
  cron: "0 9 * * MON"

  steps:
    - step generate_report:
        service: generate_team_report
        timeout: 5m

    - step send_digest:
        channel: digests
        message: DailyDigest

  timeout: 15m
