# Project Tracker — UX Component Expansion showcase
# Exercises: rich text, date picker/range, tags, combobox,
# breadcrumbs, accordion, skeleton, toast, modal, slide-over,
# command palette, steps indicator

module project_tracker.core

app project_tracker "Project Tracker":
  security_profile: basic

feedback_widget: enabled

# ── Personas ─────────────────────────────────────────────────────────

persona admin "Admin":
  role: admin
  description: "Full access to all projects and settings"
  default_workspace: dashboard
  uses nav admin_nav

persona manager "Project Manager":
  role: manager
  description: "Manages projects and assigns tasks"
  default_workspace: dashboard
  # WI N: job desks first — not auto entity-list soup
  uses nav manager_nav

persona member "Team Member":
  role: member
  description: "Works on assigned tasks"
  # Answer-first: personal task desk (product maturity)
  default_workspace: my_tasks
  uses nav member_nav

# Curated sidebars: workspace destinations only (WI primary N).
# Names must match workspace ids (not labels) — validate warns on orphans.
nav admin_nav:
  group "Ops":
    dashboard
    project_board
    milestone_plan
    discussion_desk
    files_desk
    my_tasks
    people_desk
    review_ops
    backlog_ops
    priority_ops


nav manager_nav:
  group "Manage":
    dashboard
    project_board
    milestone_plan
    discussion_desk
    files_desk
    my_tasks
    people_desk
    review_ops
    backlog_ops
    priority_ops


nav member_nav:
  group "My work":
    my_tasks
    project_board
    discussion_desk
    files_desk
    dashboard
    backlog_ops
    priority_ops

# ── Entities ─────────────────────────────────────────────────────────

entity User "Team Member":
  display_field: name
  id: uuid pk
  email: str(200) unique required pii(category=contact)
  name: str(100) required pii(category=identity)
  role: enum[admin,manager,member]=member
  department: str(50)
  is_active: bool=true
  created_at: datetime auto_add

  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

  scope:
    list: all
      as: admin, manager, member
    create: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin

entity Project "Project":
  display_field: name
  id: uuid pk
  name: str(200) required
  description: text
  status: enum[active,archived]=active
  owner: ref User required
  start_date: date
  target_date: date
  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager)
    update: role(admin) or role(manager)
    delete: role(admin)

  scope:
    list: all
      as: admin, manager, member
    create: all
      as: admin, manager
    update: all
      as: admin, manager
    delete: all
      as: admin

entity Milestone "Milestone":
  display_field: name
  id: uuid pk
  parent_project: ref Project required
  name: str(200) required
  description: text
  status: enum[planning,active,completed]=planning
  start_date: date
  end_date: date
  created_at: datetime auto_add

  transitions:
    planning -> active
    active -> completed
    completed -> active: role(admin)

  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager)
    update: role(admin) or role(manager)
    delete: role(admin)

  scope:
    list: all
      as: admin, manager, member
    create: all
      as: admin, manager
    update: all
      as: admin, manager
    delete: all
      as: admin

entity Task "Task":
  display_field: title
  id: uuid pk
  parent_project: ref Project required
  milestone: ref Milestone
  title: str(200) required
  description: text
  status: enum[backlog,todo,in_progress,review,done]=backlog
  priority: enum[low,medium,high,critical]=medium
  assigned_to: ref User
  labels: str(500)
  due_date: date
  estimated_hours: decimal(5,1)
  created_by: ref User
  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    backlog -> todo
    todo -> in_progress: requires assigned_to
    in_progress -> review
    in_progress -> todo
    review -> done
    review -> in_progress
    done -> backlog: role(admin) or role(manager)

  invariant: priority != "critical" or due_date != null

  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager) or role(member)
    update: role(admin) or role(manager) or role(member)
    delete: role(admin) or role(manager)

  scope:
    list: all
      as: admin, manager
    list: assigned_to = current_user
      as: member
    create: all
      as: admin, manager, member
    update: all
      as: admin, manager
    update: assigned_to = current_user
      as: member
    delete: all
      as: admin, manager

