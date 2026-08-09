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


nav manager_nav:
  group "Manage":
    dashboard
    project_board
    milestone_plan
    discussion_desk
    files_desk
    my_tasks
    people_desk


nav member_nav:
  group "My work":
    my_tasks
    project_board
    discussion_desk
    files_desk
    dashboard

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
    # Cycle 1347: read required so /app/user/{id} hub (and kanban assignee hops)
    # resolve — list-only scope made gated_read return opaque 404 (#303).
    read: all
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

  # Project archive SM (domain residual status∄transitions).
  # Managers archive finished work; admin may reactivate.
  transitions:
    active -> archived: role(admin) or role(manager)
    archived -> active: role(admin)

  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager)
    update: role(admin) or role(manager)
    delete: role(admin)

  scope:
    list: all
      as: admin, manager, member
    read: all
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
    read: all
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
    # Shared board + teammate hubs (ST-005) need list/read across assignees.
    # Member-only assigned_to scope emptied "Task · assigned to" on peer hubs
    # and 404'd kanban drills into teammates' cards (cycle 1350 acceptance).
    list: all
      as: admin, manager, member
    # Queue drills + detail surfaces need READ (list-only scope → detail 404).
    read: all
      as: admin, manager, member
    create: all
      as: admin, manager, member
    update: all
      as: admin, manager
    update: assigned_to = current_user
      as: member
    delete: all
      as: admin, manager

entity Comment "Comment":
  # Goal B conversation: peer tools (Linear/Jira/Asana) show discussion copy as
  # the row identity on work desks — not a UUID shell. display_field drives
  # queue titles so hero stills read as a live thread.
  intent: "Threaded discussion note on a Task — the conversation that unblocks delivery"
  domain: project_delivery
  patterns: messaging, audit_trail
  display_field: body
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
    read: all
      as: admin, manager, member
    create: all
      as: admin, manager, member
    update: all
      as: admin
    delete: all
      as: admin

  fitness:
    repr_fields: [task, author, body]

entity Attachment "Attachment":
  intent: "Supporting document on a task — filename is the document identity buyers scan, not a UUID shell"
  # Goal B document depth: queue/timeline title is the human filename.
  display_field: filename

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
    read: all
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
  # Goal B conversation + document: peer PM tools (Linear / Asana / Jira) put
  # named deliverables and discussion on the first screen — not only task piles.
  purpose: "Portfolio metrics, document composition, live discussion trail, and work queues"

  portfolio_metrics:
    source: Task
    display: metrics
    aggregate:
      open_tasks: count(Task where status != done)
      in_progress: count(Task where status = in_progress)
      critical: count(Task where priority = critical and status != done)
      documents: count(Attachment)
      conversation: count(Comment)
    tones:
      in_progress: accent
      critical: destructive
      documents: accent
      conversation: accent

  # Goal B document spine on Home (not only Files desk) — human filenames as
  # titles so hero stills read as document composition above the fold.
  composition:
    source: Attachment
    sort: created_at desc
    limit: 8
    display: queue
    action: attachment_view
    empty: "No documents yet — upload a deliverable on a task"

  # Goal B conversation spine — Message/Bubble chrome (HTTP CONVERSATION +
  # MessageScroller), not queue meta. Peer PM tools put thread copy above fold.
  live_conversation:
    source: Comment
    sort: created_at desc
    limit: 6
    display: conversation
    action: comment_detail
    empty: "No conversation yet — task discussion notes appear here as work moves"

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
    # Portfolio scan is pull-next cards, not a dense photo grid.
    display: queue
    sort: updated_at desc
    action: project_detail

  task_flow:
    source: Task
    display: kanban
    group_by: status
    sort: priority desc

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

  milestones:
    source: Milestone
    display: timeline
    sort: start_date asc

  project_status_mix:
    source: Project
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Project)
    empty: "No projects"

# Product maturity: more job desks vs 8 list surfaces (was density 0.80).
workspace my_tasks "My Tasks":
  purpose: "Member desk — assigned work, live discussion, and due pressure"
  access: persona(admin, manager, member)

  load:
    source: Task
    display: metrics
    aggregate:
      open: count(Task where status != done)
      in_progress: count(Task where status = in_progress)
      review: count(Task where status = review)
      conversation: count(Comment)
    tones:
      in_progress: accent
      review: warning
      conversation: accent

  # Goal B: members land here — Message/Bubble conversation chrome so the desk
  # is a reply surface, not only an assigned-task warehouse.
  live_conversation:
    source: Comment
    sort: created_at desc
    limit: 8
    display: conversation
    action: comment_detail
    empty: "No conversation yet — notes on your tasks appear here"

  assigned_queue:
    source: Task
    filter: status != done
    sort: priority desc, due_date asc
    limit: 20
    display: queue
    # Open the task hub (status strip + discussion queue + files), not the
    # edit form — member pilot path for ST-003 (cycle 1502 acceptance).
    action: task_detail
    empty: "No open tasks"

  board:
    source: Task
    display: kanban
    group_by: status
    sort: priority desc

  recent_discussion:
    source: Comment
    sort: created_at desc
    limit: 10
    display: timeline
    action: comment_detail
    empty: "No recent comments"

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
    # Active portfolio is a work queue, not a warehouse grid.
    display: queue
    action: project_detail

  milestone_mix:
    source: Milestone
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Milestone)
    empty: "No milestones"

  open_work_trail:
    source: Task
    filter: status != done
    sort: due_date asc
    limit: 15
    display: timeline
    action: task_detail
    empty: "No open tasks"

