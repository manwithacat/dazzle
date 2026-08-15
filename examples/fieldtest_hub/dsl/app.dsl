# DAZZLE - FieldTest Hub
# Distributed beta testing platform for hardware field testing
# Demonstrates v0.7.0 Business Logic Features:
# - State machines for device and issue lifecycle
# - Computed fields for metrics
# - Invariants for data validation
# - Access rules for role-based control

module fieldtest_hub.core

app fieldtest_hub "FieldTest Hub":
  security_profile: basic

# =============================================================================
# PERSONAS
# =============================================================================

persona admin "Administrator":
  # Product fleet desk — not framework platform chrome (#1626).
  default_workspace: manager_ops

persona engineer "Engineer":
  goals:
    - "Monitor all devices and issues"
    - "Manage firmware releases"
    - "Coordinate testers"
  proficiency_level: expert
  session_style: deep_work
  default_workspace: engineering_dashboard
  uses nav engineer_nav

persona tester "Field Tester":
  goals:
    - "Report issues from the field"
    - "Log test sessions"
    - "Track assigned devices"
  proficiency_level: intermediate
  session_style: task_based
  default_workspace: tester_dashboard
  uses nav tester_nav

persona manager "Manager":
  goals:
    - "See fleet health at a glance (active, prototype, recalled devices)"
    - "Track tester field activity and recent test sessions"
    - "Monitor critical issues and overall product quality"
  proficiency_level: intermediate
  session_style: quick_check
  # Answer-first landing (product maturity): fleet ops desk, not shared eng mega-board
  default_workspace: manager_ops
  uses nav manager_nav

# Curated sidebars: workspace destinations only (WI primary N).
nav engineer_nav:
  group "Engineering":
    engineering_dashboard
    issue_triage
    firmware_pipeline
    tester_roster
    device_fleet
    draft_releases

nav tester_nav:
  group "Field":
    tester_dashboard
    field_kit

nav manager_nav:
  group "Ops":
    manager_ops
    engineering_dashboard
    issue_triage
    firmware_pipeline
    tester_roster
    device_fleet
    draft_releases

# =============================================================================
# ENTITIES WITH v0.7 BUSINESS LOGIC
# =============================================================================

# Entity: Device
entity Device "Device":
  intent: "A physical hardware unit produced in a batch, assigned to a Tester, and tracked through prototype/active/recalled/retired states"
  domain: hardware
  patterns: lifecycle, inventory, audit_trail
  display_field: name
  id: uuid pk
  name: str(200) required
  model: str(200) required
  batch_number: str(100) required
  serial_number: str(100) required unique
  manufacturer: str(200)
  firmware_version: str(50)
  status: enum[prototype,active,recalled,retired]=prototype
  assigned_tester_id: ref Tester
  deployed_at: datetime
  # Goal B media (cycle 2080): bench/unit photo — pixels of the fleet, not defect evidence.
  photo_url: url
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # State machine: device lifecycle
  transitions:
    prototype -> active: requires firmware_version
    active -> recalled
    active -> retired
    recalled -> active: role(engineer)
    retired -> prototype: role(engineer)

  permit:
    list: role(engineer) or role(manager) or role(tester)
    read: role(engineer) or role(manager) or role(tester)
    create: role(engineer)
    update: role(engineer)
    delete: role(engineer)
  scope:
    list: assigned_tester_id = current_user
      as: tester
    list: all
      as: engineer, manager
    read: assigned_tester_id = current_user
      as: tester
    read: all
      as: engineer, manager
    # v0.71.19 (#1123): engineers manage the device fleet. Testers see
    # but don't mutate the device record itself (they file IssueReports
    # against it instead). All write ops are engineer-only.
    create: all
      as: engineer
    update: all
      as: engineer
    delete: all
      as: engineer

  index batch_number
  index status
  index assigned_tester_id

  fitness:
    # serial_number first — queue/list identity (unique serial) must survive
    # fitness workspace projection (cycle 1928; peer of Ticket.ticket_number).
    repr_fields: [serial_number, name, model, photo_url, status, firmware_version, assigned_tester_id]

# Entity: Tester
entity Tester "Tester":
  intent: "A field-testing volunteer or employee who is assigned Devices, logs TestSessions, and reports IssueReports"
  domain: identity
  patterns: profile, assignment
  display_field: name
  id: uuid pk
  name: str(200) required pii(category=identity)
  email: str(255) required unique pii(category=contact)
  location: str(200) required pii(category=location)
  skill_level: enum[casual,enthusiast,engineer]=casual
  joined_at: datetime auto_add
  active: bool=true
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Invariant: testers must have valid email
  invariant: email != null

  permit:
    list: role(engineer) or role(manager) or role(tester)
    read: role(engineer) or role(manager) or role(tester)
    create: role(engineer)
    update: role(engineer)
    delete: role(engineer)
  scope:
    list: all
      as: engineer, manager, tester
    read: all
      as: engineer, manager, tester
    # v0.71.19 (#1123): tester management is engineer-controlled.
    create: all
      as: engineer
    update: all
      as: engineer
    delete: all
      as: engineer

  index email
  index location

  fitness:
    # Cycle 1935 agent_acceptance: tester roster/media cards show identity
    # chips (name/location/skill) — not Email / Active schema dump
    # (peer support_tickets User 1933, contact_manager 1931, simple_task 1925).
    # email/active stay on list/detail surfaces.
    repr_fields: [name, location, skill_level]

# Entity: IssueReport
entity IssueReport "Issue Report":
  intent: "A problem observed on a Device during field testing, categorised by severity and tracked from open through triage to fixed/verified/closed"
  domain: quality
  patterns: lifecycle, workflow, audit_trail
  id: uuid pk
  device_id: ref Device required
  reported_by_id: ref Tester required
  category: enum[battery,connectivity,mechanical,overheating,crash,other]=other
  severity: enum[low,medium,high,critical]=medium
  description: text required
  steps_to_reproduce: text
  photo_url: url
  reported_at: datetime auto_add
  status: enum[open,triaged,in_progress,fixed,verified,closed]=open
  resolution: text
  firmware_version: str(50)
  created_at: datetime auto_add
  updated_at: datetime auto_update
  display_field: description

  # Computed field: days since issue was reported
  days_open: computed days_since(reported_at)

  # State machine: issue lifecycle
  transitions:
    open -> triaged
    triaged -> in_progress
    in_progress -> fixed: requires resolution
    fixed -> verified
    fixed -> in_progress
    verified -> closed
    closed -> open: role(engineer)

  # Invariant: fixed issues must have resolution
  invariant: status != fixed or resolution != null
  invariant: status != closed or resolution != null

  permit:
    list: role(engineer) or role(manager) or role(tester)
    read: role(engineer) or role(manager) or role(tester)
    create: role(tester) or role(engineer)
    update: role(engineer) or role(tester)
    delete: role(engineer)
  scope:
    list: reported_by_id = current_user
      as: tester
    update: reported_by_id = current_user
      as: tester
    list: all
      as: engineer, manager
    read: reported_by_id = current_user
      as: tester
    read: all
      as: engineer, manager
    # v0.71.19 (#1123): testers update only their own reports (the
    # `reported_by_id = current_user as: tester` rule above enforces
    # this at runtime now — previously was dead DSL). Engineers
    # update any. Delete is engineer-only (audit trail).
    create: all
      as: tester, engineer
    update: all
      as: engineer
    delete: all
      as: engineer

  index device_id
  index severity, status
  index reported_by_id

  fitness:
    repr_fields: [device_id, category, severity, status, reported_by_id]