entity Comment "Comment":
  id: uuid pk
  task: ref Task required
  author: ref User required
  body: text required
  created_at: datetime auto_add

  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager) or role(member)
    update: role(admin)
    delete: role(admin)

  scope:
    list: all
      as: admin, manager, member
    create: all
      as: admin, manager, member
    update: all
      as: admin
    delete: all
      as: admin

entity Attachment "Attachment":
  id: uuid pk
  task: ref Task required
  uploaded_by: ref User required
  filename: str(255) required
  file: file required
  size_bytes: int
  created_at: datetime auto_add

  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager) or role(member)
    delete: role(admin) or role(manager)

  scope:
    list: all
      as: admin, manager, member
    create: all
      as: admin, manager, member
    delete: all
      as: admin, manager

# ── Workspaces ───────────────────────────────────────────────────────

# Story-driven compositions (docs/guides/story-to-composition.md):
#   manager/admin → dashboard     = metrics + task queue + project grid
#   member        → project_board = metrics + kanban board + milestones

workspace dashboard "Dashboard":
  access: persona(admin, manager, member)
  purpose: "Project and task overview — metrics and work queues first"

  portfolio_metrics:
    source: Task
    display: metrics
    aggregate:
      open_tasks: count(Task where status != done)
      in_progress: count(Task where status = in_progress)
      critical: count(Task where priority = critical and status != done)
      projects: count(Project where status = active)
    tones:
      in_progress: accent
      critical: destructive

  # Work the pile — review queue before the visual board.
  open_task_queue:
    source: Task
    filter: status != done
    sort: priority desc, due_date asc
    limit: 15
    display: queue
    action: task_edit
    empty: "No open tasks"

  project_overview:
    source: Project
    display: grid
    sort: updated_at desc

  task_flow:
    source: Task
    display: kanban
    group_by: status
    sort: priority desc

  # WI D: chart family — priority pressure across open work
  priority_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Task)
    empty: "No open tasks"

workspace project_board "Project Board":
  access: persona(admin, manager, member)
  purpose: "Task and milestone management"

  board_metrics:
    source: Task
    display: metrics
    aggregate:
      todo: count(Task where status = todo)
      in_progress: count(Task where status = in_progress)
      done: count(Task where status = done)
    tones:
      in_progress: accent
      done: positive

  task_board:
    source: Task
    display: kanban
    group_by: status
    sort: priority desc

  unassigned_queue:
    source: Task
    filter: assigned_to = null and status != done
    sort: priority desc
    limit: 10
    display: queue
    action: task_edit
    empty: "Every open task has an assignee"

  # WI D: context family for schedule (not list pad)
  milestones:
    source: Milestone
    display: timeline
    sort: start_date asc

  # WI D: chart family — project status mix beside the board
  project_status_mix:
    source: Project
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Project)
    empty: "No projects"

# Product maturity: more job desks vs 8 list surfaces (was density 0.80).
workspace my_tasks "My Tasks":
  purpose: "Member desk — assigned work and due pressure, not the full project warehouse"
  access: persona(admin, manager, member)

  load:
    source: Task
    display: metrics
    aggregate:
      open: count(Task where status != done)
      in_progress: count(Task where status = in_progress)
      review: count(Task where status = review)
    tones:
      in_progress: accent
      review: warning

  assigned_queue:
    source: Task
    filter: status != done
    sort: priority desc, due_date asc
    limit: 20
    display: queue
    action: task_edit
    empty: "No open tasks"

  board:
    source: Task
    display: kanban
    group_by: status
    sort: priority desc

  # WI D: context family for discussion pulse
  recent_discussion:
    source: Comment
    sort: created_at desc
    limit: 10
    display: timeline
    empty: "No recent comments"

  # WI D: chart family — personal open work by priority
  my_priority_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Task)
    empty: "No open tasks"

workspace milestone_plan "Milestone Plan":
  purpose: "Schedule desk — milestones before drilling into task lists"
  access: persona(admin, manager)

  plan_metrics:
    source: Milestone
    display: metrics
    aggregate:
      planning: count(Milestone where status = planning)
      active: count(Milestone where status = active)
      completed: count(Milestone where status = completed)
    tones:
      active: accent
      completed: positive

  milestone_queue:
    source: Milestone
    filter: status != completed
    sort: start_date asc
    display: queue
    empty: "No open milestones"

  active_projects:
    source: Project
    filter: status = active
    sort: updated_at desc
    display: grid

  # WI D: chart family — milestone status mix
  milestone_mix:
    source: Milestone
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Milestone)
    empty: "No milestones"

  # WI D: context family — open tasks tied to the plan
  open_work_trail:
    source: Task
    filter: status != done
    sort: due_date asc
    limit: 15
    display: timeline
    action: task_detail
    empty: "No open tasks"

