# Sample DAZZLE DSL File
# This file demonstrates syntax highlighting features

module myapp.core

app myapp "My Application"

# Entity definition with various field types
entity User "User":
  id: uuid pk
  email: str(255) required unique
  name: str(200) required
  age: int
  bio: text
  is_active: bool
  created_at: datetime auto_add
  updated_at: datetime auto_update

# Entity with enum and foreign key
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high,critical]=medium
  assigned_to: ref User
  created_by: ref User required
  due_date: date
  created_at: datetime auto_add
  updated_at: datetime auto_update

# Surface with list mode
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assigned To"
    field created_at "Created"

# Surface with view mode
surface task_detail "Task Detail":
  uses entity Task
  mode: view

  section main "Task Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assigned To"
    field created_by "Created By"
    field due_date "Due Date"
    field created_at "Created"
    field updated_at "Updated"

# Surface with create mode
surface task_create "Create Task":
  uses entity Task
  mode: create

  section main "New Task":
    field title "Title"
    field description "Description"
    field priority "Priority"
    field due_date "Due Date"

# Surface with edit mode
surface task_edit "Edit Task":
  uses entity Task
  mode: edit

  section main "Edit Task":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assigned To"
    field due_date "Due Date"
