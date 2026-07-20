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
  # WI N: job desks first — not auto entity-list soup
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
    session_ops
    tester_roster
    task_ops
    device_fleet
    critical_ops
    prototype_ops
    recall_ops
    retired_ops
    draft_releases
    released_ops

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
    session_ops
    tester_roster
    task_ops
    device_fleet
    critical_ops
    prototype_ops
    recall_ops
    retired_ops
    draft_releases
    released_ops

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
    repr_fields: [name, model, status, firmware_version, assigned_tester_id]

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
    repr_fields: [name, email, location, skill_level, active]

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
  photo_url: str(500)
  reported_at: datetime auto_add
  status: enum[open,triaged,in_progress,fixed,verified,closed]=open
  resolution: text
  firmware_version: str(50)
  created_at: datetime auto_add
  updated_at: datetime auto_update

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
  open: Device via id

  section main "Devices":
    field name "Name"
    field model "Model"
    field batch_number "Batch"
    field firmware_version "Firmware"
    field status "Status"
    field serial_number "Serial"

  ux:
    purpose: "Monitor field devices — open a row for the device hub"
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

  related issues "Issue reports":
    display: table
    show: IssueReport
    columns: severity, status, category, reported_at

  related sessions "Test sessions":
    display: table
    show: TestSession

  ux:
    purpose: "Device hub — production strip, assignment, issues, and sessions"

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

  related activity "Testing Activity":
    display: table
    show: TestSession, IssueReport

  related assignments "Assignments":
    display: table
    show: Device, Task

  ux:
    purpose: "View tester details and activity"

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
    field active "Active"

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
    field active "Active"

  ux:
    purpose: "Update tester information"

    as engineer:
      scope: all

# Surface: Issue Report Board
surface issue_report_list "Issues":
  uses entity IssueReport
  mode: list
  render: fragment
  open: Device via device_id

  section main "Issue Reports":
    field device_id "Device"
    field category "Category"
    field severity "Severity"
    field status "Status"
    field description "Description"
    field reported_at "Reported"

  ux:
    purpose: "Triage field issues — open a row for the parent Device hub"
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

  ux:
    purpose: "Issue hub — classification strip and evidence for triage"

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
surface test_session_list "Test Sessions":
  uses entity TestSession
  mode: list
  render: fragment
  open: Device via device_id

  section main "Test Sessions":
    field device_id "Device"
    field tester_id "Tester"
    field duration_minutes "Duration (min)"
    field environment "Environment"
    field temperature "Temperature"
    field logged_at "Logged At"

  ux:
    purpose: "Track field testing sessions and usage patterns"
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
  open: Task via id

  section main "Tasks":
    field type "Type"
    field status "Status"
    field assigned_to_id "Assigned To"
    field created_at "Created"

  ux:
    purpose: "Track debugging tasks — open a row for the task hub"
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

# =============================================================================
# WORKSPACES
# =============================================================================