# Fifth product workspace (WI density D): discussion desk vs bare comment list.
workspace discussion_desk "Discussion":
  purpose: "Cross-task discussion pulse and recent comments"
  access: persona(admin, manager, member)

  discussion_pulse:
    source: Comment
    display: metrics
    aggregate:
      comments: count(Comment)
      open_tasks: count(Task where status != done)
    tones:
      comments: accent

  # WI D: timeline of comments (context family)
  recent:
    source: Comment
    sort: created_at desc
    limit: 25
    display: timeline
    empty: "No comments yet"

  # WI D: grid family for open task cards
  open_tasks:
    source: Task
    filter: status != done
    sort: priority desc
    limit: 15
    display: grid
    action: task_detail
    empty: "No open tasks"

  # WI D: kanban family — discuss work still in flight
  open_flow:
    source: Task
    filter: status != done
    display: kanban
    group_by: status
    sort: priority desc
    empty: "No open tasks"

  # WI D: chart family — priority mix on open work
  priority_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Task)
    empty: "No open tasks"

# Sixth product workspace (WI density D): files desk for attachment work.
workspace files_desk "Files":
  purpose: "Attachment desk — files linked to tasks, not a warehouse dump"
  access: persona(admin, manager, member)

  files_pulse:
    source: Attachment
    display: metrics
    aggregate:
      files: count(Attachment)
      tasks: count(Task)
      projects: count(Project)
    tones:
      files: accent

  # WI D: grid family for file cards
  recent_files:
    source: Attachment
    sort: created_at desc
    limit: 25
    display: grid
    empty: "No attachments yet"

  # WI D: context family for linked open work
  open_tasks:
    source: Task
    filter: status != done
    sort: updated_at desc
    limit: 15
    display: timeline
    action: task_detail
    empty: "No open tasks"

  # WI D: queue family — attach evidence to urgent open work
  urgent_queue:
    source: Task
    filter: status != done and (priority = critical or priority = high)
    sort: priority desc, due_date asc
    limit: 12
    display: queue
    action: task_edit
    empty: "No high-priority open tasks"

  # WI D: chart family — open task status mix next to files
  status_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No open tasks"

# Seventh product desk (WI D): people context without bare user-list warehouse.
workspace people_desk "People":
  purpose: "Team pulse — who is on the roster and open work load by status"
  access: persona(admin, manager)

  team_pulse:
    source: User
    display: metrics
    aggregate:
      people: count(User)
      open_tasks: count(Task where status != done)
      projects: count(Project where status = active)
    tones:
      open_tasks: accent
      people: positive

  # WI D: grid family for roster cards
  roster:
    source: User
    sort: name asc
    limit: 25
    display: grid
    empty: "No team members yet"

  # WI D: queue family — unassigned open work
  unassigned:
    source: Task
    filter: assigned_to = null and status != done
    sort: priority desc
    limit: 15
    display: queue
    action: task_edit
    empty: "Every open task has an assignee"

  # WI D: context family — recent comments across the team
  discussion_pulse:
    source: Comment
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No recent comments"

  # WI D: chart family — open work status mix
  load_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No open tasks"


# Eighth product desk (WI D): 5 lists floor dens ~0.42 with 7 full desks — need 8.
workspace review_ops "Review":
  purpose: "Review desk — work waiting on review and recent discussion"
  access: persona(admin, manager)

  review_pulse:
    source: Task
    display: metrics
    aggregate:
      in_review: count(Task where status = review)
      open: count(Task where status != done)
      comments: count(Comment)
    tones:
      in_review: warning
      open: accent

  # WI D: queue family — review backlog first
  review_queue:
    source: Task
    filter: status = review
    sort: updated_at asc
    limit: 20
    display: queue
    action: task_edit
    empty: "Nothing awaiting review"

  # WI D: kanban family — review pipeline
  review_board:
    source: Task
    filter: status = review or status = in_progress or status = done
    display: kanban
    group_by: status
    sort: priority desc
    action: task_detail
    empty: "No tasks in the review pipeline"

  # WI D: context family — recent comments trail
  comment_trail:
    source: Comment
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No comments yet"

  # WI D: chart family — open work status mix
  status_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No open tasks"

