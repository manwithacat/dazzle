# Domain Services for Team Task Manager
# Demonstrates DAZZLE service stubs for business logic
#
# Services define:
# - Input/output contracts
# - Business logic boundaries
# - Guarantees and invariants
# - Stub implementations for development

module simple_task.services

# =============================================================================
# Workload Services
# =============================================================================

service calculate_user_workload "Calculate User Workload":
  kind: domain_logic

  input:
    user_id: uuid required

  output:
    active_tasks: int
    urgent_tasks: int
    overdue_tasks: int
    workload_score: decimal

  guarantees:
    - "Workload score is between 0.0 and 1.0"
    - "Read-only operation, no side effects"

  stub: python

# =============================================================================
# Assignment Services
# =============================================================================

service auto_assign_task "Auto-assign Task to Best Candidate":
  kind: domain_logic

  input:
    task_id: uuid required
    department: str
    priority: str

  output:
    assigned_to: uuid
    reason: str
    confidence: decimal

  guarantees:
    - "Only assigns to active users"
    - "Considers current workload balance"

  stub: python

service find_overdue_tasks "Find All Overdue Tasks":
  kind: domain_logic

  input:
    as_of_date: date
    min_days_overdue: int

  output:
    count: int

  stub: python

# =============================================================================
# Notification Services
# =============================================================================

service send_assignment_notification "Send Task Assignment Notification":
  kind: integration

  input:
    task_id: uuid required
    assignee_id: uuid required
    assigned_by_id: uuid

  output:
    notification_sent: bool
    channel: str

  stub: python

service send_overdue_reminder "Send Overdue Task Reminder":
  kind: integration

  input:
    task_id: uuid required
    days_overdue: int required

  output:
    notifications_sent: int

  stub: python

# =============================================================================
# Escalation Services
# =============================================================================

service escalate_overdue_task "Escalate Overdue Task":
  kind: workflow

  input:
    task_id: uuid required
    escalation_level: int

  output:
    escalated_to: uuid
    action_taken: str
    notification_sent: bool

  guarantees:
    - "Task priority is increased if escalation_level >= 2"
    - "Manager is notified at all escalation levels"

  stub: python

# =============================================================================
# Analytics Services
# =============================================================================

service generate_team_report "Generate Team Performance Report":
  kind: domain_logic

  input:
    start_date: date required
    end_date: date required

  output:
    total_tasks_created: int
    total_tasks_completed: int
    average_completion_time_hours: decimal
    on_time_completion_rate: decimal

  stub: python
