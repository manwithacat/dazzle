# Vocabulary Demo App
# Demonstrates @use directives for app-local vocabulary

module task_tracker.core

app task_tracker "Task Tracker with Vocabulary"

# Define User entity (standard)
entity User "User":
  id: uuid pk
  name: str(200) required
  email: email unique?
  created_at: datetime auto_add
  updated_at: datetime auto_update

# Define Task entity
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  assigned_to: ref User
  created_at: datetime auto_add
  updated_at: datetime auto_update

# Generate complete CRUD surfaces using vocabulary
@use crud_surface_set(entity_name=Task, title_field=title)

# Also generate CRUD for User
@use crud_surface_set(entity_name=User, title_field=name)
