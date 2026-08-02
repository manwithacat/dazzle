# Journey-bound stories for project_tracker agent-first dogfood.
# Warehouse lists alone are not enough — open-via + hubs must prove green.

module project_tracker.stories

story ST-001 "Member browses projects and opens a project hub":
  status: accepted
  executed_by: surface.project_list
  persona: member
  trigger: user_click
  entities: [Project, User]
  given:
    - "Member has list permission on Project"
  then:
    - "Member sees the project list"
    - "Row open hops to Project detail with task queue and milestone pull queue (not status cards)"
    - "Project rows dual-open Project via id | User via owner (project hub first, owner teammate hub second)"

story ST-002 "Member works the task board with project context hops":
  status: accepted
  executed_by: surface.task_list
  persona: member
  trigger: user_click
  entities: [Task, Project]
  given:
    - "Member has list permission on Task"
  then:
    - "Member sees tasks scoped to self (member scope)"
    - "Row triple-opens Task via id | Project via parent_project | User via assigned_to (task hub first, project then assignee teammate — not project-only orphan hop)"

story ST-003 "Member opens a task hub with discussion and files":
  status: accepted
  executed_by: surface.task_detail
  persona: member
  trigger: user_click
  entities: [Task, Comment, Attachment]
  given:
    - "Task exists and is readable"
  then:
    - "Task hub shows status strip, ownership, discussion, and files"
    - "From task_list triple-open, the Task via id hop lands this hub (discussion queue + files)"
    - "Comment list triple-opens Comment via id | Task via task | User via author (note hub first, task then author)"
    - "Attachment list triple-opens Attachment via id | Task via task | User via uploaded_by (file hub first, task then uploader)"

story ST-004 "Manager reviews project portfolio":
  status: accepted
  executed_by: surface.project_list
  persona: manager
  trigger: user_click
  entities: [Project, User]
  given:
    - "Manager has list permission on Project"
  then:
    - "Manager sees all projects"
    - "Opening a project shows related tasks and milestones as pull queues"
    - "Project rows dual-open Project via id | User via owner (project hub first, owner teammate hub second)"

story ST-005 "Member follows an assignee hop to a teammate hub":
  status: accepted
  executed_by: surface.user_detail
  persona: member
  trigger: user_click
  entities: [User, Task, Project]
  given:
    - "Task assigned_to ref resolves to /app/user/{id}"
    - "User has read permission"
  then:
    - "Teammate hub shows identity, role strip, assigned work, and owned projects"
    - "No 404 on assignee context hop from kanban/queue"