# Fifth product workspace: discussion desk vs bare comment list.
workspace discussion_desk "Discussion":
  # Goal B conversation depth: dedicated trail desk mirrors Linear/Jira activity.
  purpose: "Live discussion trail across tasks — reply where the conversation already is"
  access: persona(admin, manager, member)

  discussion_pulse:
    source: Comment
    display: metrics
    aggregate:
      conversation: count(Comment)
      open_tasks: count(Task where status != done)
    tones:
      conversation: accent

  live_conversation:
    source: Comment
    sort: created_at desc
    limit: 20
    display: conversation
    action: comment_detail
    empty: "No conversation yet — notes on open tasks appear here"

  recent:
    source: Comment
    sort: created_at desc
    limit: 25
    display: timeline
    action: comment_detail
    empty: "No comments yet"

  open_tasks:
    source: Task
    filter: status != done
    sort: priority desc
    limit: 15
    # Open work is pull-next, not a card wall.
    display: queue
    action: task_detail
    empty: "No open tasks"

  open_flow:
    source: Task
    filter: status != done
    display: kanban
    group_by: status
    sort: priority desc
    empty: "No open tasks"

  priority_mix:
    source: Task
    filter: status != done
    display: bar_chart
    group_by: priority
    aggregate:
      count: count(Task)
    empty: "No open tasks"

# Sixth product workspace: document composition desk (Goal B document depth).
# Peer tools (Linear / Jira / Asana) show named deliverables above empty task
# chrome — filenames + parent task context, not a blank "No attachments yet".
workspace files_desk "Files":
  purpose: "Document composition — named deliverables linked to tasks (not a warehouse dump)"
  access: persona(admin, manager, member)

  files_pulse:
    source: Attachment
    display: metrics
    aggregate:
      documents: count(Attachment)
      open_tasks: count(Task where status != done)
      projects: count(Project where status = active)
    tones:
      documents: accent
      open_tasks: positive

  # Document body first (Goal B): composition queue with human filenames as
  # titles — pull open the attachment hub (PDF viewer path).
  composition:
    source: Attachment
    sort: created_at desc
    limit: 25
    display: queue
    action: attachment_view
    empty: "No documents yet — upload a deliverable on a task"

  # Tasks still missing evidence (secondary pressure, under composition).
  needs_evidence:
    source: Task
    filter: status = in_progress or status = review
    sort: priority desc, updated_at desc
    limit: 12
    display: queue
    action: task_detail
    empty: "No in-flight tasks waiting on documents"

  recent_uploads:
    source: Attachment
    sort: created_at desc
    limit: 12
    display: timeline
    action: attachment_view
    empty: "No recent uploads"

workspace people_desk "People":
  # Goal B org_structure: peer PM tools (Linear / Asana / Notion) show team
  # by department and project ownership — not a flat warehouse roster above
  # an unassigned task dump.
  purpose: "Org structure people can parse — team by department, project owners, then open load"
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

  # Role board (enum columns admin/manager/member) — org authority shape.
  by_role:
    source: User
    filter: is_active = true
    display: kanban
    group_by: role
    sort: name asc
    limit: 40
    action: user_detail
    empty: "No team members yet"

  # Department roster queue — people names with department meta (org placement).
  by_department:
    source: User
    filter: is_active = true
    display: queue
    sort: department asc, name asc
    limit: 40
    action: user_detail
    empty: "No team members yet"

  # Ownership lines — who owns which active projects (accountability hierarchy).
  project_owners:
    source: Project
    filter: status = active
    sort: name asc
    limit: 15
    display: queue
    action: project_detail
    empty: "No active projects"

  # Secondary flat roster (after hierarchy) — sorted by department.
  roster:
    source: User
    filter: is_active = true
    sort: department asc, name asc
    limit: 25
    display: queue
    action: user_detail
    empty: "No team members yet"

  unassigned:
    source: Task
    filter: assigned_to = null and status != done
    sort: priority desc
    limit: 12
    display: queue
    action: task_edit
    empty: "Every open task has an assignee"

  discussion_pulse:
    source: Comment
    sort: created_at desc
    limit: 12
    display: timeline
    empty: "No recent comments"

  # Department headcount mix (org shape at a glance).
  dept_mix:
    source: User
    filter: is_active = true
    display: bar_chart
    group_by: department
    aggregate:
      count: count(User)
    empty: "No team members yet"

  ux:
    as manager:
      purpose: "See team by department and project owners before unassigned load"
      focus: team_pulse, by_role, by_department, project_owners
    as admin:
      purpose: "Org structure and ownership before open-task load"
      focus: team_pulse, by_role, by_department, project_owners


