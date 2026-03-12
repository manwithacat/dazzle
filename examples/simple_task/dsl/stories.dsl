story ST-001 "Administrator creates a new Team Member":
  actor: Administrator
  trigger: form_submitted
  scope: [User]
  given:
    - "Administrator has permission to create User"
  then:
    - "New User is saved to database"
    - "Administrator sees confirmation message"

story ST-002 "Administrator creates a new Task":
  actor: Administrator
  trigger: form_submitted
  scope: [Task]
  given:
    - "Administrator has permission to create Task"
  then:
    - "New Task is saved to database"
    - "Administrator sees confirmation message"

story ST-003 "Administrator changes Task from todo to in_progress":
  actor: Administrator
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'todo'"
  then:
    - "Task.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-004 "Administrator changes Task from in_progress to review":
  actor: Administrator
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'review'"
    - "Timestamp is recorded"

story ST-005 "Administrator changes Task from in_progress to todo":
  actor: Administrator
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'todo'"
    - "Timestamp is recorded"

story ST-006 "Administrator creates a new Team Member":
  status: accepted
  actor: Administrator
  trigger: form_submitted
  scope: [User]
  given:
    - "Administrator has permission to create User"
  then:
    - "New User is saved to database"
    - "Administrator sees confirmation message"

story ST-007 "Administrator creates a new Task":
  status: accepted
  actor: Administrator
  trigger: form_submitted
  scope: [Task]
  given:
    - "Administrator has permission to create Task"
  then:
    - "New Task is saved to database"
    - "Administrator sees confirmation message"

story ST-008 "Administrator changes Task from todo to in_progress":
  status: accepted
  actor: Administrator
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'todo'"
  then:
    - "Task.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-009 "Administrator changes Task from in_progress to review":
  status: accepted
  actor: Administrator
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'review'"
    - "Timestamp is recorded"

story ST-010 "Administrator changes Task from in_progress to todo":
  status: accepted
  actor: Administrator
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'todo'"
    - "Timestamp is recorded"

story ST-011 "Administrator creates a new Task Comment":
  status: accepted
  actor: Administrator
  trigger: form_submitted
  scope: [TaskComment]
  given:
    - "Administrator has permission to create TaskComment"
  then:
    - "New TaskComment is saved to database"
    - "Administrator sees confirmation message"
