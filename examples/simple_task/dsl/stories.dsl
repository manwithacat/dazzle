story ST-006 "Administrator creates a new Team Member":
  status: accepted
  narrative_only: true
  persona: admin
  trigger: form_submitted
  entities: [User]
  given:
    - "Administrator has permission to create User"
  then:
    - "New User is saved to database"
    - "Administrator sees confirmation message"

story ST-007 "Administrator creates a new Task":
  status: accepted
  narrative_only: true
  persona: admin
  trigger: form_submitted
  entities: [Task]
  given:
    - "Administrator has permission to create Task"
  then:
    - "New Task is saved to database"
    - "Administrator sees confirmation message"

story ST-008 "Administrator changes Task from todo to in_progress":
  status: accepted
  narrative_only: true
  persona: admin
  trigger: status_changed
  entities: [Task]
  given:
    - "Task.status is 'todo'"
  then:
    - "Task.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-009 "Administrator changes Task from in_progress to review":
  status: accepted
  narrative_only: true
  persona: admin
  trigger: status_changed
  entities: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'review'"
    - "Timestamp is recorded"

story ST-010 "Administrator changes Task from in_progress to todo":
  status: accepted
  narrative_only: true
  persona: admin
  trigger: status_changed
  entities: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'todo'"
    - "Timestamp is recorded"

story ST-011 "Administrator creates a new Task Comment":
  status: accepted
  narrative_only: true
  persona: admin
  trigger: form_submitted
  entities: [TaskComment]
  given:
    - "Administrator has permission to create TaskComment"
  then:
    - "New TaskComment is saved to database"
    - "Administrator sees confirmation message"

story ST-012 "Administrator views all tasks across organization":
  persona: admin
  trigger: user_click
  entities: [Task]
  given:
    - "Administrator has list permission on Task"
  then:
    - "Administrator sees every Task regardless of assignee"
    - "Task list is sortable by priority, status, due_date"

story ST-013 "Administrator configures team settings":
  persona: admin
  trigger: user_click
  entities: [User]
  given:
    - "Administrator has list+update permission on User"
  then:
    - "Administrator sees the full team roster"
    - "Administrator can change a Team Member's role or department"

story ST-014 "Administrator views system-wide analytics":
  persona: admin
  trigger: user_click
  entities: [Task, User]
  given:
    - "Administrator is on the admin dashboard workspace"
  then:
    - "Administrator sees aggregate counts of Tasks by status"
    - "Administrator sees team velocity metrics"

story ST-015 "Team Manager views all tasks for team":
  status: accepted
  executed_by: surface.task_list
  persona: manager
  trigger: user_click
  entities: [Task]
  given:
    - "Team Manager has list permission on Task"
  then:
    - "Team Manager sees every Task assigned within their team"
    - "Task list is sortable by priority, status, due_date"
    - "Row open hops to the assignee overview (User via assigned_to)"

story ST-016 "Team Manager views unassigned tasks":
  status: accepted
  executed_by: surface.task_list
  persona: manager
  trigger: user_click
  entities: [Task]
  given:
    - "Team Manager is on the team_overview workspace"
  then:
    - "Team Manager sees an unassigned queue of Tasks where assigned_to is null"
    - "Team Manager can open a Task from the queue to assign it"

story ST-017 "Team Manager assigns a task to a Team Member":
  persona: manager
  status: accepted
  executed_by: process.task_auto_assignment
  trigger: form_submitted
  entities: [Task, User]
  given:
    - "Task has no assignee"
    - "Team Manager has update permission on Task"
  then:
    - "Task.assigned_to is set to the chosen Team Member"
    - "Team Member sees the new Task in their my_work view"

story ST-018 "Team Manager reviews tasks awaiting review":
  status: accepted
  executed_by: surface.task_list
  persona: manager
  trigger: user_click
  entities: [Task]
  given:
    - "Team Manager is on the team_overview workspace"
    - "Tasks exist with status review"
  then:
    - "Team Manager sees the needs_review queue sorted by updated_at"
    - "Team Manager can approve a Task to done or send it back to in_progress"

story ST-019 "Team Member updates own task status":
  status: accepted
  executed_by: surface.task_edit
  persona: member
  trigger: status_changed
  entities: [Task]
  given:
    - "Task.assigned_to = current Team Member"
    - "Team Member has update permission on Task"
  then:
    - "Task.status transitions through declared state machine"
    - "Updated timestamp is recorded"

story ST-020 "Team Member views own tasks":
  status: accepted
  executed_by: surface.task_list
  persona: member
  trigger: user_click
  entities: [Task]
  given:
    - "Team Member is on the my_work workspace"
  then:
    - "Team Member sees personal metrics and WIP/todo queues for assigned work"
    - "Team Member sees only Tasks scoped to self"

story ST-021 "Team Manager opens assignee overview from the task board":
  status: accepted
  executed_by: surface.user_detail
  persona: manager
  trigger: user_click
  entities: [Task, User]
  given:
    - "Team Manager is on the task list"
    - "A Task has assigned_to set"
  then:
    - "Clicking the row opens the Team Member overview hub"
    - "Hub shows identity, role strip, and related open work"
