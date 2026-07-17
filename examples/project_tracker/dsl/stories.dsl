# Journey-bound stories for project_tracker agent-first dogfood.
# Warehouse lists alone are not enough — open-via + hubs must prove green.

module project_tracker.stories

story ST-001 "Member browses projects and opens a project hub":
  status: accepted
  executed_by: surface.project_list
  persona: member
  trigger: user_click
  entities: [Project]
  given:
    - "Member has list permission on Project"
  then:
    - "Member sees the project list"
    - "Row open hops to Project detail with tasks and milestones"

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
    - "Row open hops to the parent Project overview hub"

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

story ST-004 "Manager reviews project portfolio":
  status: accepted
  executed_by: surface.project_list
  persona: manager
  trigger: user_click
  entities: [Project]
  given:
    - "Manager has list permission on Project"
  then:
    - "Manager sees all projects"
    - "Opening a project shows related tasks and milestones"