# Goal B conversation: peer field-quality tools (Jira / Linear / Zendesk) show
# triage discussion on the ops desk — not only photo grids and severity queues.
entity IssueNote "Issue Note":
  intent: "Engineer/tester discussion on an IssueReport — the conversation that drives triage, mitigation, and close"
  domain: quality
  patterns: messaging, audit_trail
  display_field: body
  id: uuid pk
  issue: ref IssueReport required
  author: str(120) required
  body: text required
  created_at: datetime auto_add

  permit:
    list: role(engineer) or role(manager) or role(tester)
    read: role(engineer) or role(manager) or role(tester)
    create: role(engineer) or role(manager) or role(tester)
    update: role(engineer) or role(manager)
    delete: role(engineer)

  scope:
    list: all
      as: engineer, manager, tester
    read: all
      as: engineer, manager, tester
    create: all
      as: engineer, manager, tester
    update: all
      as: engineer, manager
    delete: all
      as: engineer

  fitness:
    repr_fields: [issue, author, body]




# Goal B document composition: named test briefs/protocols buyers scan above triage notes.
entity TestDocument "Test Document":
  intent: "A named field-test document — brief, protocol, acceptance criteria, field plan, or decision log buyers scan above the triage discussion trail"
  domain: quality
  patterns: documentation, audit_trail
  display_field: headline
  id: uuid pk
  device: ref Device required
  headline: str(200) required
  doc_kind: enum[brief, protocol, acceptance_criteria, field_plan, decision]=brief
  body: text
  status: enum[draft, published, archived]=draft
  author: str(120)
  created_at: datetime auto_add

  # Domain residual status∄transitions (cycle 1845): briefs/protocols publish then archive.
  transitions:
    draft -> published: role(engineer) or role(manager) or role(admin)
    published -> archived: role(engineer) or role(manager) or role(admin)
    draft -> archived: role(admin)
    published -> draft: role(admin)

  permit:
    list: role(engineer) or role(manager) or role(tester) or role(admin)
    read: role(engineer) or role(manager) or role(tester) or role(admin)
    create: role(engineer) or role(manager) or role(admin)
    update: role(engineer) or role(manager) or role(admin)
    delete: role(engineer) or role(admin)

  scope:
    list: all
      as: engineer, manager, tester, admin
    read: all
      as: engineer, manager, tester, admin
    create: all
      as: engineer, manager, admin
    update: all
      as: engineer, manager, admin
    delete: all
      as: engineer, admin

  fitness:
    repr_fields: [device, headline, doc_kind, status, author]

# Entity: TestSession
entity TestSession "Test Session":
  intent: "A logged episode of hands-on testing on a specific Device by a Tester, capturing duration, conditions, and observations"
  domain: quality
  patterns: event_log, audit_trail
  id: uuid pk
  device_id: ref Device required
  tester_id: ref Tester required
  duration_minutes: int
  environment: enum[indoor,outdoor,vehicle,industrial,other]=indoor
  temperature: decimal(5,2)
  notes: text
  logged_at: datetime auto_add
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Invariant: duration must be positive
  invariant: duration_minutes > 0

  permit:
    list: role(engineer) or role(manager) or role(tester)
    read: role(engineer) or role(manager) or role(tester)
    create: role(tester) or role(engineer)
    update: role(tester) or role(engineer)
    delete: role(engineer)
  scope:
    list: tester_id = current_user
      as: tester
    list: all
      as: engineer, manager
    read: tester_id = current_user
      as: tester
    read: all
      as: engineer, manager
    # v0.71.19 (#1123): testers see only their own sessions (list/read)
    # and update only their own (tester_id = current_user enforcement).
    # Engineers update any session.
    create: all
      as: tester, engineer
    update: tester_id = current_user
      as: tester
    update: all
      as: engineer
    delete: all
      as: engineer

  index device_id
  index tester_id
  index logged_at

  fitness:
    repr_fields: [device_id, tester_id, environment, duration_minutes, logged_at]

# Entity: FirmwareRelease
entity FirmwareRelease "Firmware Release":
  intent: "A versioned firmware build that can be rolled out to a Device batch and transitions from draft to released to deprecated"
  domain: hardware
  patterns: lifecycle, versioning, audit_trail
  id: uuid pk
  version: str(50) required unique
  release_notes: text
  release_date: datetime required
  status: enum[draft,released,deprecated]=draft
  applies_to_batch: str(100)
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # State machine: firmware lifecycle
  transitions:
    draft -> released: requires release_notes
    released -> deprecated
    deprecated -> draft: role(engineer)

  # Invariant: released firmware must have release notes
  invariant: status != released or release_notes != null

  permit:
    list: role(engineer) or role(manager) or role(tester)
    read: role(engineer) or role(manager) or role(tester)
    create: role(engineer)
    update: role(engineer)
    delete: role(engineer)
  scope:
    list: all
      as: engineer, manager, tester
    read: all
      as: engineer, manager, tester
    # v0.71.19 (#1123): firmware management is engineer-only.
    create: all
      as: engineer
    update: all
      as: engineer
    delete: all
      as: engineer

  index status
  index version

  fitness:
    repr_fields: [version, status, release_date, applies_to_batch]

# Entity: Task
entity Task "Task":
  intent: "A remediation or investigation task spawned from field testing, assigned between engineers and testers with a lifecycle from open to completed"
  domain: task_management
  patterns: lifecycle, workflow, assignment
  id: uuid pk
  type: enum[debugging,hardware_replacement,firmware_update,recall_request]=debugging
  created_by_id: ref Tester required
  assigned_to_id: ref Tester
  status: enum[open,in_progress,completed,cancelled]=open
  notes: text
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Computed field: days since task was created
  days_open: computed days_since(created_at)

  # State machine: task lifecycle
  transitions:
    open -> in_progress: requires assigned_to_id
    in_progress -> completed
    in_progress -> open
    completed -> open: role(engineer)
    * -> cancelled: role(engineer)

  # Invariant: in_progress tasks must be assigned
  invariant: status != in_progress or assigned_to_id != null

  permit:
    list: role(engineer) or role(manager) or role(tester)
    read: role(engineer) or role(manager) or role(tester)
    create: role(engineer) or role(manager)
    update: role(engineer) or role(manager) or role(tester)
    delete: role(engineer)
  scope:
    list: assigned_to_id = current_user
      as: tester
    list: all
      as: engineer, manager
    read: assigned_to_id = current_user
      as: tester
    read: all
      as: engineer, manager
    # v0.71.19 (#1123): testers update only tasks assigned to them.
    # Engineers/managers create + update + delete any task.
    create: all
      as: engineer, manager
    update: assigned_to_id = current_user
      as: tester
    update: all
      as: engineer, manager
    delete: all
      as: engineer

  index status
  index assigned_to_id
  index created_by_id

  fitness:
    repr_fields: [type, status, assigned_to_id, created_by_id]

# =============================================================================
# SURFACES
# =============================================================================

# Surface: Device Dashboard
surface device_list "Device Dashboard":
  uses entity Device
  mode: list
  render: fragment
  # Dual open: device hub first, assigned tester second (ST-040/044 path).
  open: Device via id | Tester via assigned_tester_id

  section main "Devices":
    field name "Name"
    field model "Model"
    field photo_url "Unit Photo"
    field batch_number "Batch"
    field firmware_version "Firmware"
    field status "Status"
    field serial_number "Serial"
    field assigned_tester_id "Assigned Tester"

  ux:
    purpose: "Monitor field devices — open device hub or hop to assigned tester"
    sort: batch_number asc, status asc
    filter: batch_number, firmware_version, status, assigned_tester_id
    search: name, model, serial_number
    empty: "No devices registered yet. Add your first device to begin field testing!"

    attention critical:
      when: status = recalled
      message: "Device recalled - notify tester"
      action: device_detail

    attention warning:
      when: status = prototype
      message: "Prototype device - handle with care"
      action: device_detail

    as engineer:
      scope: all
      purpose: "Manage all devices across batches"
      action_primary: device_create

    as tester:
      scope: assigned_tester_id = current_user
      purpose: "Your assigned devices"

