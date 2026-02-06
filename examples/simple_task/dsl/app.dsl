# DAZZLE Team Task Manager
# Comprehensive Showcase of Dazzle v0.9+ Features:
#
# Core Features:
# - Personas for role-based views
# - Scenarios for demo state switching
# - Relationships between entities
# - Business logic: state machines, invariants, access rules
#
# Advanced Features (see separate DSL files):
# - Events: Task lifecycle events (events.dsl)
# - Services: Domain logic stubs (services.dsl)
# - Messaging: Email notifications (messaging.dsl)
# - Processes: Temporal workflows (processes.dsl)
# - LLM: AI-powered task classification (llm.dsl)

module simple_task.core

app simple_task "Team Task Manager"

# =============================================================================
# User Entity - team members who can be assigned tasks
# =============================================================================

entity User "Team Member":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  role: enum[admin,manager,member]=member
  department: str(50)
  avatar_url: str(500)
  is_active: bool=true
  created_at: datetime auto_add

# =============================================================================
# Task Entity - with proper user relationships
# =============================================================================

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,review,done]=todo
  priority: enum[low,medium,high,urgent]=medium
  due_date: date
  assigned_to: ref User
  created_by: ref User
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Computed field: days until/past due date
  days_overdue: computed days_since(due_date)

  # State machine: defines allowed status transitions
  transitions:
    todo -> in_progress: requires assigned_to
    in_progress -> review
    in_progress -> todo
    review -> done
    review -> in_progress
    done -> todo: role(admin)

  # Invariant: urgent tasks must have a due date
  invariant: priority != "urgent" or due_date != null

  # Access control
  access:
    read: role(admin) or role(manager) or assigned_to = current_user or created_by = current_user
    write: role(admin) or role(manager) or assigned_to = current_user

  # Event publishing (see events.dsl for event definitions)
  # TODO: Enable when publish syntax is implemented in parser
  # publish TaskCreated when created
  # publish TaskStatusChanged when status changed
  # publish TaskAssigned when assigned_to changed

# =============================================================================
# TaskComment Entity - for task collaboration
# =============================================================================

entity TaskComment "Task Comment":
  id: uuid pk
  task: ref Task required
  author: ref User required
  content: text required
  created_at: datetime auto_add

  # Publish comment events
  # TODO: Enable when publish syntax is implemented in parser
  # publish CommentAdded when created

  # Access: anyone who can read the task can read comments
  access:
    read: role(admin) or role(manager) or task.assigned_to = current_user or task.created_by = current_user
    write: author = current_user or role(admin)

# =============================================================================
# Personas - role-based variants for the UI
# =============================================================================

persona admin "Administrator":
  description: "Full system access for task and user management"
  goals: "Manage all tasks", "Configure team settings", "View analytics"
  proficiency: expert
  default_workspace: admin_dashboard
  default_route: "/admin"

persona manager "Team Manager":
  description: "Oversee team tasks and assignments"
  goals: "Assign tasks to team", "Track team progress", "Review completed work"
  proficiency: intermediate
  default_workspace: team_overview
  default_route: "/team"

persona member "Team Member":
  description: "Work on assigned tasks"
  goals: "Complete assigned tasks", "Update task status", "Request help"
  proficiency: novice
  default_workspace: my_work
  default_route: "/my-work"

# =============================================================================
# Scenarios - demo states for the Dazzle Bar
# =============================================================================

scenario empty "Empty State":
  description: "Fresh install with no data - test onboarding flows"

  for persona admin:
    start_route: "/admin"

  for persona manager:
    start_route: "/team"

  for persona member:
    start_route: "/my-work"

scenario busy_sprint "Active Sprint":
  description: "Mid-sprint with tasks in various states"

  for persona admin:
    start_route: "/admin"

  for persona manager:
    start_route: "/team"

  for persona member:
    start_route: "/my-work"

  demo:
    User:
      - email: "admin@example.com", name: "Alice Admin", role: admin, department: "Engineering"
      - email: "manager@example.com", name: "Bob Manager", role: manager, department: "Engineering"
      - email: "dev1@example.com", name: "Carol Developer", role: member, department: "Engineering"
      - email: "dev2@example.com", name: "Dave Developer", role: member, department: "Engineering"
      - email: "design@example.com", name: "Eve Designer", role: member, department: "Design"

    Task:
      - title: "Implement user authentication", status: done, priority: high
      - title: "Design dashboard mockups", status: review, priority: medium
      - title: "Write API documentation", status: in_progress, priority: medium
      - title: "Fix login bug", status: in_progress, priority: urgent
      - title: "Add dark mode support", status: todo, priority: low
      - title: "Performance optimization", status: todo, priority: high
      - title: "Database migration", status: todo, priority: urgent

scenario overdue_crisis "Overdue Tasks":
  description: "Several overdue tasks needing attention"

  for persona admin:
    start_route: "/admin"

  for persona manager:
    start_route: "/team"

  for persona member:
    start_route: "/my-work"