# Workspace: Engineering Dashboard
# Story-driven (docs/guides/story-to-composition.md):
#   ST-037 triage queue · ST-040 team workload · ST-041 release metrics
#   TR-17 manager focus: fleet KPIs + tester activity first
workspace engineering_dashboard "Engineering Dashboard":
  purpose: "Fleet overview, tester activity, and field-quality oversight"
  access: persona(engineer, manager)

  # Fleet overview KPI strip: total/active/prototype/recalled devices.
  fleet_overview:
    source: Device
    display: metrics
    aggregate:
      total_devices: count(Device)
      active_devices: count(Device where status = active)
      prototype_devices: count(Device where status = prototype)
      recalled_devices: count(Device where status = recalled)
    tones:
      active_devices: positive
      recalled_devices: destructive
      prototype_devices: accent

  # TR-35: fleet status without click-through to /app/device — non-active
  # devices as a review queue next to the KPI strip.
  device_attention:
    source: Device
    filter: status != active
    sort: status asc, name asc
    limit: 15
    display: queue
    action: device_detail
    empty: "All registered devices are active"

  # WI D: context family for tester activity (not list pad)
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

  # WI D: grid family for critical cards
  critical_issues:
    source: IssueReport
    filter: severity = critical and status != closed
    sort: reported_at desc
    limit: 10
    display: grid
    action: issue_report_detail
    empty: "No critical issues!"

  # WI D: context family for recent reports
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

  # WI D: grid family for active fleet
  active_devices:
    source: Device
    filter: status = active
    sort: batch_number asc
    limit: 50
    display: grid
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

  # WI D: grid family for release cards
  firmware_releases:
    source: FirmwareRelease
    sort: release_date desc
    limit: 10
    display: grid
    action: firmware_release_detail
    empty: "No firmware releases"

  # WI D: context family for open work trail
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

  # WI D: chart family — severity mix on open reports
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
    display: list
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
      purpose: "Triage field issues and ship firmware"
      focus: triage_queue, critical_issues, metrics, all_tasks, firmware_releases

    as manager:
      # TR-17/TR-35: fleet KPIs + non-active device queue first (no /app/device hop).
      purpose: "Fleet overview, tester activity, and product quality"
      focus: fleet_overview, device_attention, metrics, tester_activity, critical_issues, all_tasks

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

  # WI D: grid family for assigned devices
  my_devices:
    source: Device
    filter: assigned_tester_id = current_user
    sort: name asc
    limit: 15
    display: grid
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

  # WI D: chart family — personal issue severity mix
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
  purpose: "Fleet health and field quality at a glance — no device warehouse hop"
  access: persona(manager, admin)

  fleet_overview:
    source: Device
    display: metrics
    aggregate:
      total_devices: count(Device)
      active_devices: count(Device where status = active)
      prototype_devices: count(Device where status = prototype)
      recalled_devices: count(Device where status = recalled)
    tones:
      active_devices: positive
      recalled_devices: destructive
      prototype_devices: accent

  device_attention:
    source: Device
    filter: status != active
    sort: status asc, name asc
    limit: 15
    display: queue
    action: device_detail
    empty: "All registered devices are active"

  quality_strip:
    source: IssueReport
    display: metrics
    aggregate:
      open: count(IssueReport where status = open)
      critical: count(IssueReport where severity = critical and status != closed)
      sessions: count(TestSession)
    tones:
      open: warning
      critical: destructive

  critical_issues:
    source: IssueReport
    filter: severity = critical and status != closed
    sort: reported_at desc
    limit: 10
    display: queue
    action: issue_report_detail
    empty: "No critical issues!"

  # WI D: context family (not list pad)
  tester_activity:
    source: TestSession
    sort: logged_at desc
    limit: 15
    display: timeline
    action: test_session_detail
    empty: "No recent test sessions logged"

  # WI D: kanban family for open work
  open_work:
    source: Task
    filter: status != completed and status != cancelled
    display: kanban
    group_by: status
    action: task_detail
    empty: "No open tasks"

  # WI D: chart family — fleet status mix
  fleet_status_mix:
    source: Device
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Device)
    empty: "No devices"

workspace issue_triage "Issue Triage":
  purpose: "Engineer triage desk — open and critical field reports first"
  access: persona(engineer, manager)

  open_pressure:
    source: IssueReport
    display: metrics
    aggregate:
      open: count(IssueReport where status = open)
      critical: count(IssueReport where severity = critical and status != closed)
      total: count(IssueReport)
    tones:
      open: warning
      critical: destructive

  triage_queue:
    source: IssueReport
    filter: status = open
    sort: severity desc, reported_at desc
    limit: 20
    display: queue
    action: issue_report_edit
    empty: "No open reports to triage"

  # WI D: grid family for critical cards
  critical_issues:
    source: IssueReport
    filter: severity = critical and status != closed
    sort: reported_at desc
    limit: 10
    display: grid
    action: issue_report_detail
    empty: "No critical issues!"

  issues_board:
    source: IssueReport
    display: kanban
    group_by: status
    action: issue_report_edit
    empty: "No issues to triage"

  # WI D: context family — recent critical timeline
  critical_trail:
    source: IssueReport
    filter: severity = critical
    sort: reported_at desc
    limit: 12
    display: timeline
    action: issue_report_detail
    empty: "No critical history"