# Surface: Device Detail — fleet hub (identity / production / assignment + related)
surface device_detail "Device Detail":
  uses entity Device
  mode: view
  render: fragment

  section identity "Identity":
    field name "Name"
    field model "Model"
    field serial_number "Serial Number"
    field photo_url "Unit Photo"

  section production "Production":
    layout: strip
    field batch_number "Batch Number"
    field firmware_version "Firmware Version"
    field status "Status"

  section assignment "Assignment":
    field assigned_tester_id "Assigned Tester"
    field deployed_at "Deployed At"
    field created_at "Created"
    field updated_at "Last Updated"

  # Pull-next issue/session queues (not warehouse tables) — ST-045 journey dig.
  related issues "Issue reports":
    display: queue
    show: IssueReport
    columns: severity, status, category, reported_at

  related sessions "Test sessions":
    display: queue
    show: TestSession
    columns: environment, duration_minutes, logged_at

  # Goal B document: named briefs / protocols on the device hub.
  related documents "Documents":
    display: queue
    show: TestDocument
    columns: headline, doc_kind, status, author

  ux:
    purpose: "Device hub — production strip, assignment, issues, sessions, and test documents"

    as engineer:
      scope: all
      action_primary: device_edit

    as tester:
      scope: assigned_tester_id = current_user
      action_primary: issue_report_create

# Surface: Device Create
surface device_create "Register Device":
  uses entity Device
  mode: create
  render: fragment

  section identity "Identity":
    field name "Device Name"
    field model "Model"
    field manufacturer "Manufacturer" source=companies_house_lookup.search_companies
    field photo_url "Unit Photo"

  section production "Production":
    field batch_number "Batch Number"
    field serial_number "Serial Number"
    field firmware_version "Firmware Version"

  section assignment "Status & Assignment":
    field status "Status"
    field assigned_tester_id "Assign to Tester"

  ux:
    purpose: "Register a new device for field testing"

    as engineer:
      defaults:
        status: prototype

# Surface: Device Edit
surface device_edit "Edit Device":
  uses entity Device
  mode: edit
  render: fragment

  section identity "Identity":
    field name "Device Name"
    field model "Model"
    field manufacturer "Manufacturer" source=companies_house_lookup.search_companies
    field photo_url "Unit Photo"

  section production "Production":
    field batch_number "Batch Number"
    field firmware_version "Firmware Version"

  section assignment "Status & Assignment":
    field status "Status"
    field assigned_tester_id "Assign to Tester"

  ux:
    purpose: "Update device information and status"

    as engineer:
      scope: all

# Surface: Tester Directory
surface tester_list "Tester Directory":
  uses entity Tester
  mode: list
  render: fragment
  open: Tester via id

  section main "Testers":
    field name "Name"
    field email "Email"
    field location "Location"
    field skill_level "Skill Level"
    field active "Active"
    field joined_at "Joined"

  ux:
    purpose: "Manage field testers — open a row for the tester hub"
    sort: name asc
    filter: location, skill_level, active
    search: name, email, location
    empty: "No testers registered yet. Add testers to begin field testing!"

    attention notice:
      when: active = false
      message: "Inactive tester"
      action: tester_detail

    as engineer:
      scope: all
      action_primary: tester_create

# Surface: Tester Detail
surface tester_detail "Tester Detail":
  uses entity Tester
  mode: view
  render: fragment

  section main "Tester Information":
    field name "Name"
    field email "Email"
    field location "Location"
    field skill_level "Skill Level"
    field active "Active"
    field joined_at "Joined At"

  # Pull-next activity/assignment queues — ST-047 journey dig.
  related activity "Testing Activity":
    display: queue
    show: TestSession, IssueReport
    columns: environment, severity, logged_at

  related assignments "Assignments":
    display: queue
    show: Device, Task
    columns: name, status, type

  ux:
    purpose: "Tester hub — activity and assignment queues (not warehouse tables)"

    as engineer:
      scope: all
      action_primary: tester_edit

# Surface: Tester Create
surface tester_create "Register Tester":
  uses entity Tester
  mode: create
  render: fragment

  section identity "Identity":
    field name "Name"
    field email "Email"

  section profile "Profile":
    field location "Location"
    field skill_level "Skill Level"

  section account "Account Status":
    # HM Switch — account on-off (boolean_settings_switch)
    field active "Active" widget=switch

  ux:
    purpose: "Register a new field tester"

    as engineer:
      defaults:
        active: true

# Surface: Tester Edit
surface tester_edit "Edit Tester":
  uses entity Tester
  mode: edit
  render: fragment

  section identity "Identity":
    field name "Name"
    field email "Email"

  section profile "Profile":
    field location "Location"
    field skill_level "Skill Level"

  section account "Account Status":
    # HM Switch — account on-off (boolean_settings_switch)
    field active "Active" widget=switch

  ux:
    purpose: "Update tester information"

    as engineer:
      scope: all

# Surface: Issue Report Board
surface issue_report_list "Issues":
  uses entity IssueReport
  mode: list
  render: fragment
  # Triple open (story_walk dig cycle 1592): issue hub first (ST-037/046 triage),
  # device hub second (fleet), reporter Tester third (who filed).
  open: IssueReport via id | Device via device_id | Tester via reported_by_id

  section main "Issue Reports":
    field photo_url "Evidence"
    field device_id "Device"
    field reported_by_id "Reported By"
    field category "Category"
    field severity "Severity"
    field status "Status"
    field description "Description"
    field reported_at "Reported"

  ux:
    purpose: "Triage field issues — open a row for the issue, Device, or reporter hub"
    sort: severity desc, reported_at desc
    filter: category, severity, status, firmware_version, device_id
    search: description, steps_to_reproduce
    empty: "No issues reported yet - great work!"

    attention critical:
      when: severity = critical and status = open
      message: "Critical issue - requires immediate attention"
      action: issue_report_detail

    attention warning:
      when: severity = high and status = open
      message: "High severity issue"
      action: issue_report_detail

    as engineer:
      scope: all
      purpose: "Manage all field issues"
      action_primary: issue_report_create

    as tester:
      scope: reported_by_id = current_user
      purpose: "Track your reported issues"
      action_primary: issue_report_create

# Surface: Issue Report Detail
surface issue_report_detail "Issue Detail":
  uses entity IssueReport
  mode: view
  render: fragment

  section summary "Summary":
    field device_id "Device"
    field description "Description"
    field reported_by_id "Reported By"

  section classification "Classification":
    layout: strip
    field severity "Severity"
    field status "Status"
    field category "Category"
    field firmware_version "Firmware Version"
    field reported_at "Reported At"

  section evidence "Evidence":
    field steps_to_reproduce "Steps to Reproduce"
    field photo_url "Photo/Video"
    field resolution "Resolution"

  # Goal B conversation (cycle 1899 hub wave): issue hub Discussion uses
  # RelatedDisplayMode.conversation → Message/Bubble chrome (ops/triage
  # live_conversation parity). Peer Linear/Jira issue comments read as a
  # content-first trail on the work item — not queue meta rows.
  related discussion "Discussion":
    display: conversation
    show: IssueNote
    columns: body, author, created_at

  ux:
    purpose: "Issue hub — classification, evidence, and triage discussion"

    as engineer:
      scope: all
      action_primary: issue_report_edit

    as tester:
      scope: reported_by_id = current_user
      action_primary: issue_report_edit

