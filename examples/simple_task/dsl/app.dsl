# DAZZLE Simple Task Manager
# A minimal example demonstrating DAZZLE DSL basics with v0.2 features

module simple_task.core

app simple_task "Simple Task Manager"

# Core entity with common patterns
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

# List view - the main task overview
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
    purpose: "View and manage all tasks at a glance"
    sort: created_at desc
    filter: status, priority
    search: title, description, assigned_to
    empty: "No tasks yet. Create your first task!"

    attention warning:
      when: due_date < today and status != done
      message: "Overdue task"

    attention notice:
      when: priority = high and status = todo
      message: "High priority - needs attention"

# Detail view - individual task
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

# Create form
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
    purpose: "Add a new task to track"

# Edit form
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
    purpose: "Update task details and status"

# Workspaces - compose regions for user-centric views
workspace dashboard "Task Dashboard":
  purpose: "Overview of all tasks with key metrics"

  metrics:
    source: Task
    aggregate:
      total: count(Task)
      todo: count(Task where status = todo)
      in_progress: count(Task where status = in_progress)
      done: count(Task where status = done)

  overdue:
    source: Task
    filter: due_date < today and status != done
    sort: due_date asc
    limit: 5
    display: list
    action: task_edit
    empty: "No overdue tasks!"

  high_priority:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc
    limit: 5
    display: list
    action: task_edit
    empty: "No high priority tasks pending"

  recent:
    source: Task
    sort: created_at desc
    limit: 10
    display: list
    action: task_detail

workspace my_work "My Work":
  purpose: "Personal task view for assigned work"

  my_in_progress:
    source: Task
    filter: status = in_progress
    sort: priority desc, due_date asc
    limit: 10
    display: list
    action: task_edit
    empty: "No tasks in progress"

  my_todo:
    source: Task
    filter: status = todo
    sort: priority desc, due_date asc
    limit: 10
    display: list
    action: task_edit
    empty: "No pending tasks"

  my_completed:
    source: Task
    filter: status = done
    sort: updated_at desc
    limit: 5
    display: list
    empty: "No completed tasks yet"
