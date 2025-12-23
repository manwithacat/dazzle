# Event Definitions for Team Task Manager
# Demonstrates DAZZLE event streaming capabilities (v0.18.0+)
#
# Events enable:
# - Audit trails for compliance
# - Real-time notifications
# - Analytics and reporting
# - Integration with external systems

module simple_task.events

# =============================================================================
# Event Model - Topics and Event Definitions
# =============================================================================

event_model:
  # Task lifecycle topic
  topic task_events:
    retention: 30
    partition_key: task_id

  # Notification events topic
  topic notification_events:
    retention: 7

  # Task created event
  event TaskCreated:
    topic: task_events
    fields:
      task_id: uuid required
      title: str required
      priority: str required
      created_by: uuid
      created_at: datetime required

  # Task status changed event
  event TaskStatusChanged:
    topic: task_events
    fields:
      task_id: uuid required
      old_status: str required
      new_status: str required
      changed_by: uuid
      changed_at: datetime required

  # Task assigned event
  event TaskAssigned:
    topic: task_events
    fields:
      task_id: uuid required
      previous_assignee: uuid
      new_assignee: uuid required
      assigned_by: uuid
      assigned_at: datetime required

  # Task overdue event
  event TaskOverdue:
    topic: task_events
    fields:
      task_id: uuid required
      due_date: date required
      days_overdue: int required
      assigned_to: uuid
      priority: str

  # Comment added event
  event CommentAdded:
    topic: task_events
    fields:
      comment_id: uuid required
      task_id: uuid required
      author_id: uuid required
      content_preview: str
      created_at: datetime required

# =============================================================================
# Event Subscriptions
# =============================================================================

# Notify assignee when task is assigned
subscribe task_events as assignment_notifier:
  on TaskAssigned:
    call service send_assignment_notification

# Track overdue tasks for escalation
subscribe task_events as overdue_tracker:
  on TaskOverdue:
    call service escalate_overdue_task
