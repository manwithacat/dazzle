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

app simple_task "Team Task Manager":
  security_profile: basic

feedback_widget: enabled

# =============================================================================
# User Entity - team members who can be assigned tasks
# =============================================================================

entity User "Team Member":
  intent: "A person with an account who can create and be assigned tasks within an organisation"
  domain: identity
  patterns: authentication, authorization, profile
  display_field: name
  id: uuid pk
  email: str(200) unique required pii(category=contact)
  name: str(100) required pii(category=identity)
  role: enum[admin,manager,member]=member
  department: str(50)
  avatar_url: str(500)
  is_active: bool=true
  # #1619 rel.json_extension — tenant/UI bag only; identity stays typed columns
  preferences: json
  created_at: datetime auto_add

  # ADR-0039 (#778/#1398): this entity IS the authenticated principal's domain row.
  # On real auth-user creation the framework provisions a matching User row, and
  # `ref User` FKs resolve to it via the email link — so a logged-in member can own
  # tasks without a manual seed. `name` (required) is filled from the email local-part.
  auth_identity:
    link_via: email
    map:
      name: email_localpart

  permit:
    list: role(admin) or role(manager)
    read: role(admin) or role(manager)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

  scope:
    list: all
      as: admin, manager
    read: all
      as: admin, manager
    # v0.71.19 (#1123): write-op scope rules enforce at runtime for
    # update/delete; create is parsed-but-not-enforced (#1124, v0.72.x).
    # User management is admin-only — `all as: admin` matches the permit
    # gate so the lint passes and downstream policy walks stay clean.
    create: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin

  fitness:
    repr_fields: [name, email, role, department, is_active]

# =============================================================================
# Task Entity - with proper user relationships
# =============================================================================

entity Task "Task":
  intent: "A unit of work assigned to a Team Member with a lifecycle from todo through review to done"
  domain: task_management
  patterns: lifecycle, workflow, audit_trail
  display_field: title
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
  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager) or role(member)
    update: role(admin) or role(manager) or role(member)
    delete: role(admin)

  scope:
    list: assigned_to = current_user or created_by = current_user
      as: member
    list: all
      as: admin, manager
    read: assigned_to = current_user or created_by = current_user
      as: member
    read: all
      as: admin, manager
    # v0.71.19 (#1123): members can update tasks they created or are
    # assigned to. Managers/admins update any task. Delete is admin-
    # only (matches permit). `create: all` keeps the lint clean —
    # create-time scope enforcement deferred to v0.72.x (#1124).
    create: all
      as: admin, manager, member
    update: assigned_to = current_user or created_by = current_user
      as: member
    update: all
      as: admin, manager
    delete: all
      as: admin

  fitness:
    repr_fields: [title, status, priority, assigned_to, due_date]

  # Event publishing (see events.dsl for event definitions)
  # TODO: Enable when publish syntax is implemented in parser
  # publish TaskCreated when created
  # publish TaskStatusChanged when status changed
  # publish TaskAssigned when assigned_to changed

# =============================================================================
# TaskComment Entity - for task collaboration
# =============================================================================

entity TaskComment "Task Comment":
  intent: "A discussion note attached to a Task by a Team Member to capture context or decisions"
  domain: task_management
  patterns: messaging, audit_trail
  id: uuid pk
  task: ref Task required
  author: ref User required
  content: text required
  created_at: datetime auto_add

  # Publish comment events
  # TODO: Enable when publish syntax is implemented in parser
  # publish CommentAdded when created

  # Access control
  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager) or role(member)
    update: role(admin)
    delete: role(admin)

  scope:
    list: all
      as: admin, manager, member
    read: all
      as: admin, manager, member
    # v0.71.19 (#1123): comments are append-only for members (their
    # own); admins edit/delete any. `update: author = current_user
    # as: member` would enforce author-only updates at runtime — but
    # the permit gate currently rejects member updates, so the scope
    # rule only fires for admin (where `all` is right).
    create: all
      as: admin, manager, member
    update: all
      as: admin
    delete: all
      as: admin

  fitness:
    repr_fields: [task, author, content]

# =============================================================================
# Personas - role-based variants for the UI
# =============================================================================

persona admin "Administrator":
  description: "Full system access for task and user management"
  goals: "Manage all tasks", "Configure team settings", "View analytics"
  proficiency: expert
  default_workspace: admin_dashboard
  default_route: "/admin"
  uses nav admin_nav

persona manager "Team Manager":
  description: "Oversee team tasks and assignments"
  goals: "Assign tasks to team", "Track team progress", "Review completed work"
  proficiency: intermediate
  default_workspace: team_overview
  default_route: "/team"
  uses nav manager_nav