# =============================================================================
# Surfaces - UI views for entities
# =============================================================================

# Task List - main overview
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assigned To"

  ux:
    purpose: "View and manage all tasks"
    sort: created_at desc
    filter: status, priority, assigned_to
    search: title, description
    empty: "No tasks yet. Create your first task!"

    attention warning:
      when: due_date < today and status != done
      message: "Overdue task"

    attention notice:
      when: priority = urgent and status = todo
      message: "Urgent - needs immediate attention"

    for admin:
      scope: all
      purpose: "Manage all tasks across the team"

    for manager:
      scope: all
      purpose: "Review and assign team tasks"
      action_primary: task_create

    for member:
      scope: assigned_to = current_user or created_by = current_user
      purpose: "View your assigned and created tasks"

# Task Detail
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
    field created_by "Created By"
    field created_at "Created"
    field updated_at "Updated"

  ux:
    purpose: "View complete task information"

# Task Create Form
surface task_create "Create Task":
  uses entity Task
  mode: create

  section main "New Task":
    field title "Title"
    field description "Description"
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assign To"

  ux:
    purpose: "Create a new task"

    for admin:
      purpose: "Create and assign task to any team member"

    for manager:
      purpose: "Create task and assign to your team"

    for member:
      purpose: "Create a task for yourself"
      hide: assigned_to

# Task Edit Form
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

  ux:
    purpose: "Update task details and status"

# User List (admin only)
surface user_list "Team Members":
  uses entity User
  mode: list

  section main "Team":
    field name "Name"
    field email "Email"
    field role "Role"
    field department "Department"
    field is_active "Active"

  ux:
    purpose: "Manage team members"
    sort: name asc
    filter: role, department, is_active
    search: name, email
    empty: "No team members yet. Add your first team member to get started."

    for admin:
      scope: all
      purpose: "Full team management"
      action_primary: user_create

    for manager:
      scope: all
      purpose: "View team members"
      read_only: true

# User Create (admin only)
surface user_create "Add Team Member":
  uses entity User
  mode: create

  section main "New Team Member":
    field name "Name"
    field email "Email"
    field role "Role"
    field department "Department"

  ux:
    purpose: "Add a new team member"

# =============================================================================
# Workspaces - role-based dashboards
# =============================================================================

workspace task_board "Task Board":
  purpose: "Manage tasks visually"
  tasks:
    source: Task
    display: kanban
    group_by: status

workspace admin_dashboard "Admin Dashboard":
  access: persona(admin)
  purpose: "System-wide overview and management"

  metrics:
    source: Task
    aggregate:
      total_tasks: count(Task)
      todo: count(Task where status = todo)
      in_progress: count(Task where status = in_progress)
      in_review: count(Task where status = review)
      done: count(Task where status = done)

  team_metrics:
    source: User
    aggregate:
      total_users: count(User)
      active_users: count(User where is_active = true)

  urgent_tasks:
    source: Task
    filter: priority = urgent and status != done
    sort: due_date asc
    limit: 5
    display: list
    action: task_edit
    empty: "No urgent tasks"

  overdue_tasks:
    source: Task
    filter: due_date < today and status != done
    sort: due_date asc
    limit: 5
    display: list
    action: task_edit
    empty: "No overdue tasks"

workspace team_overview "Team Overview":
  access: persona(admin, manager)
  purpose: "Monitor team progress and workload"

  metrics:
    source: Task
    aggregate:
      total: count(Task)
      in_progress: count(Task where status = in_progress)
      in_review: count(Task where status = review)
      completed_today: count(Task where status = done and updated_at >= today)

  needs_review:
    source: Task
    filter: status = review
    sort: updated_at asc
    limit: 10
    display: list
    action: task_edit
    empty: "No tasks awaiting review"

  team_workload:
    source: Task
    filter: status = in_progress
    sort: priority desc, due_date asc
    limit: 10
    display: list
    action: task_detail
    empty: "No tasks in progress"

  unassigned:
    source: Task
    filter: assigned_to = null and status = todo
    sort: priority desc
    limit: 5
    display: list
    action: task_edit
    empty: "All tasks are assigned"

workspace my_work "My Work":
  access: authenticated
  purpose: "Personal task view for assigned work"

  my_in_progress:
    source: Task
    filter: status = in_progress and assigned_to = current_user
    sort: priority desc, due_date asc
    limit: 10
    display: list
    action: task_edit
    empty: "No tasks in progress - pick one from your backlog!"

  my_todo:
    source: Task
    filter: status = todo and assigned_to = current_user
    sort: priority desc, due_date asc
    limit: 10
    display: list
    action: task_edit
    empty: "No pending tasks - ask your manager for work"

  my_in_review:
    source: Task
    filter: status = review and assigned_to = current_user
    sort: updated_at desc
    limit: 5
    display: list
    action: task_detail
    empty: "No tasks in review"

  my_completed:
    source: Task
    filter: status = done and assigned_to = current_user
    sort: updated_at desc
    limit: 5
    display: list
    empty: "No completed tasks yet"