# Surface: Issue Report Create
surface issue_report_create "Report Issue":
  uses entity IssueReport
  mode: create
  render: fragment

  section target "Affected Device":
    field device_id "Device"
    field firmware_version "Firmware Version"

  section classification "Classification":
    field category "Category"
    field severity "Severity"

  section evidence "Evidence":
    field description "Description"
    field steps_to_reproduce "Steps to Reproduce"
    field photo_url "Photo/Video URL"

  ux:
    purpose: "Fast capture of field problems with evidence"

    as tester:
      defaults:
        reported_by_id: current_user
        severity: medium

# Surface: Issue Report Edit
surface issue_report_edit "Update Issue":
  uses entity IssueReport
  mode: edit
  render: fragment

  section classification "Classification":
    field category "Category"
    field severity "Severity"

  section evidence "Evidence":
    field description "Description"
    field steps_to_reproduce "Steps to Reproduce"
    field photo_url "Photo/Video URL"

  section resolution_section "Status & Resolution":
    field status "Status"
    field resolution "Resolution"

  ux:
    purpose: "Update issue status and details"

    as engineer:
      scope: all

    as tester:
      scope: reported_by_id = current_user

# Surface: Test Session List

surface issue_note_list "Issue Notes":
  uses entity IssueNote
  mode: list
  render: fragment
  open: IssueNote via id | IssueReport via issue

  section main "Notes":
    field body "Note"
    field author "Author"
    field issue "Issue"
    field created_at "When"

  ux:
    purpose: "Triage discussion — open a note or its parent issue"
    sort: created_at desc
    search: body, author
    empty: "No issue notes yet"

surface issue_note_detail "Issue Note":
  uses entity IssueNote
  mode: view
  render: fragment

  section summary "Note":
    field body "Note"
    field author "Author"
    field issue "Issue"
    field created_at "When"

  ux:
    purpose: "Read a triage note in context of its parent issue"

surface issue_note_create "Add Issue Note":
  uses entity IssueNote
  mode: create
  render: fragment
  section main "New note":
    field issue "Issue"
    field author "Author"
    field body "Note"

surface test_session_list "Test Sessions":
  uses entity TestSession
  mode: list
  render: fragment
  # Triple open (story_walk dig cycle 1592): session hub first, device second,
  # tester third (who ran the session — ST-043 path).
  open: TestSession via id | Device via device_id | Tester via tester_id

  section main "Test Sessions":
    field device_id "Device"
    field tester_id "Tester"
    field duration_minutes "Duration (min)"
    field environment "Environment"
    field temperature "Temperature"
    field logged_at "Logged At"

  ux:
    purpose: "Track field testing sessions — open a row for the session, Device, or Tester hub"
    sort: logged_at desc
    filter: device_id, tester_id, environment
    search: notes
    empty: "No test sessions logged yet."

    as engineer:
      scope: all
      action_primary: test_session_create

    as tester:
      scope: tester_id = current_user
      action_primary: test_session_create

# Surface: Test Session Create
surface test_session_create "Log Test Session":
  uses entity TestSession
  mode: create
  render: fragment

  section participants "Participants":
    field device_id "Device"
    field tester_id "Tester"

  section conditions "Conditions":
    field environment "Environment"
    field temperature "Temperature"

  section measurements "Measurements":
    field duration_minutes "Duration (minutes)"
    field notes "Notes"

  ux:
    purpose: "Record field testing session details"

    as tester:
      defaults:
        tester_id: current_user
        environment: indoor

surface test_session_detail "Test Session Detail":
  uses entity TestSession
  mode: view
  render: fragment

  section main "Session":
    field device_id "Device"
    field tester_id "Tester"
    field duration_minutes "Duration (min)"
    field environment "Environment"
    field temperature "Temperature"
    field notes "Notes"
    field logged_at "Logged At"

  ux:
    purpose: "Review a logged field-testing session in full detail"

surface test_session_edit "Edit Test Session":
  uses entity TestSession
  mode: edit
  render: fragment

  section main "Edit Test Session":
    field duration_minutes "Duration (minutes)"
    field environment "Environment"
    field temperature "Temperature"
    field notes "Notes"

  ux:
    purpose: "Update test session details after testing"

# Surface: Firmware Release Timeline
surface firmware_release_list "Firmware Releases":
  uses entity FirmwareRelease
  mode: list
  render: fragment
  open: FirmwareRelease via id

  section main "Firmware Releases":
    field version "Version"
    field status "Status"
    field release_date "Release Date"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Track firmware versions — open a row for the release hub"
    sort: release_date desc
    filter: status, applies_to_batch
    search: version, release_notes
    empty: "No firmware releases yet."

    attention warning:
      when: status = deprecated
      message: "Deprecated firmware - upgrade recommended"
      action: firmware_release_detail

    as engineer:
      scope: all
      action_primary: firmware_release_create

# Surface: Firmware Release Detail
surface firmware_release_detail "Firmware Detail":
  uses entity FirmwareRelease
  mode: view
  render: fragment

  section main "Firmware Information":
    field version "Version"
    field release_notes "Release Notes"
    field release_date "Release Date"
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "View firmware release details"

    as engineer:
      scope: all
      action_primary: firmware_release_edit

# Surface: Firmware Release Create
surface firmware_release_create "Create Firmware Release":
  uses entity FirmwareRelease
  mode: create
  render: fragment

  section identity "Release":
    field version "Version"
    field release_date "Release Date"

  section notes "Release Notes":
    field release_notes "Release Notes"

  section rollout "Rollout":
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Create a new firmware release"

    as engineer:
      defaults:
        status: draft

# Surface: Firmware Release Edit
surface firmware_release_edit "Edit Firmware Release":
  uses entity FirmwareRelease
  mode: edit
  render: fragment

  section identity "Release":
    field version "Version"
    field release_date "Release Date"

  section notes "Release Notes":
    field release_notes "Release Notes"

  section rollout "Rollout":
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Update firmware release"

    as engineer:
      scope: all

# Surface: Task List
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: fragment
  # Triple open (journey_dogfood dig cycle 1602): task hub first (ST-040 work
  # queue), assignee second, creator third (who filed the remediation).
  open: Task via id | Tester via assigned_to_id | Tester via created_by_id

  section main "Tasks":
    field type "Type"
    field status "Status"
    field assigned_to_id "Assigned To"
    field created_by_id "Created By"
    field created_at "Created"

  ux:
    purpose: "Track debugging tasks — open task hub, assignee, or creator tester"
    sort: status asc, created_at desc
    filter: type, status, assigned_to_id
    search: notes
    empty: "No tasks yet."

    as engineer:
      scope: all
      action_primary: task_create

# Surface: Task Detail
surface task_detail "Task Detail":
  uses entity Task
  mode: view
  render: fragment

  section main "Task Information":
    field type "Type"
    field created_by_id "Created By"
    field assigned_to_id "Assigned To"
    field status "Status"
    field notes "Notes"
    field created_at "Created At"
    field updated_at "Updated At"

  ux:
    purpose: "View task details"

    as engineer:
      scope: all
      action_primary: task_edit

# Surface: Task Create
surface task_create "Create Task":
  uses entity Task
  mode: create
  render: fragment

  section main "New Task":
    field type "Type"
    field assigned_to_id "Assign To"
    field notes "Notes"

  ux:
    purpose: "Create maintenance or debugging task"

    as engineer:
      defaults:
        created_by_id: current_user
        status: open

# Surface: Task Edit
surface task_edit "Edit Task":
  uses entity Task
  mode: edit
  render: fragment

  section main "Edit Task":
    field type "Type"
    field assigned_to_id "Assign To"
    field status "Status"
    field notes "Notes"

  ux:
    purpose: "Update task status and assignment"

    as engineer:
      scope: all


