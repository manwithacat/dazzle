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

persona manager "Project Manager":
  role: manager
  description: "Manages projects and assigns tasks"
  default_workspace: dashboard

persona member "Team Member":
  role: member
  description: "Works on assigned tasks"
  default_workspace: project_board

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

  milestones:
    source: Milestone
    display: list
    sort: start_date asc

# ── Surfaces ─────────────────────────────────────────────────────────

surface project_list "Projects":
  uses entity Project
  mode: list
  section main:
    field name "Name"
    field owner "Owner"
    field status "Status"
    field target_date "Target Date"

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
  section main:
    field name "Name"
    field description "Description"
    field owner "Owner"
    field status "Status"
    field start_date "Start"
    field target_date "Target"

  related tasks "Tasks":
    display: table
    show: Task

  related milestones "Milestones":
    display: status_cards
    show: Milestone

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assignee"
    field due_date "Due"
    field labels "Labels"

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
  section main:
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assignee"
    field due_date "Due Date"
    field labels "Labels"
    field estimated_hours "Estimate"

  related comments "Discussion":
    display: table
    show: Comment

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
  section main:
    field task "Task"
    field author "Author"
    field body "Comment"
    field created_at "Date"
  ux:
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
  section main:
    field name "Name"
    field status "Status"
    field parent_project "Project"
    field start_date "Start"
    field end_date "End"

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
  section main:
    field task "Task"
    field filename "File"
    field uploaded_by "Uploaded By"
    field created_at "Date"
  ux:
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
