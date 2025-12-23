# Messaging Channels for Team Task Manager
# Demonstrates DAZZLE messaging capabilities
#
# Messaging enables:
# - Email notifications to team members
# - Outbox pattern for reliable delivery
# - Template-based message content

module simple_task.messaging

# =============================================================================
# Message Schemas
# =============================================================================

message TaskAssignmentNotification "Task Assignment Email":
  to: email required
  subject: str(200) required
  task_title: str(200) required
  task_id: uuid required
  priority: str(20) required
  due_date: date
  assigned_by_name: str(100)
  task_url: str(500)

message TaskOverdueNotification "Overdue Task Alert":
  to: email required
  subject: str(200) required
  task_title: str(200) required
  task_id: uuid required
  days_overdue: int required
  priority: str(20) required
  manager_email: email

message TaskCompletedNotification "Task Completed Notification":
  to: email required
  subject: str(200) required
  task_title: str(200) required
  completed_by_name: str(100) required
  completion_notes: text

message CommentNotification "New Comment Alert":
  to: email required
  subject: str(200) required
  task_title: str(200) required
  comment_author: str(100) required
  comment_preview: str(200)
  task_url: str(500)

message DailyDigest "Daily Task Digest":
  to: email required
  subject: str(200) required
  tasks_assigned: int
  tasks_completed: int
  tasks_overdue: int
  high_priority_pending: int
  summary_html: text

# =============================================================================
# Notification Channel
# =============================================================================

channel notifications "Email Notifications":
  kind: email
  provider: auto

  config:
    from_address: "tasks@example.com"
    from_name: "Team Task Manager"
    reply_to: "noreply@example.com"

  send task_assigned:
    message: TaskAssignmentNotification

  send task_overdue:
    message: TaskOverdueNotification

  send comment_added:
    message: CommentNotification

# =============================================================================
# Digest Channel (Scheduled)
# =============================================================================

channel digests "Daily Digest Emails":
  kind: email
  provider: auto

  config:
    from_address: "digest@example.com"
    from_name: "Task Manager Digest"

  send daily_digest:
    message: DailyDigest

# =============================================================================
# Internal Queue (for async processing)
# =============================================================================

channel task_queue "Task Processing Queue":
  kind: queue
  provider: auto

  config:
    max_retries: 3
    retry_delay_seconds: 60
