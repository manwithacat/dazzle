# DAZZLE Simple Task Manager
# A minimal example demonstrating DAZZLE DSL basics

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
    field description "Description"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assigned To"

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