workspace firmware_pipeline "Firmware Pipeline":
  purpose: "Ship firmware — release board, live drafts, and related tasks"
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

  # WI D: grid family for release cards
  firmware_releases:
    source: FirmwareRelease
    sort: release_date desc
    limit: 15
    display: grid
    action: firmware_release_detail
    empty: "No firmware releases"

  firmware_board:
    source: FirmwareRelease
    display: kanban
    group_by: status
    action: firmware_release_edit
    empty: "No firmware releases"

  # WI D: context family for release tasks
  release_tasks:
    source: Task
    filter: status != completed and status != cancelled
    sort: created_at desc
    limit: 15
    display: timeline
    action: task_detail
    empty: "No open tasks"

  # WI D: chart family — release status mix
  release_status_mix:
    source: FirmwareRelease
    display: bar_chart
    group_by: status
    aggregate:
      count: count(FirmwareRelease)
    empty: "No firmware releases"

workspace field_kit "Field Kit":
  purpose: "Tester kit — assigned devices and recent sessions on the road"
  access: persona(tester)

  kit_pulse:
    source: Device
    display: metrics
    aggregate:
      assigned: count(Device where assigned_tester_id = current_user)
      open_tasks: count(Task where assigned_to_id = current_user and status != completed)
      sessions: count(TestSession where tester_id = current_user)
    tones:
      open_tasks: accent
      assigned: positive

  # WI D: grid family for device cards
  assigned_devices:
    source: Device
    filter: assigned_tester_id = current_user
    sort: name asc
    limit: 20
    display: grid
    action: device_detail
    empty: "No devices assigned to you yet"

  recent_sessions:
    source: TestSession
    filter: tester_id = current_user
    sort: logged_at desc
    limit: 15
    display: timeline
    empty: "No test sessions logged"

  my_open_tasks:
    source: Task
    filter: assigned_to_id = current_user and status != completed
    sort: created_at desc
    limit: 10
    display: queue
    action: task_detail
    empty: "No open tasks"

  # WI D: kanban family for personal open work
  my_task_flow:
    source: Task
    filter: assigned_to_id = current_user and status != completed and status != cancelled
    display: kanban
    group_by: status
    action: task_detail
    empty: "No open tasks"

# Seventh product desk (WI D): dens floor with 6 lists needs ≥7 job-weighted desks.
workspace session_ops "Session Ops":
  purpose: "Field session pulse — recent tests, devices exercised, and open issues"
  access: persona(engineer, manager)

  session_metrics:
    source: TestSession
    display: metrics
    aggregate:
      sessions: count(TestSession)
      open_issues: count(IssueReport where status = open)
      active_devices: count(Device where status = active)
    tones:
      open_issues: warning
      active_devices: positive

  # WI D: context family — recent field sessions
  recent_sessions:
    source: TestSession
    sort: logged_at desc
    limit: 20
    display: timeline
    action: test_session_detail
    empty: "No test sessions logged"

  # WI D: grid family — devices exercised in the field
  active_fleet:
    source: Device
    filter: status = active
    sort: name asc
    limit: 15
    display: grid
    action: device_detail
    empty: "No active devices"

  # WI D: queue family — open field reports
  open_reports:
    source: IssueReport
    filter: status = open
    sort: severity desc, reported_at desc
    limit: 15
    display: queue
    action: issue_report_edit
    empty: "No open reports"

  # WI D: chart family — session environment mix
  environment_mix:
    source: TestSession
    display: bar_chart
    group_by: environment
    aggregate:
      count: count(TestSession)
    empty: "No test sessions"