# TestDocument surfaces (Goal B document composition)
surface test_document_list "Test Documents":
  uses entity TestDocument
  mode: list
  render: fragment
  open: TestDocument via id | Device via device

  section main "Documents":
    field headline "Headline"
    field doc_kind "Kind"
    field device "Device"
    field status "Status"
    field author "Author"
    field created_at "When"

  ux:
    purpose: "Document composition queue — named briefs and protocols; open a letter hub or hop to the Device"
    sort: created_at desc
    filter: doc_kind, status
    search: headline, body
    empty: "No test documents yet — open a device hub to attach a brief or protocol"

surface test_document_create "Add Test Document":
  uses entity TestDocument
  mode: create
  render: fragment
  section main "New document":
    field device "Device"
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field body "Body"
    field author "Author"
  ux:
    purpose: "Attach a named brief, protocol, acceptance criteria, field plan, or decision log to a device"

surface test_document_detail "Test Document":
  uses entity TestDocument
  mode: view
  render: fragment

  section summary "Document":
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field device "Device"
    field author "Author"
    field created_at "When"

  section body "Body":
    field body "Body"

  ux:
    purpose: "Test document hub — named letter, lifecycle strip, device, and body in one place"

surface test_document_edit "Edit Test Document":
  uses entity TestDocument
  mode: edit
  render: fragment
  section main "Edit document":
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field body "Body"
    field author "Author"
  ux:
    purpose: "Update test document headline, kind, or status"

# =============================================================================
# WORKSPACES
# =============================================================================

# Workspace: Engineering Dashboard
# Story-driven (docs/guides/story-to-composition.md):
#   ST-037 triage queue · ST-040 team workload · ST-041 release metrics
#   TR-17 manager focus: fleet KPIs + tester activity first
workspace engineering_dashboard "Engineering Dashboard":
  # Goal B command_density + document (cycle 1843): peer field-quality tools
  # (TestRail / qTest / Jira) put named test briefs/protocols after dual
  # attention and above triage notes — not conversation alone owning the fold.
  # Goal B conversation remains: display: conversation → MessageScroller.
  purpose: "Multi-panel eng home — fleet pulse, dual attention, test docs, then triage notes"
  access: persona(engineer, manager)

  # Fleet overview KPI strip: total/active/prototype/recalled devices + docs.
  fleet_overview:
    source: Device
    display: metrics
    aggregate:
      total_devices: count(Device)
      active_devices: count(Device where status = active)
      prototype_devices: count(Device where status = prototype)
      recalled_devices: count(Device where status = recalled)
      documents: count(TestDocument)
      conversation: count(IssueNote)
    tones:
      active_devices: positive
      recalled_devices: destructive
      prototype_devices: accent
      documents: accent
      conversation: accent

  # TR-35: fleet status without click-through to /app/device — non-active
  # devices as a review queue next to the KPI strip (dual attention A).
  device_attention:
    source: Device
    filter: status != active
    sort: status asc, name asc
    limit: 15
    display: queue
    action: device_detail
    empty: "All registered devices are active"

  # Dual attention B — open triage pressure shares fold with device attention.
  triage_pressure:
    source: IssueReport
    filter: status = open
    sort: severity desc, reported_at desc
    limit: 4
    display: queue
    action: issue_report_edit
    empty: "No open reports to triage"

  # Goal B document composition after dual attention — named briefs before notes.
  composition:
    source: TestDocument
    sort: created_at desc
    limit: 3
    display: queue
    action: test_document_detail
    empty: "No test documents yet — attach a brief or protocol on a device hub"

  # Goal B conversation after dual attention + docs — Message/Bubble chrome.
  live_conversation:
    source: IssueNote
    sort: created_at desc
    limit: 4
    display: conversation
    action: issue_note_detail
    empty: "No conversation yet — notes on field issues appear here"

  tester_activity:
    source: TestSession
    sort: logged_at desc
    limit: 15
    display: timeline
    action: test_session_detail
    empty: "No recent test sessions logged"

  # ST-037 — triage open reports (severity-first), not a generic list.
  triage_queue:
    source: IssueReport
    filter: status = open
    sort: severity desc, reported_at desc
    limit: 20
    display: queue
    action: issue_report_edit
    empty: "No open reports to triage"

  # Work-surface utility: critical open work is a pull queue, not inventory grid.
  critical_issues:
    source: IssueReport
    filter: severity = critical and status != closed
    sort: reported_at desc
    limit: 10
    display: queue
    action: issue_report_detail
    empty: "No critical issues!"

  recent_reports:
    source: IssueReport
    sort: reported_at desc
    limit: 20
    display: timeline
    action: issue_report_detail
    empty: "No recent reports"

  issues_board:
    source: IssueReport
    display: kanban
    group_by: status
    action: issue_report_edit
    empty: "No issues to triage"

  # Work-surface utility (cycle 1486 story_walk): fleet devices are pull-to-open
  # hubs, not a gallery grid.
  active_devices:
    source: Device
    filter: status = active
    sort: batch_number asc
    limit: 50
    display: queue
    action: device_detail
    empty: "No active devices"

  # ST-041 release + issue pressure strip.
  metrics:
    source: IssueReport
    display: metrics
    aggregate:
      total_issues: count(IssueReport)
      critical: count(IssueReport where severity = critical)
      open: count(IssueReport where status = open)
      releases_draft: count(FirmwareRelease where status = draft)
      releases_live: count(FirmwareRelease where status = released)
    tones:
      critical: destructive
      open: warning
      releases_live: positive

  # Work-surface utility: release history is chronological — timeline beats grid.
  firmware_releases:
    source: FirmwareRelease
    sort: release_date desc
    limit: 10
    display: timeline
    action: firmware_release_detail
    empty: "No firmware releases"

  all_tasks:
    source: Task
    filter: status != completed and status != cancelled
    sort: created_at desc
    limit: 20
    display: timeline
    action: task_detail
    empty: "No open tasks"

  task_board:
    source: Task
    display: kanban
    group_by: status
    action: task_detail
    empty: "No tasks"

  firmware_board:
    source: FirmwareRelease
    display: kanban
    group_by: status
    action: firmware_release_edit
    empty: "No firmware releases"

  severity_mix:
    source: IssueReport
    filter: status != closed
    display: bar_chart
    group_by: severity
    aggregate:
      count: count(IssueReport)
    empty: "No open reports"

  device_board:
    source: Device
    display: kanban
    group_by: status
    action: device_edit
    empty: "No devices"

  firmware_timeline:
    source: FirmwareRelease
    sort: release_date desc
    limit: 30
    display: timeline
    action: firmware_release_detail
    empty: "No firmware releases yet"

  device_registry_timeline:
    source: Device
    sort: deployed_at desc
    limit: 30
    display: timeline
    action: device_detail
    empty: "No devices yet"

  all_testers:
    source: Tester
    filter: active = true
    sort: name asc
    # Active tester roster is a pull-next desk (queue), not a dense table scan.
    display: queue
    action: tester_detail
    empty: "No active testers"

  # Device deployment tree — hierarchy by batch_number
  device_tree:
    source: Device
    display: tree
    group_by: batch_number
    action: device_detail
    empty: "No devices registered"

  # Entity diagram — relationships between Device, Tester, IssueReport
  fleet_diagram:
    source: Device
    display: diagram
    empty: "No devices to diagram"

  # Issue categories — tabbed list over IssueReport by status
  issue_tabs:
    source: IssueReport
    display: tabbed_list
    group_by: status
    sort: reported_at desc
    action: issue_report_detail
    empty: "No issues reported"

  # Device geographic distribution — geo-pinned on the device location.
  # Exercises DisplayMode.MAP (unlocked in 0.57.35 — the parser now
  # accepts `map` as an identifier in display-value position).
  device_map:
    source: Device
    display: map
    action: device_detail
    empty: "No devices registered"

  ux:
    as engineer:
      purpose: "Fleet pulse, dual attention, test docs, then triage notes — multi-panel eng home"
      focus: fleet_overview, device_attention, triage_pressure, composition, live_conversation
    as manager:
      # TR-17/TR-35 + Goal B document: fleet KPIs + dual attention + docs before notes.
      purpose: "Fleet overview, dual attention, test documents, and triage notes"
      focus: fleet_overview, device_attention, triage_pressure, composition, live_conversation

