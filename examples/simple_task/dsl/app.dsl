# DAZZLE v0.2 - Simple Task Manager with UX Semantic Layer
# This version enhances the basic task manager with UX features

module simple_task.core

app simple_task "Simple Task Manager"

# Entity: Same as v0.1 (entities are unchanged)
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  due_date: date
  assigned_to: str(100)
  created_at: datetime auto_add
  updated_at: datetime auto_update

# Enhanced list surface with UX semantics
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assigned To"

  ux:
    purpose: "Track and manage team tasks efficiently"

    # Information needs
    show: title, status, priority, due_date, assigned_to
    sort: status asc, priority desc, due_date asc
    filter: status, priority, assigned_to
    search: title, description
    empty: "No tasks yet. Create your first task to get started!"

    # Attention signals
    attention critical:
      when: due_date < today and status != done
      message: "Overdue task"
      action: task_edit

    attention warning:
      when: priority = high and status = todo
      message: "High priority - start soon"
      action: task_edit

    attention notice:
      when: status = in_progress and days_since(updated_at) > 7
      message: "No updates for a week"
      action: task_detail

    # Persona variants
    for team_member:
      scope: assigned_to = current_user
      purpose: "Your personal task list"
      show: title, status, priority, due_date
      action_primary: task_edit

    for manager:
      scope: all
      purpose: "Team task oversight"
      show_aggregate: total_tasks, overdue_count, completion_rate
      action_primary: task_create

    for viewer:
      scope: all
      purpose: "View task progress"
      read_only: true

# Enhanced detail view with UX
surface task_detail "Task Detail":
  uses entity Task
  mode: view

  section main "Task Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assigned To"
    field created_at "Created"
    field updated_at "Updated"

  ux:
    purpose: "View complete task information"

    # Different detail levels for personas
    for team_member:
      scope: assigned_to = current_user
      action_primary: task_edit

    for manager:
      scope: all
      show_aggregate: related_tasks_count, blocker_count

# Create form with purpose
surface task_create "Create Task":
  uses entity Task
  mode: create

  section main "New Task":
    field title "Title"
    field description "Description"
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assigned To"

  ux:
    purpose: "Add a new task to the team backlog"

    # Auto-assignment for team members
    for team_member:
      # Pre-fill assigned_to with current user
      defaults:
        assigned_to: current_user

# Edit form with context
surface task_edit "Edit Task":
  uses entity Task
  mode: edit

  section main "Edit Task":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assigned To"

  ux:
    purpose: "Update task details and progress"

    # Limit status transitions based on role
    for team_member:
      scope: assigned_to = current_user
      # Can only change their own tasks

    for manager:
      scope: all
      # Can change any task

# NEW in v0.2: Task dashboard workspace
workspace task_dashboard "Task Dashboard":
  purpose: "Comprehensive task management overview"

  # My tasks region
  my_tasks:
    source: Task
    filter: assigned_to = current_user and status != done
    sort: priority desc, due_date asc
    limit: 10
    display: list
    action: task_edit
    empty: "No tasks assigned to you"

  # Overdue tasks region
  overdue:
    source: Task
    filter: due_date < today and status != done
    sort: due_date asc
    limit: 5
    display: list
    action: task_edit
    empty: "No overdue tasks!"

  # Team metrics
  metrics:
    source: Task
    aggregate:
      total_tasks: count(Task)
      completed: count(Task where status = done)
      in_progress: count(Task where status = in_progress)

  # Recent activity
  recent_activity:
    source: Task
    sort: updated_at desc
    limit: 10
    display: timeline
    empty: "No recent activity"

  # Workload distribution
  workload:
    source: Task
    filter: status != done
    sort: assigned_to asc
    limit: 20
    display: grid

  ux:
    # Dashboard variants for different roles
    for team_member:
      purpose: "Your personal task tracking"
      focus: my_tasks, overdue

    for manager:
      purpose: "Team performance and workload management"
      focus: metrics, workload, overdue

# NEW in v0.2: Personal workspace
workspace my_workspace "My Workspace":
  purpose: "Personal productivity hub"

  today_tasks:
    source: Task
    filter: assigned_to = current_user and status != done
    sort: priority desc
    limit: 10
    action: task_edit
    empty: "No tasks due today"

  high_priority:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc
    limit: 5
    action: task_edit
    empty: "No high priority tasks"

  my_stats:
    source: Task
    aggregate:
      total: count(Task)
      done: count(Task where status = done)
      pending: count(Task where status != done)

  ux:
    for team_member:
      purpose: "Focus on your daily priorities"