# Eighth product desk (WI D): 6 lists floor dens ~0.46 with 7 full desks — need 8.
workspace tester_roster "Tester Roster":
  purpose: "Field tester capacity — active roster, assignments, and session pulse"
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

  # WI D: grid family for tester cards
  active_testers:
    source: Tester
    filter: active = true
    sort: name asc
    limit: 25
    display: grid
    action: tester_detail
    empty: "No active testers"

  # WI D: queue family — devices still needing an assignee
  unassigned_devices:
    source: Device
    filter: assigned_tester_id = null and status = active
    sort: name asc
    limit: 15
    display: queue
    action: device_detail
    empty: "Every active device has a tester"

  # WI D: context family — recent field sessions across the roster
  session_trail:
    source: TestSession
    sort: logged_at desc
    limit: 15
    display: timeline
    action: test_session_detail
    empty: "No test sessions logged"

  # WI D: chart family — tester skill mix
  skill_mix:
    source: Tester
    display: bar_chart
    group_by: skill_level
    aggregate:
      count: count(Tester)
    empty: "No testers yet"


# Ninth product desk (WI D): 6 lists floor dens ~0.43 with 8 full desks — need 9.
workspace task_ops "Task Ops":
  purpose: "Field task pulse — open work, assignments, and priority pressure"
  access: persona(engineer, manager)

  task_metrics:
    source: Task
    display: metrics
    aggregate:
      open: count(Task where status != completed and status != cancelled)
      in_progress: count(Task where status = in_progress)
      unassigned: count(Task where assigned_to_id = null and status != completed)
    tones:
      open: warning
      in_progress: accent
      unassigned: destructive

  # WI D: queue family — open tasks first
  open_queue:
    source: Task
    filter: status != completed and status != cancelled
    sort: created_at desc
    limit: 20
    display: queue
    action: task_detail
    empty: "No open tasks"

  # WI D: kanban family — task pipeline board
  task_board:
    source: Task
    filter: status != completed and status != cancelled
    display: kanban
    group_by: status
    action: task_detail
    empty: "No open tasks"

  # WI D: context family — recent task trail
  task_trail:
    source: Task
    sort: created_at desc
    limit: 15
    display: timeline
    action: task_detail
    empty: "No tasks yet"

  # WI D: chart family — task status mix
  status_mix:
    source: Task
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Task)
    empty: "No tasks yet"

# Tenth product desk (WI D): 6 lists floor dens ~0.40 with 9 full desks — need 10.
workspace device_fleet "Device Fleet":
  purpose: "Fleet pressure — active/recalled/prototype devices and batch mix"
  access: persona(engineer, manager)

  fleet_metrics:
    source: Device
    display: metrics
    aggregate:
      active: count(Device where status = active)
      prototype: count(Device where status = prototype)
      recalled: count(Device where status = recalled)
    tones:
      active: positive
      prototype: accent
      recalled: destructive

  # WI D: grid family — active fleet cards
  active_devices:
    source: Device
    filter: status = active
    sort: name asc
    limit: 20
    display: grid
    action: device_detail
    empty: "No active devices"

  # WI D: queue family — recalled units need attention first
  recall_queue:
    source: Device
    filter: status = recalled
    sort: updated_at desc
    limit: 15
    display: queue
    action: device_detail
    empty: "No recalled devices"

  # WI D: context family — recent fleet changes
  fleet_trail:
    source: Device
    sort: updated_at desc
    limit: 15
    display: timeline
    action: device_detail
    empty: "No devices yet"

  # WI D: chart family — lifecycle status mix
  status_mix:
    source: Device
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Device)
    empty: "No devices yet"