# Workspace: Tester Dashboard
# ST-042–044: personal metrics + assigned devices + open issues/tasks as queues
workspace tester_dashboard "Tester Dashboard":
  purpose: "Personal field testing hub"
  access: persona(tester)

  my_stats:
    source: IssueReport
    display: metrics
    aggregate:
      total_reports: count(IssueReport where reported_by_id = current_user)
      critical_found: count(IssueReport where reported_by_id = current_user and severity = critical)
      open_tasks: count(Task where assigned_to_id = current_user and status != completed)
    tones:
      critical_found: destructive
      open_tasks: accent

  # Work-surface utility (cycle 1486 story_walk ST-044): assigned kit is a pull queue.
  my_devices:
    source: Device
    filter: assigned_tester_id = current_user
    sort: name asc
    limit: 15
    display: queue
    action: device_detail
    empty: "No devices assigned to you yet"

  my_issues:
    source: IssueReport
    filter: reported_by_id = current_user
    sort: reported_at desc
    limit: 20
    display: queue
    action: issue_report_detail
    empty: "No issues reported yet"

  my_sessions:
    source: TestSession
    filter: tester_id = current_user
    sort: logged_at desc
    limit: 10
    display: timeline
    empty: "No test sessions logged"

  my_tasks:
    source: Task
    filter: assigned_to_id = current_user and status != completed
    sort: created_at desc
    limit: 10
    display: queue
    action: task_detail
    empty: "No tasks assigned to you"

  my_severity_mix:
    source: IssueReport
    filter: reported_by_id = current_user
    display: bar_chart
    group_by: severity
    aggregate:
      count: count(IssueReport)
    empty: "No issues reported yet"

  ux:
    as tester:
      purpose: "Your field testing activity"
      focus: my_stats, my_devices, my_tasks, my_issues, my_severity_mix

# ── Job workspaces (product maturity: anti-warehouse + nav list share) ───────
# Extra product desks lower list/(list+ws) density and credit multi-workspace
# nav for engineer/manager/tester (auto-discover still lists entities).

workspace manager_ops "Manager Ops":
  # Goal B command_density (cycle 1726) + document (cycle 1843): peer field-ops
  # / TestRail-style homes put ≥2 attention panels then named test briefs above
  # triage notes — not a single conversation queue that eats the viewport.
  # Caps match ops_dashboard command_center fold share.
  purpose: "Multi-panel field ops — quality pulse, dual attention, test docs, then triage notes"
  access: persona(manager, admin)

  # Compact quality pulse first (open / critical / sessions / documents).
  quality_strip:
    source: IssueReport
    display: metrics
    aggregate:
      open: count(IssueReport where status = open)
      critical: count(IssueReport where severity = critical and status != closed)
      sessions: count(TestSession)
      documents: count(TestDocument)
      conversation: count(IssueNote)
    tones:
      open: warning
      critical: destructive
      documents: accent
      conversation: accent

  # Attention panel 1 — critical open field issues (cap for fold share).
  critical_issues:
    source: IssueReport
    filter: severity = critical and status != closed
    sort: reported_at desc
    limit: 4
    display: queue
    action: issue_report_detail
    empty: "No critical issues!"

  # Attention panel 2 — non-active fleet (prototype / recalled / offline).
  device_attention:
    source: Device
    filter: status != active
    sort: status asc, name asc
    limit: 4
    display: queue
    action: device_detail
    empty: "All registered devices are active"

  # Goal B document composition after dual attention — named briefs before notes.
  composition:
    source: TestDocument
    sort: created_at desc
    limit: 3
    display: queue
    action: test_document_detail
    empty: "No test documents yet — attach a brief or protocol on a device hub"

  # Goal B conversation shares the fold — Message/Bubble chrome (not queue meta);
  # cap so dual attention + docs stay visible (command_density + document).
  live_conversation:
    source: IssueNote
    sort: created_at desc
    limit: 4
    display: conversation
    action: issue_note_detail
    empty: "No conversation yet — notes on field issues appear here"

  fleet_overview:
    source: Device
    display: metrics
    aggregate:
      total_devices: count(Device)
      active_devices: count(Device where status = active)
      prototype_devices: count(Device where status = prototype)
      recalled_devices: count(Device where status = recalled)
      documents: count(TestDocument)
      conversation: count(IssueNote)
    tones:
      active_devices: positive
      recalled_devices: destructive
      prototype_devices: accent
      documents: accent
      conversation: accent

  ux:
    as manager:
      purpose: "Quality pulse, dual attention, test docs above fold — live notes share the fold"
      focus: quality_strip, critical_issues, device_attention, composition, live_conversation
    as admin:
      purpose: "Multi-panel field quality oversight — dual attention and test documents first"
      focus: quality_strip, critical_issues, device_attention, composition, live_conversation

  tester_activity:
    source: TestSession
    sort: logged_at desc
    limit: 15
    display: timeline
    action: test_session_detail
    empty: "No recent test sessions logged"

  open_work:
    source: Task
    filter: status != completed and status != cancelled
    display: kanban
    group_by: status
    action: task_detail
    empty: "No open tasks"

  # empty_region_honesty (cycle 1855): multi-panel ops keeps pulse + dual attention
  # + docs + notes + under-fold session/task boards — not a fleet status bar dump
  # (bar_chart dogfood stays on engineering_dashboard / tester_dashboard).

workspace issue_triage "Issue Triage":
  # Goal B conversation + media + empty_region_honesty (cycle 1855) + media
  # peer-pack (cycle 2059): recipe severity_evidence_density — TestRail /
  # BrowserStack put P0/critical photo shelves vs high-severity evidence as
  # dual media grids (not one mixed field_evidence dump or headshot shelf).
  purpose: "Critical vs high field photo density, triage notes, then open queues"
  access: persona(engineer, manager)

  open_pressure:
    source: IssueReport
    display: metrics
    aggregate:
      open: count(IssueReport where status = open)
      critical: count(IssueReport where severity = critical and status != closed)
      high: count(IssueReport where severity = high and status != closed)
      critical_photos: count(IssueReport where severity = critical and photo_url != null and status != closed)
      high_photos: count(IssueReport where severity = high and photo_url != null and status != closed)
      conversation: count(IssueNote)
    tones:
      open: warning
      critical: destructive
      high: warning
      critical_photos: danger
      high_photos: warning
      conversation: accent

  # Goal B media dual density — exclusive severity photo grids (caps for fold).
  critical_evidence:
    source: IssueReport
    filter: severity = critical and photo_url != null and status != closed
    sort: reported_at desc
    limit: 4
    display: grid
    action: issue_report_detail
    empty: "No critical field photos — attach evidence on P0 reports"

  high_evidence:
    source: IssueReport
    filter: severity = high and photo_url != null and status != closed
    sort: reported_at desc
    limit: 4
    display: grid
    action: issue_report_detail
    empty: "No high-severity field photos yet"

  # Conversation trail after dual media density (still Message chrome).
  live_conversation:
    source: IssueNote
    sort: created_at desc
    limit: 4
    display: conversation
    action: issue_note_detail
    empty: "No triage conversation yet — engineer notes on open issues appear here"

  # Mixed photo shelf under dual density (scroll) — not a third focus twin.
  field_evidence:
    source: IssueReport
    filter: photo_url != null and (status = open or status = triaged or status = in_progress)
    sort: severity desc, reported_at desc
    limit: 8
    display: grid
    action: issue_report_detail
    empty: "No field photos yet — ask testers to attach evidence"

  triage_queue:
    source: IssueReport
    filter: status = open
    sort: severity desc, reported_at desc
    limit: 12
    display: queue
    action: issue_report_edit
    empty: "No open reports to triage"

  # Work-surface utility: critical open work is a pull queue, not inventory grid.
  critical_issues:
    source: IssueReport
    filter: severity = critical and status != closed
    sort: reported_at desc
    limit: 8
    display: queue
    action: issue_report_detail
    empty: "No critical issues!"

  ux:
    as engineer:
      purpose: "Critical vs high field photo density before notes and open triage queue"
      focus: open_pressure, critical_evidence, high_evidence, live_conversation
    as manager:
      purpose: "Critical vs high field photo density — quality pressure with pixels first"
      focus: open_pressure, critical_evidence, high_evidence, live_conversation