persona member "Team Member":
  description: "Work on assigned tasks"
  goals: "Complete assigned tasks", "Update task status", "Request help"
  proficiency: novice
  default_workspace: my_work
  default_route: "/my-work"
  uses nav member_nav

# admin_dashboard is platform-prefix excluded from product D; still a valid nav target.
nav admin_nav:
  group "Ops":
    admin_dashboard
    team_overview
    task_board
    comments_desk
    people_desk

nav manager_nav:
  group "Lead":
    team_overview
    task_board
    people_desk
    comments_desk

nav member_nav:
  group "My work":
    my_work
    task_board
    comments_desk

# =============================================================================
# Scenarios - demo states for dev mode
# =============================================================================

scenario empty "Empty State":
  description: "Fresh install with no data - test onboarding flows"

  as persona admin:
    start_route: "/admin"

  as persona manager:
    start_route: "/team"

  as persona member:
    start_route: "/my-work"

scenario busy_sprint "Active Sprint":
  description: "Mid-sprint with tasks in various states"

  as persona admin:
    start_route: "/admin"

  as persona manager:
    start_route: "/team"

  as persona member:
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

  as persona admin:
    start_route: "/admin"

  as persona manager:
    start_route: "/team"

  as persona member:
    start_route: "/my-work"

# =============================================================================
# Surfaces - UI views for entities
# =============================================================================

# Task List - main overview
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: fragment
  # #1603 — row click opens the assignee (context hop), not the task detail.
  # Task detail remains available via actions / related on the user detail.
  open: User via assigned_to

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

    as admin:
      scope: all
      purpose: "Manage all tasks across the team"

    as manager:
      scope: all
      purpose: "Review and assign team tasks"
      action_primary: task_create

    as member:
      scope: assigned_to = current_user or created_by = current_user
      purpose: "View your assigned and created tasks"

# Task Detail — journey hub (not a flat warehouse dump): strip + related
surface task_detail "Task Detail":
  uses entity Task
  mode: view
  render: fragment

  section summary "Summary":
    field title "Title"
    field description "Description"

  section status "Status":
    layout: strip
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"

  section ownership "Ownership":
    field assigned_to "Assigned To"
    field created_by "Created By"
    field created_at "Created"
    field updated_at "Updated"

  related discussion "Discussion":
    display: table
    show: TaskComment
    columns: content, author, created_at

  ux:
    purpose: "Task context — status, ownership, and discussion in one place"

# Task Comment List - open hops to parent task context (not orphan warehouse row)
surface task_comments "Task Comments":
  uses entity TaskComment
  mode: list
  render: fragment
  open: Task via task

  section main "Comments":
    field author "Author"
    field content "Comment"
    field created_at "Posted"
    field task "Task"

  ux:
    purpose: "View and add comments on a task"
    sort: created_at desc
    search: content
    filter: author
    empty: "No comments yet. Start the discussion!"

# Comment Create - inline comment form on task detail
surface comment_detail "Comment Detail":
  uses entity TaskComment
  mode: view
  render: fragment

  section main "Comment":
    field task "Task"
    field author "Author"
    field content "Comment"
    field created_at "Created"

  ux:
    purpose: "Review a single task comment in full detail with its task and author context"

surface comment_create "Add Comment":
  uses entity TaskComment
  mode: create
  render: fragment

  section main "New Comment":
    field content "Comment"

  ux:
    purpose: "Add a comment to a task"

# Comment Edit - admin-only editing of comments
surface comment_edit "Edit Comment":
  uses entity TaskComment
  mode: edit
  render: fragment

  access: persona(admin)

  section main "Edit Comment":
    field content "Comment"

  ux:
    purpose: "Edit an existing comment"

# Task Create Form
surface task_create "Create Task":
  uses entity Task
  mode: create
  render: fragment

  section details "Task Details":
    field title "Title"
    field description "Description"

  section scheduling "Scheduling & Ownership":
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assign To"

  ux:
    purpose: "Create a new task"

    as admin:
      purpose: "Create and assign task to any team member"

    as manager:
      purpose: "Create task and assign to your team"

    as member:
      purpose: "Create a task for yourself"
      hide: assigned_to

# Task Edit Form
surface task_edit "Edit Task":
  uses entity Task
  mode: edit
  render: fragment

  section details "Task Details":
    field title "Title"
    field description "Description"

  section status_section "Status":
    field status "Status"

  section scheduling "Scheduling & Ownership":
    field priority "Priority"
    field due_date "Due Date"
    field assigned_to "Assigned To"

  ux:
    purpose: "Update task details and status"