surface project_list "Projects":
  uses entity Project
  mode: list
  # Dual open (story_walk dig cycle 1575): project hub first; secondary hop
  # to owner User hub for teammate context (ST-001/004 + ST-005 path).
  open: Project via id | User via owner
  section main:
    field name "Name"
    field owner "Owner"
    field status "Status"
    field target_date "Target Date"
  ux:
    purpose: "Browse projects — open a row for the project hub or owner teammate hub"
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

  # Journey hub: pull-work task roster (queue) beats warehouse table —
  # RelatedDisplayMode.QUEUE (framework cycle 1494) + open hops to Task detail.
  related tasks "Tasks":
    display: queue
    show: Task
    columns: title, status, priority, assigned_to, due_date

  # Pull-next milestone roster (not status_cards warehouse) — ST-001/004 story_walk dig.
  related milestones "Milestones":
    display: queue
    show: Milestone
    columns: name, status, end_date

surface task_list "Tasks":
  uses entity Task
  mode: list
  # Triple open (cycle 1586 story_walk): task hub, parent project, assignee teammate.
  # Prior dual Task|Project (1563); assignee hop completes ST-002/005 teammate path.
  open: Task via id | Project via parent_project | User via assigned_to
  section main:
    field title "Title"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assignee"
    field parent_project "Project"
    field due_date "Due"
    field labels "Labels"
  ux:
    purpose: "Work across projects — open task hub, parent project, or assignee teammate"
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

  # Task hub discussion as pull roster queue (body-first), not warehouse
  # table — ST-003 member task hub path (cycle 1502 agent_acceptance_panel).
  related comments "Discussion":
    display: queue
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
  # Triple open (agent_acceptance dig cycle 1595): note hub, parent task, author teammate.
  open: Comment via id | Task via task | User via author
  section main:
    field task "Task"
    field author "Author"
    field body "Comment"
    field created_at "Date"
  ux:
    purpose: "Discussion across tasks — open a row for the comment, task, or author hub"
    sort: created_at desc
    filter: task, author
    empty: "No comments yet."

# View surface so dual-open Comment via id lands a readable note (not edit maze).
surface comment_detail "Comment Detail":
  uses entity Comment
  mode: view
  section summary "Comment":
    field task "Task"
    field author "Author"
    field body "Comment"
    field created_at "Date"
  ux:
    purpose: "Read a discussion note in context of the parent Task"

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
  # Dual open: milestone edit/context + parent project hub.
  open: Milestone via id | Project via parent_project
  section main:
    field name "Name"
    field status "Status"
    field parent_project "Project"
    field start_date "Start"
    field end_date "End"
  ux:
    purpose: "Milestones by project — open a row for the milestone or parent project hub"

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
  # Triple open (agent_acceptance dig cycle 1595): file hub, parent task, uploader teammate.
  open: Attachment via id | Task via task | User via uploaded_by
  section main:
    field task "Task"
    field filename "File"
    field uploaded_by "Uploaded By"
    field created_at "Date"
  ux:
    purpose: "Files across tasks — open a row for the attachment, task, or uploader hub"
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

# Cycle 1347 / PENDING #303 — User VIEW hub so kanban assignee FK hops
# (/app/user/{id}) land on a real page after ref_route→detail_path fix (c1345).
surface user_list "Team Members":
  uses entity User
  mode: list
  open: User via id
  access: persona(admin, manager, member)

  section main "Team":
    field name "Name"
    field email "Email"
    field role "Role"
    field department "Department"
    field is_active "Active"

  ux:
    purpose: "Team roster — open a member for identity and assigned work"
    sort: name asc
    filter: role, department, is_active
    search: name, email
    empty: "No team members yet."

surface user_detail "Team Member Overview":
  uses entity User
  mode: view
  access: persona(admin, manager, member)

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

  # Teammate hub: assigned work as prioritised queue (RelatedDisplayMode.QUEUE).
  related assigned_work "Assigned work":
    display: queue
    show: Task
    columns: title, status, priority, parent_project, due_date

  related owned_projects "Owned projects":
    display: queue
    show: Project
    columns: name, status, target_date

  ux:
    purpose: "Context hub — identity, role, and related work from assignee hops"

surface user_edit "Edit Team Member":
  uses entity User
  mode: edit
  access: persona(admin)

  section identity "Identity":
    field name "Name"
    field email "Email"

  section organisation "Organisation":
    field role "Role"
    field department "Department"
    # HM Switch — account on-off (boolean_settings_switch)
    field is_active "Active" widget=switch