# Ninth product desk (WI D): 5 lists floor dens ~0.38 with 8 full desks — need 9.
workspace backlog_ops "Backlog Ops":
  purpose: "Backlog pressure — unstarted work ready to pull into sprint"
  access: persona(admin, manager, member)

  backlog_pulse:
    source: Task
    display: metrics
    aggregate:
      backlog: count(Task where status = backlog)
      todo: count(Task where status = todo)
      in_progress: count(Task where status = in_progress)
    tones:
      backlog: accent
      todo: warning
      in_progress: positive

  # WI D: queue family — backlog first
  backlog_queue:
    source: Task
    filter: status = backlog
    sort: priority desc, updated_at asc
    limit: 20
    display: queue
    action: task_edit
    empty: "Backlog is empty"

  # WI D: grid family — ready-to-start todos
  todo_grid:
    source: Task
    filter: status = todo
    sort: priority desc
    limit: 20
    display: grid
    action: task_detail
    empty: "No ready todos"

  # WI D: context family — recent task trail
  task_trail:
    source: Task
    filter: status = backlog or status = todo
    sort: updated_at desc
    limit: 15
    display: timeline
    action: task_detail
    empty: "No backlog activity yet"

  # WI D: chart family — unstarted status mix
  status_mix:
    source: Task
    filter: status = backlog or status = todo
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No unstarted tasks"

# Tenth product desk (WI D): 5 lists floor dens ~0.36 with 9 full desks — need 10.
workspace priority_ops "Priority Ops":
  purpose: "Priority pressure — high and critical open work that needs pull-forward"
  access: persona(admin, manager, member)

  priority_pulse:
    source: Task
    display: metrics
    aggregate:
      critical: count(Task where priority = critical and status != done)
      high: count(Task where priority = high and status != done)
      open: count(Task where status != done)
    tones:
      critical: destructive
      high: warning
      open: accent

  # WI D: queue family — critical first among open work
  critical_queue:
    source: Task
    filter: priority = critical and status != done
    sort: due_date asc, updated_at asc
    limit: 20
    display: queue
    action: task_edit
    empty: "No critical open tasks"

  # WI D: grid family — high-priority open board
  high_grid:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc, priority desc
    limit: 20
    display: grid
    action: task_detail
    empty: "No high-priority open tasks"

  # WI D: context family — recent priority trail
  priority_trail:
    source: Task
    filter: (priority = high or priority = critical) and status != done
    sort: updated_at desc
    limit: 15
    display: timeline
    action: task_detail
    empty: "No priority activity yet"

  # WI D: chart family — priority mix among open work
  priority_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Task)
    empty: "No open tasks to chart"

# ── Surfaces ─────────────────────────────────────────────────────────

surface project_list "Projects":
  uses entity Project
  mode: list
  open: Project via id
  section main:
    field name "Name"
    field owner "Owner"
    field status "Status"
    field target_date "Target Date"
  ux:
    purpose: "Browse projects — open a project for tasks and milestones"
    empty: "No projects yet."

surface project_create "New Project":
  uses entity Project
  mode: create
  section details:
    field name "Project Name"
    field description "Description" widget=rich_text
    field owner "Owner" widget=combobox
    field start_date "Start Date" widget=picker
    field target_date "Target Date" widget=picker

surface project_detail "Project Detail":
  uses entity Project
  mode: view
  section summary "Summary":
    field name "Name"
    field description "Description"
  section status "Status":
    layout: strip
    field status "Status"
    field owner "Owner"
    field start_date "Start"
    field target_date "Target"

  related tasks "Tasks":
    display: table
    show: Task
    columns: title, status, priority, assigned_to, due_date

  related milestones "Milestones":
    display: status_cards
    show: Milestone

