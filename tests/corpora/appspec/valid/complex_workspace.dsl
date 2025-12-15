# Complex workspace with regions and personas
module corpus.workspace
app workspace_app "Workspace App"

persona admin "Administrator":
  description: "System administrator with full access"
  default_workspace: admin_dashboard

persona user "Regular User":
  description: "Standard user with limited access"
  default_workspace: user_home

entity Task "Task":
  id: uuid pk
  title: str(200) required
  priority: enum[low,medium,high]=medium
  status: enum[todo,in_progress,done]=todo
  assigned_to: str(100) optional
  due_date: date optional

entity Report "Report":
  id: uuid pk
  title: str(200) required
  generated_at: datetime required
  content: text optional

surface task_kanban "Task Board":
  uses entity Task
  mode: list
  section main:
    field title "Task"
    field priority "Priority"
    field status "Status"
    field assigned_to "Assignee"

surface task_create "New Task":
  uses entity Task
  mode: create
  section main:
    field title "Title"
    field priority "Priority"
    field assigned_to "Assign To"
    field due_date "Due Date"

surface report_list "Reports":
  uses entity Report
  mode: list
  section main:
    field title "Report"
    field generated_at "Generated"

workspace admin_dashboard "Admin Dashboard":
  purpose: "Administrative overview of tasks and reports"
  sidebar:
    source: Task
    display: list
  main:
    source: Task
    display: kanban
    filter: status != "done"

workspace user_home "User Home":
  purpose: "User's personal task view"
  main:
    source: Task
    display: list
    filter: status != "done"