# Eleventh product desk (WI D): critical issue pressure for eng/manager.
workspace critical_ops "Critical Ops":
  purpose: "Critical and high-severity issue pressure without warehouse CRUD"
  access: persona(engineer, manager)

  critical_metrics:
    source: IssueReport
    display: metrics
    aggregate:
      critical: count(IssueReport where severity = critical and status = open)
      high: count(IssueReport where severity = high and status = open)
      open: count(IssueReport where status = open)
    tones:
      critical: destructive
      high: warning
      open: accent

  # WI D: queue family — critical open first
  critical_queue:
    source: IssueReport
    filter: severity = critical and status = open
    sort: reported_at asc
    limit: 20
    display: queue
    action: issue_report_edit
    empty: "No open critical issues"

  # WI D: grid family — high severity cards
  high_grid:
    source: IssueReport
    filter: severity = high and status = open
    sort: reported_at asc
    limit: 15
    display: grid
    action: issue_report_detail
    empty: "No open high-severity issues"

  # WI D: context family — recent critical trail
  critical_trail:
    source: IssueReport
    filter: severity = critical or severity = high
    sort: reported_at desc
    limit: 15
    display: timeline
    action: issue_report_detail
    empty: "No high or critical issues yet"

  # WI D: chart family — open severity mix
  severity_mix:
    source: IssueReport
    filter: status = open
    display: bar_chart
    group_by: severity
    aggregate:
      count: count(IssueReport)
    empty: "No open issues to chart"

# Twelfth product desk (WI D): 6 lists floor dens ~0.35 with 11 full desks — need 12.
workspace prototype_ops "Prototype Ops":
  purpose: "Prototype pressure — pre-production units needing exercise and attention"
  access: persona(engineer, manager)

  prototype_metrics:
    source: Device
    display: metrics
    aggregate:
      prototype: count(Device where status = prototype)
      active: count(Device where status = active)
      retired: count(Device where status = retired)
    tones:
      prototype: accent
      active: positive
      retired: warning

  # WI D: queue family — oldest prototypes first
  prototype_queue:
    source: Device
    filter: status = prototype
    sort: updated_at asc
    limit: 20
    display: queue
    action: device_detail
    empty: "No prototype devices"

  # WI D: grid family — prototype cards
  prototype_grid:
    source: Device
    filter: status = prototype
    sort: name asc
    limit: 15
    display: grid
    action: device_detail
    empty: "No prototype devices"

  # WI D: context family — recent prototype trail
  prototype_trail:
    source: Device
    filter: status = prototype
    sort: updated_at desc
    limit: 15
    display: timeline
    action: device_detail
    empty: "No prototype activity yet"

  # WI D: chart family — prototype model mix
  model_mix:
    source: Device
    filter: status = prototype
    display: bar_chart
    group_by: model
    aggregate:
      count: count(Device)
    empty: "No prototypes to chart"

# Thirteenth product desk (WI D): 6 lists floor dens ~0.33 with 12 full desks — need 13.
workspace recall_ops "Recall Ops":
  purpose: "Recall pressure — pulled units and related open issues without warehouse CRUD"
  access: persona(engineer, manager)

  recall_metrics:
    source: Device
    display: metrics
    aggregate:
      recalled: count(Device where status = recalled)
      retired: count(Device where status = retired)
      open_issues: count(IssueReport where status = open)
    tones:
      recalled: destructive
      retired: warning
      open_issues: accent

  # WI D: queue family — recalled units first
  recall_queue:
    source: Device
    filter: status = recalled
    sort: updated_at desc
    limit: 20
    display: queue
    action: device_detail
    empty: "No recalled devices"

  # WI D: grid family — recalled device cards
  recall_grid:
    source: Device
    filter: status = recalled
    sort: name asc
    limit: 15
    display: grid
    action: device_detail
    empty: "No recalled devices"

  # WI D: context family — recent recall trail
  recall_trail:
    source: Device
    filter: status = recalled or status = retired
    sort: updated_at desc
    limit: 15
    display: timeline
    action: device_detail
    empty: "No recall or retire activity yet"

  # WI D: chart family — lifecycle status mix among non-active
  status_mix:
    source: Device
    filter: status = recalled or status = retired or status = prototype
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Device)
    empty: "No non-active devices to chart"