surface task_list "Tasks":
  uses entity Task
  mode: list
  # Context hop to project hub (not only task warehouse)
  open: Project via parent_project
  section main:
    field title "Title"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assignee"
    field parent_project "Project"
    field due_date "Due"
    field labels "Labels"
  ux:
    purpose: "Work across projects — open a row for the project context hub"
    sort: due_date asc
    filter: status, priority, assigned_to
    empty: "No tasks yet."

surface task_create "New Task":
  uses entity Task
  mode: create
  section basic:
    field title "Title"
    field description "Description" widget=rich_text
    field parent_project "Project" widget=combobox
    field milestone "Milestone" widget=combobox
  section assignment:
    field assigned_to "Assignee" widget=combobox
    field priority "Priority"
    field due_date "Due Date" widget=picker
    field labels "Labels" widget=tags
    field estimated_hours "Estimate (hours)"

surface task_detail "Task Detail":
  uses entity Task
  mode: view
  section summary "Summary":
    field title "Title"
    field description "Description"
  section status "Status":
    layout: strip
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"
  section ownership "Ownership":
    field assigned_to "Assignee"
    field parent_project "Project"
    field milestone "Milestone"
    field labels "Labels"
    field estimated_hours "Estimate"

  related comments "Discussion":
    display: table
    show: Comment
    columns: body, author, created_at

  related task_files "Files":
    display: file_list
    show: Attachment

surface task_edit "Edit Task":
  uses entity Task
  mode: edit
  section basic:
    field title "Title"
    field description "Description" widget=rich_text
  section assignment:
    field assigned_to "Assignee" widget=combobox
    field priority "Priority"
    field due_date "Due Date" widget=picker
    field labels "Labels" widget=tags

surface milestone_create "New Milestone":
  uses entity Milestone
  mode: create
  section main:
    field name "Name"
    field description "Description" widget=rich_text
    field parent_project "Project" widget=combobox
    field start_date "Start Date" widget=picker
    field end_date "End Date" widget=picker

surface comment_create "Add Comment":
  uses entity Comment
  mode: create
  section main:
    field body "Comment" widget=rich_text

surface comment_list "Comments":
  uses entity Comment
  mode: list
  open: Task via task
  section main:
    field task "Task"
    field author "Author"
    field body "Comment"
    field created_at "Date"
  ux:
    purpose: "Discussion across tasks — open hops to the task hub"
    sort: created_at desc
    filter: task, author
    empty: "No comments yet."

surface comment_edit "Edit Comment":
  uses entity Comment
  mode: edit
  access: persona(admin)
  section main:
    field body "Comment" widget=rich_text

surface project_edit "Edit Project":
  uses entity Project
  mode: edit
  section details:
    field name "Project Name"
    field description "Description" widget=rich_text
    field owner "Owner" widget=combobox
    field start_date "Start Date" widget=picker
    field target_date "Target Date" widget=picker

surface milestone_list "Milestones":
  uses entity Milestone
  mode: list
  open: Project via parent_project
  section main:
    field name "Name"
    field status "Status"
    field parent_project "Project"
    field start_date "Start"
    field end_date "End"
  ux:
    purpose: "Milestones by project — open hops to the project hub"

surface milestone_edit "Edit Milestone":
  uses entity Milestone
  mode: edit
  section main:
    field name "Name"
    field description "Description" widget=rich_text
    field status "Status"
    field start_date "Start Date" widget=picker
    field end_date "End Date" widget=picker

surface attachment_list "Attachments":
  uses entity Attachment
  mode: list
  open: Task via task
  section main:
    field task "Task"
    field filename "File"
    field uploaded_by "Uploaded By"
    field created_at "Date"
  ux:
    purpose: "Files across tasks — open hops to the task hub"
    sort: created_at desc
    filter: task
    empty: "No attachments uploaded yet."

surface attachment_view "Attachment":
  uses entity Attachment
  mode: view
  # Plain file field → the built-in PDF viewer sources the document
  # through the scope-gated /_dazzle/documents range proxy (#162) —
  # viewing an attachment is gated exactly like reading its record.
  display: pdf_viewer
  section main:
    field filename "Filename"
    field task "Task"
    field uploaded_by "Uploaded By"
    field created_at "Uploaded"

surface attachment_create "Upload Attachment":
  uses entity Attachment
  mode: create
  section main:
    field task "Task"
    field file "File"
    field filename "Filename"