# User List (admin only)
surface user_list "Team Members":
  uses entity User
  mode: list
  render: fragment
  # Row click → member overview hub (journey, not dead warehouse row)
  open: User via id

  access: persona(admin, manager)

  section main "Team":
    field name "Name"
    field email "Email"
    field role "Role"
    field department "Department"
    field is_active "Active"

  ux:
    purpose: "Manage team members — open a member for context and open work"
    sort: name asc
    filter: role, department, is_active
    search: name, email
    empty: "No team members yet. Add your first team member to get started."

    as admin:
      scope: all
      purpose: "Full team management"
      action_primary: user_create

    as manager:
      scope: all
      purpose: "View team members and open their work hub"
      read_only: true

# #1600 Wedge B — multi-section VIEW is the client/context overview hub.
# Task list open: User via assigned_to lands here: identity + role + related work.
surface user_detail "Team Member Overview":
  uses entity User
  mode: view
  render: fragment

  access: persona(admin, manager)

  section identity "Identity":
    field name "Name"
    field email "Email"

  section role "Role & access":
    layout: strip
    field role "Role"
    field department "Department"
    field is_active "Active"

  section timeline "Timeline":
    field created_at "Joined"

  related work "Open work":
    display: table
    show: Task
    columns: title, status, priority, due_date

  related comments "Comments":
    display: table
    show: TaskComment
    columns: content, author, created_at

  ux:
    purpose: "Context overview — identity, role, and related work in one place"

# User Create (admin only)
surface user_create "Add Team Member":
  uses entity User
  mode: create
  render: fragment

  access: persona(admin)

  section main "New Team Member":
    field name "Name"
    field email "Email"
    field role "Role"
    field department "Department"

  ux:
    purpose: "Add a new team member"

# User Edit (admin only)
surface user_edit "Edit Team Member":
  uses entity User
  mode: edit
  render: fragment

  access: persona(admin)

  section identity "Identity":
    field name "Name"
    field email "Email"

  section organisation "Organisation":
    field role "Role"
    field department "Department"

  section account "Account Status":
    field is_active "Active"

  ux:
    purpose: "Update team member details"

# =============================================================================
# Workspaces - role-based dashboards
# =============================================================================

workspace task_board "Task Board":
  access: persona(admin, manager, member)
  purpose: "Manage tasks visually"

  board_pulse:
    source: Task
    display: metrics
    aggregate:
      open: count(Task where status != done)
      in_progress: count(Task where status = in_progress)
      in_review: count(Task where status = review)
    tones:
      in_progress: accent
      in_review: warning

  tasks:
    source: Task
    display: kanban
    group_by: status

  # #1626 P0-7: not a calendar/Gantt — sorted due-date list with timeline display mode
  upcoming_due:
    source: Task
    filter: due_date != null and status != done
    sort: due_date asc
    limit: 30
    display: timeline
    action: task_edit
    empty: "No upcoming due dates"

  urgent_queue:
    source: Task
    filter: priority = urgent and status != done
    sort: due_date asc
    limit: 12
    display: queue
    action: task_edit
    empty: "No urgent tasks"

  status_mix:
    source: Task
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No tasks yet"

  recent_comments:
    source: TaskComment
    display: timeline
    sort: created_at desc
    limit: 12
    empty: "No comments yet"

# Story-driven compositions (docs/guides/story-to-composition.md):
#   admin   → admin_dashboard = metrics + urgent/overdue queues (ST-014)
#   manager → team_overview   = metrics + review/unassigned queues (ST-015–018)
#   member  → my_work         = personal metrics + WIP/todo queues (ST-019–020)

workspace admin_dashboard "Admin Dashboard":
  access: persona(admin)
  purpose: "System-wide overview and management"

  metrics:
    source: Task
    display: metrics
    aggregate:
      total_tasks: count(Task)
      todo: count(Task where status = todo)
      in_progress: count(Task where status = in_progress)
      in_review: count(Task where status = review)
      done: count(Task where status = done)
    tones:
      in_progress: accent
      in_review: warning
      done: positive

  team_metrics:
    source: User
    display: metrics
    aggregate:
      total_users: count(User)
      active_users: count(User where is_active = true)
    tones:
      active_users: positive

  # Job queues — not bare CRUD lists (ST-014 pressure surfaces).
  urgent_tasks:
    source: Task
    filter: priority = urgent and status != done
    sort: due_date asc
    limit: 10
    display: queue
    action: task_edit
    empty: "No urgent tasks"

  overdue_tasks:
    source: Task
    filter: due_date < today and status != done
    sort: due_date asc
    limit: 10
    display: queue
    action: task_edit
    empty: "No overdue tasks"