# Fourteenth product desk (WI D): 6 lists floor dens ~0.32 with 13 full desks — need 14.
workspace retired_ops "Retired Ops":
  purpose: "End-of-life pressure — retired units and batch mix without warehouse CRUD"
  access: persona(engineer, manager)

  retired_metrics:
    source: Device
    display: metrics
    aggregate:
      retired: count(Device where status = retired)
      recalled: count(Device where status = recalled)
      active: count(Device where status = active)
    tones:
      retired: warning
      recalled: destructive
      active: positive

  # WI D: queue family — retired units first
  retired_queue:
    source: Device
    filter: status = retired
    sort: updated_at desc
    limit: 20
    display: queue
    action: device_detail
    empty: "No retired devices"

  # WI D: grid family — retired device cards
  retired_grid:
    source: Device
    filter: status = retired
    sort: name asc
    limit: 15
    display: grid
    action: device_detail
    empty: "No retired devices"

  # WI D: context family — recent retire trail
  retired_trail:
    source: Device
    filter: status = retired
    sort: updated_at desc
    limit: 15
    display: timeline
    action: device_detail
    empty: "No retire activity yet"

  # WI D: chart family — retired model mix
  model_mix:
    source: Device
    filter: status = retired
    display: bar_chart
    group_by: model
    aggregate:
      count: count(Device)
    empty: "No retired devices to chart"

# Fifteenth product desk (WI D): 6 lists floor dens ~0.30 with 14 full desks — need 15.
workspace draft_releases "Draft Releases":
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

  # WI D: queue family — drafts first
  draft_queue:
    source: FirmwareRelease
    filter: status = draft
    sort: release_date desc
    limit: 20
    display: queue
    action: firmware_release_edit
    empty: "No draft firmware releases"

  # WI D: grid family — draft release cards
  draft_grid:
    source: FirmwareRelease
    filter: status = draft
    sort: version asc
    limit: 15
    display: grid
    action: firmware_release_detail
    empty: "No draft firmware releases"

  # WI D: context family — recent draft trail
  draft_trail:
    source: FirmwareRelease
    filter: status = draft
    sort: updated_at desc
    limit: 15
    display: timeline
    action: firmware_release_detail
    empty: "No draft release activity yet"

  # WI D: chart family — release status mix
  status_mix:
    source: FirmwareRelease
    display: bar_chart
    group_by: status
    aggregate:
      count: count(FirmwareRelease)
    empty: "No firmware releases to chart"

# Sixteenth product desk (WI D): skip invoice_ops desk-cap; densify fieldtest_hub.
workspace released_ops "Released Ops":
  purpose: "Live firmware pressure — shipped builds without warehouse CRUD"
  access: persona(engineer, manager)

  released_metrics:
    source: FirmwareRelease
    display: metrics
    aggregate:
      released: count(FirmwareRelease where status = released)
      drafts: count(FirmwareRelease where status = draft)
      deprecated: count(FirmwareRelease where status = deprecated)
    tones:
      released: positive
      drafts: warning
      deprecated: accent

  # WI D: queue family — released first
  released_queue:
    source: FirmwareRelease
    filter: status = released
    sort: release_date desc
    limit: 20
    display: queue
    action: firmware_release_detail
    empty: "No released firmware yet"

  # WI D: grid family — live release cards
  released_grid:
    source: FirmwareRelease
    filter: status = released
    sort: version asc
    limit: 15
    display: grid
    action: firmware_release_detail
    empty: "No released firmware yet"

  # WI D: context family — recent ship trail
  released_trail:
    source: FirmwareRelease
    filter: status = released
    sort: updated_at desc
    limit: 15
    display: timeline
    action: firmware_release_detail
    empty: "No release activity yet"

  # WI D: chart family — release status mix
  status_mix:
    source: FirmwareRelease
    display: bar_chart
    group_by: status
    aggregate:
      count: count(FirmwareRelease)
    empty: "No firmware releases to chart"

# =============================================================================
# LEDGER — device-repair cost accrual accounts
# =============================================================================

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