workspace firmware_pipeline "Firmware Pipeline":
  # Goal B empty_region_honesty (cycle 1855): peer ship desks keep pulse + board
  # + one release history + open-task queue — not status bar dumps under the desk.
  purpose: "Ship firmware — release board, live drafts, and related open tasks"
  access: persona(engineer, manager)

  release_metrics:
    source: FirmwareRelease
    display: metrics
    aggregate:
      drafts: count(FirmwareRelease where status = draft)
      live: count(FirmwareRelease where status = released)
      open_tasks: count(Task where status != completed and status != cancelled)
    tones:
      drafts: warning
      live: positive
      open_tasks: accent

  # Work-surface utility: release history is chronological — timeline beats grid.
  firmware_releases:
    source: FirmwareRelease
    sort: release_date desc
    limit: 15
    display: timeline
    action: firmware_release_detail
    empty: "No firmware releases"

  firmware_board:
    source: FirmwareRelease
    display: kanban
    group_by: status
    action: firmware_release_edit
    empty: "No firmware releases"

  # Open ship work as a pull queue (not a second timeline twin of release history).
  release_tasks:
    source: Task
    filter: status != completed and status != cancelled
    sort: created_at desc
    limit: 15
    display: queue
    action: task_detail
    empty: "No open tasks"

workspace field_kit "Field Kit":
  # Goal B media peer-pack upgrade (cycle 1944): road testers scan field photo
  # evidence before device queues — peer field tools put pixels first, not meta
  # lists alone (recipe road_kit_evidence; ban headshot_shelf; not document/
  # conversation re-stack after 1940–1942).
  purpose: "Tester kit — field photo evidence, assigned devices, and sessions on the road"
  access: persona(tester)

  kit_pulse:
    source: Device
    display: metrics
    aggregate:
      assigned: count(Device where assigned_tester_id = current_user)
      open_tasks: count(Task where assigned_to_id = current_user and status != completed)
      sessions: count(TestSession where tester_id = current_user)
      evidence: count(IssueReport where reported_by_id = current_user and photo_url != null)
    tones:
      open_tasks: accent
      assigned: positive
      evidence: accent

  # Goal B media FIRST — my field photos (preview thumbs) before assignment dump.
  field_evidence:
    source: IssueReport
    filter: reported_by_id = current_user and photo_url != null
    sort: reported_at desc
    limit: 8
    display: grid
    action: issue_report_detail
    empty: "No field photos yet — attach evidence when you file an issue"

  # Work-surface utility (cycle 1486 story_walk): field kit assignments → queue.
  assigned_devices:
    source: Device
    filter: assigned_tester_id = current_user
    sort: name asc
    limit: 12
    display: queue
    action: device_detail
    empty: "No devices assigned to you yet"

  recent_sessions:
    source: TestSession
    filter: tester_id = current_user
    sort: logged_at desc
    limit: 10
    display: timeline
    empty: "No test sessions logged"

  my_open_tasks:
    source: Task
    filter: assigned_to_id = current_user and status != completed
    sort: created_at desc
    limit: 8
    display: queue
    action: task_detail
    empty: "No open tasks"

  my_task_flow:
    source: Task
    filter: assigned_to_id = current_user and status != completed and status != cancelled
    display: kanban
    group_by: status
    action: task_detail
    empty: "No open tasks"

  ux:
    as tester:
      purpose: "Road kit — field photo evidence first, then devices, sessions, and open tasks"
      focus: kit_pulse, field_evidence, assigned_devices, recent_sessions, my_open_tasks

workspace tester_roster "Tester Roster":
  # Goal B org_structure (cycle 1848): peer field-test tools (TestFlight /
  # Beta programs / LabTrack) show testers by skill tier and region before a
  # flat name dump — managers assign devices from org shape, not a warehouse list.
  purpose: "Org structure for field capacity — skill and region before flat roster and unassigned devices"
  access: persona(engineer, manager)

  roster_metrics:
    source: Tester
    display: metrics
    aggregate:
      testers: count(Tester)
      active: count(Tester where active = true)
      devices: count(Device where assigned_tester_id != null)
      sessions: count(TestSession)
    tones:
      active: positive
      devices: accent

  # Skill board (casual / enthusiast / engineer) — capacity authority shape.
  by_skill:
    source: Tester
    filter: active = true
    display: kanban
    group_by: skill_level
    sort: name asc
    limit: 40
    action: tester_detail
    empty: "No active testers"

  # Region queue — location placement before flat roster (geo org for field kits).
  by_location:
    source: Tester
    filter: active = true
    display: queue
    sort: location asc, name asc
    limit: 40
    action: tester_detail
    empty: "No active testers"

  # Secondary flat roster (after hierarchy) — still pull-to-open hubs (ST-047).
  active_testers:
    source: Tester
    filter: active = true
    sort: location asc, name asc
    limit: 25
    display: queue
    action: tester_detail
    empty: "No active testers"

  unassigned_devices:
    source: Device
    filter: assigned_tester_id = null and status = active
    sort: name asc
    limit: 15
    display: queue
    action: device_detail
    empty: "Every active device has a tester"

  # empty_region_honesty (cycle 1855): org desk keeps hierarchy + unassigned load —
  # not a session timeline dump (session history lives on eng home / tester home).

  org_hint:
    display: status_list
    entries:
      - title: "By skill board"
        caption: "Casual / Enthusiast / Engineer columns show who can take hard kits"
        icon: "users"
        state: accent
      - title: "Region queue"
        caption: "Testers sorted by location before flat roster and unassigned devices"
        icon: "map-pin"
        state: positive
      - title: "Unassigned devices"
        caption: "Active devices without a tester — assign after you read org shape"
        icon: "cpu"
        state: warning

  ux:
    as manager:
      purpose: "See testers by skill and region before unassigned device load"
      focus: roster_metrics, by_skill, by_location, active_testers
    as engineer:
      purpose: "Read field capacity by skill tier and location before assignment"
      focus: roster_metrics, by_skill, by_location, active_testers


