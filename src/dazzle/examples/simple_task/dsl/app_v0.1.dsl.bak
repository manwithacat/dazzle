# Module declaration - defines the Python package name
module simple_task.core

# Application definition - sets project name and display title
app simple_task "Simple Task Manager"

# Entity: defines a data model
# Entities become database tables, API endpoints, and admin interfaces
entity Task "Task":
  # Primary key - every entity needs one
  id: uuid pk

  # String fields with max length
  # 'required' means the field cannot be null
  title: str(200) required

  # Text field - unlimited length (becomes TextField in Django)
  description: text

  # Enum field - restricts values to a defined set
  # Default value is 'todo' (specified after '=')
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium

  # Auto fields - managed automatically by the system
  created_at: datetime auto_add      # Set once on creation
  updated_at: datetime auto_update   # Updated on every save

# Surface: defines a user interface or API view
# mode: list - displays multiple records in a table/list format
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    # Each field line maps an entity field to a display label
    field title "Title"
    field status "Status"
    field priority "Priority"

# mode: view - displays a single record (read-only)
surface task_detail "Task Detail":
  uses entity Task
  mode: view

  section main "Task Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field created_at "Created"
    field updated_at "Updated"

# mode: create - form for creating new records
# Notice: we don't include auto_add/auto_update fields or the ID
surface task_create "Create Task":
  uses entity Task
  mode: create

  section main "New Task":
    field title "Title"
    field description "Description"
    field priority "Priority"

# mode: edit - form for updating existing records
surface task_edit "Edit Task":
  uses entity Task
  mode: edit

  section main "Edit Task":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
