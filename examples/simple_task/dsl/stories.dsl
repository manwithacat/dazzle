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

story ST-012 "Administrator views all tasks across organization":
  actor: Administrator
  trigger: user_click
  scope: [Task]
  given:
    - "Administrator has list permission on Task"
  then:
    - "Administrator sees every Task regardless of assignee"
    - "Task list is sortable by priority, status, due_date"

story ST-013 "Administrator configures team settings":
  actor: Administrator
  trigger: user_click
  scope: [User]
  given:
    - "Administrator has list+update permission on User"
  then:
    - "Administrator sees the full team roster"
    - "Administrator can change a Team Member's role or department"

story ST-014 "Administrator views system-wide analytics":
  actor: Administrator
  trigger: user_click
  scope: [Task, User]
  given:
    - "Administrator is on the admin dashboard workspace"
  then:
    - "Administrator sees aggregate counts of Tasks by status"
    - "Administrator sees team velocity metrics"

story ST-015 "Team Manager views all tasks for team":
  actor: manager
  trigger: user_click
  scope: [Task]
  given:
    - "Team Manager has list permission on Task"
  then:
    - "Team Manager sees every Task assigned within their team"
    - "Task list is sortable by priority, status, due_date"

story ST-016 "Team Manager views unassigned tasks":
  actor: manager
  trigger: user_click
  scope: [Task]
  given:
    - "Team Manager is on the team overview workspace"
  then:
    - "Team Manager sees Tasks where assigned_to is null"
    - "Team Manager can click a Task to assign it"

story ST-017 "Team Manager assigns a task to a Team Member":
  actor: manager
  trigger: form_submitted
  scope: [Task, User]
  given:
    - "Task has no assignee"
    - "Team Manager has update permission on Task"
  then:
    - "Task.assigned_to is set to the chosen Team Member"
    - "Team Member sees the new Task in their my_work view"

story ST-018 "Team Manager reviews completed tasks":
  actor: manager
  trigger: user_click
  scope: [Task]
  given:
    - "Tasks exist with status review"
  then:
    - "Team Manager sees the review queue sorted by updated_at desc"
    - "Team Manager can approve a Task to done or send it back to in_progress"

story ST-019 "Team Member updates own task status":
  actor: member
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.assigned_to = current Team Member"
    - "Team Member has update permission on Task"
  then:
    - "Task.status transitions through declared state machine"
    - "Updated timestamp is recorded"

story ST-020 "Team Member views own tasks":
  actor: member
  trigger: user_click
  scope: [Task]
  given:
    - "Team Member is on the my_work workspace"
  then:
    - "Team Member sees only Tasks where assigned_to = self or created_by = self"
    - "Task list is grouped by status"