workspace device_fleet "Device Fleet":
  # Goal B empty_region_honesty (cycle 1855): peer fleet desks keep pulse + work
  # queues — not a twin device timeline + status bar dump (chart/timeline dogfood
  # stays on engineering_dashboard).
  # Goal B org_structure peer-pack upgrade (cycle 1938): model + lifecycle
  # columns before flat load — hardware ops parse Probe/Gateway/Sensor shape
  # and prototype→active→recalled stages (recipe fleet_model_hierarchy; not
  # dual_attention / headshot_shelf).
  # Goal B media upgrade (cycle 2080): recipe device_identity_wall — TestFlight /
  # Apple Configurator / LabTrack put hardware unit photos on the fleet desk so
  # operators pick the right bench unit. Defect pixels stay on issue_triage
  # (severity_evidence_density); this is pixels of the fleet, not another
  # IssueReport photo filter or headshot_shelf.
  purpose: "Hardware identity wall, then fleet org — model and lifecycle before pressure queues"
  access: persona(engineer, manager)

  fleet_metrics:
    source: Device
    display: metrics
    aggregate:
      active: count(Device where status = active)
      prototype: count(Device where status = prototype)
      recalled: count(Device where status = recalled)
      unassigned: count(Device where assigned_tester_id = null)
      identified: count(Device where photo_url != null)
    tones:
      active: positive
      prototype: accent
      recalled: destructive
      unassigned: warning
      identified: accent

  # Goal B media FIRST — bench/unit photos (preview thumbs) before org boards.
  hardware_identity:
    source: Device
    filter: photo_url != null
    sort: model asc, serial_number asc
    limit: 8
    display: grid
    action: device_detail
    empty: "No unit photos yet — attach a bench photo when you register a device"

  # Org structure: lifecycle columns (enum kanban — status is the fleet hierarchy).
  by_status:
    source: Device
    display: kanban
    group_by: status
    sort: serial_number asc
    limit: 30
    action: device_detail
    empty: "No devices in this lifecycle stage"

  # Org structure: model-sorted roster — free-string model is not kanban-groupable
  # (empty board dogfood); serial/name fitness shows family placement in queue meta.
  by_model:
    source: Device
    sort: model asc, serial_number asc
    limit: 24
    display: queue
    action: device_detail
    empty: "No devices registered in the fleet"

  # Unassigned stock — capacity gap buyers scan after org boards.
  unassigned_devices:
    source: Device
    filter: assigned_tester_id = null
    sort: model asc, serial_number asc
    limit: 12
    display: queue
    action: device_detail
    empty: "Every device has a tester assignment"

  # Work-surface utility (cycle 1486 story_walk ST-045): fleet active devices → queue.
  active_devices:
    source: Device
    filter: status = active
    sort: name asc
    limit: 12
    display: queue
    action: device_detail
    empty: "No active devices"

  recall_queue:
    source: Device
    filter: status = recalled
    sort: updated_at desc
    limit: 8
    display: queue
    action: device_detail
    empty: "No recalled devices"

  ux:
    as engineer:
      purpose: "Hardware identity first, then lifecycle board + model roster"
      focus: fleet_metrics, hardware_identity, by_status, by_model
    as manager:
      purpose: "Unit photos first — fleet shape after hardware identity"
      focus: fleet_metrics, hardware_identity, by_status, by_model

workspace draft_releases "Draft Releases":
  # Goal B empty_region_honesty (cycle 1855): one draft queue + pulse — not twin
  # draft queues, draft trail, and status bar theater.
  purpose: "Draft firmware pressure — unshipped builds without warehouse CRUD"
  access: persona(engineer, manager)

  draft_metrics:
    source: FirmwareRelease
    display: metrics
    aggregate:
      drafts: count(FirmwareRelease where status = draft)
      released: count(FirmwareRelease where status = released)
      deprecated: count(FirmwareRelease where status = deprecated)
    tones:
      drafts: warning
      released: positive
      deprecated: accent

  draft_queue:
    source: FirmwareRelease
    filter: status = draft
    sort: release_date desc
    limit: 20
    display: queue
    action: firmware_release_edit
    empty: "No draft firmware releases"

ledger DeviceCost "Device Cost Account":
  intent: "Accrue repair and replacement expenses against the fleet of field devices"
  account_code: 5100
  ledger_id: 1
  account_type: expense
  currency: GBP

ledger OperationsBudget "Operations Budget":
  intent: "Draw down the field-test programme's allocated operations budget"
  account_code: 1100
  ledger_id: 1
  account_type: asset
  currency: GBP

# =============================================================================
# TRANSACTION — record a repair cost against the budget
# =============================================================================

transaction RecordRepair "Record Repair Cost":
  intent: "Charge a device repair to the cost account and draw it from operations budget"
  transfer repair_expense:
    debit: DeviceCost
    credit: OperationsBudget
    amount: event.amount
    code: 1

  idempotency_key: event.id

# =============================================================================
# RHYTHMS — longitudinal persona journeys (#1559 follow-on)
# Thin temporal ordering over existing stories: each scene cites an ST-xxx,
# it does not re-describe the behaviour. Verify with `dazzle rhythm fidelity`.
# =============================================================================

rhythm engineer_lifecycle "Engineer — Device Lifecycle":
  persona: engineer
  cadence: "continuous"

  # Setup — bring a new device online.
  phase setup:
    kind: onboarding
    # Thin form (#1559 slice 3): surface (device_create), action (submit) and
    # entity (Device) are all derived from the cited story ST-019 at link time.
    scene register_device "Register a new device":
      story: ST-019
      expects: "A new device is recorded in prototype state"
    scene activate_device "Promote the device to active":
      on: device_detail
      action: approve
      entity: Device
      story: ST-020
      expects: "A validated prototype moves to active and is testable in the field"

  # Operate — triage and drive issue reports to resolution.
  phase operate:
    kind: active
    depends_on: setup
    scene triage_issues "Triage incoming issue reports":
      on: issue_report_list
      action: review
      entity: IssueReport
      story: ST-037
      expects: "Recent open issue reports are reviewed and prioritised"
    scene advance_issue "Take a triaged issue into progress":
      on: issue_report_detail
      action: submit
      entity: IssueReport
      story: ST-026
      expects: "A triaged issue is picked up and moves to in_progress"
    scene fix_issue "Mark an issue fixed":
      on: issue_report_detail
      action: approve
      entity: IssueReport
      story: ST-027
      expects: "An in_progress issue is confirmed fixed"

  # Release — cut and ship firmware across a device batch.
  phase release:
    kind: periodic
    cadence: "each firmware cycle"
    depends_on: operate
    scene cut_firmware "Draft a firmware release":
      on: firmware_release_create
      action: submit
      entity: FirmwareRelease
      story: ST-029
      expects: "A new firmware release is drafted"
    scene ship_firmware "Ship the firmware release":
      on: firmware_release_detail
      action: approve
      entity: FirmwareRelease
      story: ST-030
      expects: "A drafted release moves to released and is available to devices"
    scene link_batch "Link the release to a device batch":
      on: firmware_release_detail
      action: submit
      entity: FirmwareRelease
      story: ST-038
      expects: "The release is associated with the devices it targets"

  # Retire — recall or retire devices at end of life.
  phase retire:
    kind: offboarding
    scene recall_device "Recall a device":
      on: device_detail
      action: approve
      entity: Device
      story: ST-039
      expects: "A device with a field fault is pulled from service"
    scene retire_device "Retire a device":
      on: device_detail
      action: approve
      entity: Device
      story: ST-022
      expects: "An end-of-life device is moved to retired"

rhythm tester_fieldwork "Field Tester — Test Visit":
  persona: tester
  cadence: "each field visit"

  phase fieldwork:
    kind: active
    # Thin form (#1559 slice 3): device_list / browse / Device all derived from
    # the cited story ST-044.
    scene check_assignments "Check assigned devices":
      story: ST-044
      expects: "The tester sees the devices assigned to them for this visit"
    scene run_session "Log a test session":
      on: test_session_create
      action: submit
      entity: TestSession
      story: ST-043
      expects: "A completed test session is recorded against a device"
    scene report_issue "Report a device issue":
      on: issue_report_create
      action: submit
      entity: IssueReport
      story: ST-042
      expects: "A field fault is reported and linked to the device"

rhythm manager_oversight "Manager — Weekly Review":
  persona: manager
  cadence: "weekly"

  phase review:
    kind: periodic
    cadence: "weekly"
    scene check_workload "Review team workload":
      on: engineering_dashboard
      action: review
      entity: Task
      story: ST-040
      expects: "Open task load across testers is visible at a glance"
    scene track_releases "Track release progress":
      on: firmware_release_list
      action: review
      entity: FirmwareRelease
      story: ST-041
      expects: "In-flight firmware releases and their states are visible"