workspace team_overview "Team Overview":
  access: persona(admin, manager)
  purpose: "Monitor team progress and workload"

  metrics:
    source: Task
    display: metrics
    aggregate:
      total: count(Task)
      in_progress: count(Task where status = in_progress)
      in_review: count(Task where status = review)
      completed_today: count(Task where status = done and updated_at >= today)
    tones:
      in_progress: accent
      in_review: warning
      completed_today: positive

  # Status mix chart — different mode family than queues.
  flow_chart:
    source: Task
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No tasks yet"

  # ST-018 review queue (one listish Task signal for the review job).
  needs_review:
    source: Task
    filter: status = review
    sort: updated_at asc
    limit: 12
    display: queue
    action: task_edit
    empty: "No tasks awaiting review"

  # People source — not another Task queue pad.
  team_roster:
    source: User
    filter: is_active = true
    sort: name asc
    limit: 15
    display: list
    action: user_detail
    empty: "No active teammates"

  # Discussion pulse — TaskComment source.
  recent_discussion:
    source: TaskComment
    sort: created_at desc
    limit: 12
    display: list
    empty: "No recent comments"

  lead_readiness:
    display: status_list
    entries:
      - title: "Review queue"
        caption: "Clear review before assigning more WIP"
        icon: "eye"
        state: warning
      - title: "People desk"
        caption: "Unassigned work and capacity live on People"
        icon: "users"
        state: accent
      - title: "Board"
        caption: "Kanban flow is on Task Board"
        icon: "columns"
        state: positive

workspace my_work "My Work":
  access: authenticated
  purpose: "Personal task view for assigned work"

  my_summary:
    source: Task
    display: metrics
    aggregate:
      in_progress: count(Task where status = in_progress and assigned_to = current_user)
      todo: count(Task where status = todo and assigned_to = current_user)
      in_review: count(Task where status = review and assigned_to = current_user)
      done: count(Task where status = done and assigned_to = current_user)
    tones:
      in_progress: accent
      in_review: warning
      done: positive

  # Kanban for personal flow — mode family distinct from listish queues.
  my_board:
    source: Task
    filter: assigned_to = current_user and status != done
    display: kanban
    group_by: status
    sort: priority desc
    action: task_edit
    empty: "No open tasks assigned to you"

  # Due-date timeline — another mode family on Task.
  my_upcoming:
    source: Task
    filter: assigned_to = current_user and due_date != null and status != done
    sort: due_date asc
    limit: 15
    display: timeline
    action: task_edit
    empty: "No upcoming due dates on your work"

  # Comments source — not another Task list pad.
  my_discussion:
    source: TaskComment
    sort: created_at desc
    limit: 12
    display: list
    empty: "No comments on tasks yet"

  focus_hint:
    display: status_list
    entries:
      - title: "Work the board"
        caption: "Move cards through todo → in progress → review"
        icon: "columns"
        state: accent
      - title: "Due dates"
        caption: "Timeline shows what is due next on your plate"
        icon: "calendar"
        state: warning
      - title: "Team board"
        caption: "Full team kanban lives on Task Board"
        icon: "layout-grid"
        state: positive

# Fourth product workspace: discussion desk so list surfaces
# no longer dominate vs job shells (comments as collaboration, not CRUD dump).
workspace comments_desk "Discussion":
  purpose: "Recent task discussion across the team"
  access: persona(admin, manager, member)

  comment_pulse:
    source: TaskComment
    display: metrics
    aggregate:
      comments: count(TaskComment)
      tasks: count(Task)
    tones:
      comments: accent

  recent:
    source: TaskComment
    sort: created_at desc
    limit: 25
    display: queue
    empty: "No comments yet"

  comment_trail:
    source: TaskComment
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No comments yet"

  active_tasks:
    source: Task
    filter: status = in_progress
    sort: priority desc
    limit: 15
    display: grid
    action: task_detail
    empty: "No tasks in progress"

  status_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No open tasks"

# Fifth product workspace: people/roster desk.
workspace people_desk "People":
  purpose: "Team roster and capacity — who is active and what is on their plate"
  access: persona(admin, manager)

  people_pulse:
    source: User
    display: metrics
    aggregate:
      people: count(User)
      active: count(User where is_active = true)
      open_tasks: count(Task where status != done)
    tones:
      active: positive
      open_tasks: accent

  roster:
    source: User
    filter: is_active = true
    sort: name asc
    limit: 25
    display: grid
    action: user_detail
    empty: "No active teammates"

  unassigned_work:
    source: Task
    filter: assigned_to = null and status != done
    sort: priority desc
    limit: 15
    display: queue
    action: task_edit
    empty: "Every open task has an owner"

  in_flight_board:
    source: Task
    filter: status = in_progress or status = review
    display: kanban
    group_by: status
    sort: priority desc
    action: task_detail
    empty: "No tasks in progress or review"

  load_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No open tasks"

  capacity_hint:
    display: status_list
    entries:
      - title: "Assign from Team Overview"
        caption: "Unassigned and review queues live on the manager desk"
        icon: "list-checks"
        state: accent
      - title: "Board view"
        caption: "Kanban flow is on Task Board for visual WIP"
        icon: "columns"
        state: positive
