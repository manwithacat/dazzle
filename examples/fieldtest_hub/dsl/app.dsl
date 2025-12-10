# DAZZLE - FieldTest Hub
# Distributed beta testing platform for hardware field testing
# Demonstrates v0.7.0 Business Logic Features:
# - State machines for device and issue lifecycle
# - Computed fields for metrics
# - Invariants for data validation
# - Access rules for role-based control

module fieldtest_hub.core

app fieldtest_hub "FieldTest Hub"

# =============================================================================
# PERSONAS
# =============================================================================

persona engineer "Engineer":
  goals:
    - "Monitor all devices and issues"
    - "Manage firmware releases"
    - "Coordinate testers"
  proficiency_level: expert
  session_style: deep_work

persona tester "Field Tester":
  goals:
    - "Report issues from the field"
    - "Log test sessions"
    - "Track assigned devices"
  proficiency_level: intermediate
  session_style: task_based

persona manager "Manager":
  goals:
    - "Track overall product quality"
    - "Monitor critical issues"
  proficiency_level: intermediate
  session_style: quick_check

# =============================================================================
# ENTITIES WITH v0.7 BUSINESS LOGIC
# =============================================================================

# Entity: Device
entity Device "Device":
  id: uuid pk
  name: str(200) required
  model: str(200) required
  batch_number: str(100) required
  serial_number: str(100) required unique
  firmware_version: str(50)
  status: enum[prototype,active,recalled,retired]=prototype
  assigned_tester_id: uuid
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

  # Access: engineers can modify, testers can view assigned
  access:
    read: role(engineer) or role(manager) or assigned_tester_id = current_user
    write: role(engineer)

  index batch_number
  index status
  index assigned_tester_id

# Entity: Tester
entity Tester "Tester":
  id: uuid pk
  name: str(200) required
  email: str(255) required unique
  location: str(200) required
  skill_level: enum[casual,enthusiast,engineer]=casual
  joined_at: datetime auto_add
  active: bool=true
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Invariant: testers must have valid email
  invariant: email != null

  # Access: engineers can manage testers
  access:
    read: role(engineer) or role(manager) or id = current_user
    write: role(engineer)

  index email
  index location

# Entity: IssueReport
entity IssueReport "Issue Report":
  id: uuid pk
  device_id: uuid required
  reported_by_id: uuid required
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

  # Access: testers see own issues, engineers see all
  access:
    read: reported_by_id = current_user or role(engineer) or role(manager)
    write: role(engineer)

  index device_id
  index severity, status
  index reported_by_id

# Entity: TestSession
entity TestSession "Test Session":
  id: uuid pk
  device_id: uuid required
  tester_id: uuid required
  duration_minutes: int
  environment: enum[indoor,outdoor,vehicle,industrial,other]=indoor
  temperature: decimal(5,2)
  notes: text
  logged_at: datetime auto_add
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Invariant: duration must be positive
  invariant: duration_minutes > 0

  # Access: testers see own sessions
  access:
    read: tester_id = current_user or role(engineer) or role(manager)
    write: tester_id = current_user or role(engineer)

  index device_id
  index tester_id
  index logged_at

# Entity: FirmwareRelease
entity FirmwareRelease "Firmware Release":
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

  # Access: only engineers can manage firmware
  access:
    read: role(engineer) or role(manager) or role(tester)
    write: role(engineer)

  index status
  index version

# Entity: Task
entity Task "Task":
  id: uuid pk
  type: enum[debugging,hardware_replacement,firmware_update,recall_request]=debugging
  created_by_id: uuid required
  assigned_to_id: uuid
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

  # Access: engineers can manage all tasks
  access:
    read: role(engineer) or role(manager) or assigned_to_id = current_user
    write: role(engineer) or assigned_to_id = current_user

  index status
  index assigned_to_id
  index created_by_id

# =============================================================================
# SURFACES
# =============================================================================

# Surface: Device Dashboard
surface device_list "Device Dashboard":
  uses entity Device
  mode: list

  section main "Devices":
    field name "Name"
    field model "Model"
    field batch_number "Batch"
    field firmware_version "Firmware"
    field status "Status"
    field serial_number "Serial"

  ux:
    purpose: "Monitor all field devices with status indicators"
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

    for engineer:
      scope: all
      purpose: "Manage all devices across batches"
      action_primary: device_create

    for tester:
      scope: assigned_tester_id = current_user
      purpose: "Your assigned devices"

# Surface: Device Detail
surface device_detail "Device Detail":
  uses entity Device
  mode: view

  section main "Device Information":
    field name "Name"
    field model "Model"
    field batch_number "Batch Number"
    field serial_number "Serial Number"
    field firmware_version "Firmware Version"
    field status "Status"
    field deployed_at "Deployed At"
    field created_at "Created"
    field updated_at "Last Updated"

  ux:
    purpose: "View complete device history and reports"

    for engineer:
      scope: all
      action_primary: device_edit

    for tester:
      scope: assigned_tester_id = current_user
      action_primary: issue_report_create

# Surface: Device Create
surface device_create "Register Device":
  uses entity Device
  mode: create

  section main "New Device":
    field name "Device Name"
    field model "Model"
    field batch_number "Batch Number"
    field serial_number "Serial Number"
    field firmware_version "Firmware Version"
    field status "Status"
    field assigned_tester_id "Assign to Tester"

  ux:
    purpose: "Register a new device for field testing"

    for engineer:
      defaults:
        status: prototype

# Surface: Device Edit
surface device_edit "Edit Device":
  uses entity Device
  mode: edit

  section main "Edit Device":
    field name "Device Name"
    field model "Model"
    field batch_number "Batch Number"
    field firmware_version "Firmware Version"
    field status "Status"
    field assigned_tester_id "Assign to Tester"

  ux:
    purpose: "Update device information and status"

    for engineer:
      scope: all

# Surface: Tester Directory
surface tester_list "Tester Directory":
  uses entity Tester
  mode: list

  section main "Testers":
    field name "Name"
    field email "Email"
    field location "Location"
    field skill_level "Skill Level"
    field active "Active"
    field joined_at "Joined"

  ux:
    purpose: "Manage field testers and device assignments"
    sort: name asc
    filter: location, skill_level, active
    search: name, email, location
    empty: "No testers registered yet. Add testers to begin field testing!"

    attention notice:
      when: active = false
      message: "Inactive tester"
      action: tester_detail

    for engineer:
      scope: all
      action_primary: tester_create

# Surface: Tester Detail
surface tester_detail "Tester Detail":
  uses entity Tester
  mode: view

  section main "Tester Information":
    field name "Name"
    field email "Email"
    field location "Location"
    field skill_level "Skill Level"
    field active "Active"
    field joined_at "Joined At"

  ux:
    purpose: "View tester details and activity"

    for engineer:
      scope: all
      action_primary: tester_edit

# Surface: Tester Create
surface tester_create "Register Tester":
  uses entity Tester
  mode: create

  section main "New Tester":
    field name "Name"
    field email "Email"
    field location "Location"
    field skill_level "Skill Level"
    field active "Active"

  ux:
    purpose: "Register a new field tester"

    for engineer:
      defaults:
        active: true

# Surface: Tester Edit
surface tester_edit "Edit Tester":
  uses entity Tester
  mode: edit

  section main "Edit Tester":
    field name "Name"
    field email "Email"
    field location "Location"
    field skill_level "Skill Level"
    field active "Active"

  ux:
    purpose: "Update tester information"

    for engineer:
      scope: all

# Surface: Issue Report Board
surface issue_report_list "Issue Board":
  uses entity IssueReport
  mode: list

  section main "Issue Reports":
    field device_id "Device"
    field category "Category"
    field severity "Severity"
    field status "Status"
    field description "Description"
    field reported_at "Reported"

  ux:
    purpose: "Track and triage field issues with Kanban workflow"
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

    for engineer:
      scope: all
      purpose: "Manage all field issues"
      action_primary: issue_report_create

    for tester:
      scope: reported_by_id = current_user
      purpose: "Track your reported issues"
      action_primary: issue_report_create

# Surface: Issue Report Detail
surface issue_report_detail "Issue Detail":
  uses entity IssueReport
  mode: view

  section main "Issue Information":
    field device_id "Device"
    field reported_by_id "Reported By"
    field category "Category"
    field severity "Severity"
    field description "Description"
    field steps_to_reproduce "Steps to Reproduce"
    field photo_url "Photo/Video"
    field firmware_version "Firmware Version"
    field status "Status"
    field resolution "Resolution"
    field reported_at "Reported At"

  ux:
    purpose: "View complete issue details and context"

    for engineer:
      scope: all
      action_primary: issue_report_edit

    for tester:
      scope: reported_by_id = current_user
      action_primary: issue_report_edit

# Surface: Issue Report Create
surface issue_report_create "Report Issue":
  uses entity IssueReport
  mode: create

  section main "New Issue Report":
    field device_id "Device"
    field category "Category"
    field severity "Severity"
    field description "Description"
    field steps_to_reproduce "Steps to Reproduce"
    field photo_url "Photo/Video URL"
    field firmware_version "Firmware Version"

  ux:
    purpose: "Fast capture of field problems with evidence"

    for tester:
      defaults:
        reported_by_id: current_user
        severity: medium

# Surface: Issue Report Edit
surface issue_report_edit "Update Issue":
  uses entity IssueReport
  mode: edit

  section main "Edit Issue":
    field category "Category"
    field severity "Severity"
    field description "Description"
    field steps_to_reproduce "Steps to Reproduce"
    field photo_url "Photo/Video URL"
    field status "Status"
    field resolution "Resolution"

  ux:
    purpose: "Update issue status and details"

    for engineer:
      scope: all

    for tester:
      scope: reported_by_id = current_user

# Surface: Test Session List
surface test_session_list "Test Sessions":
  uses entity TestSession
  mode: list

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

    for engineer:
      scope: all
      action_primary: test_session_create

    for tester:
      scope: tester_id = current_user
      action_primary: test_session_create

# Surface: Test Session Create
surface test_session_create "Log Test Session":
  uses entity TestSession
  mode: create

  section main "New Test Session":
    field device_id "Device"
    field tester_id "Tester"
    field duration_minutes "Duration (minutes)"
    field environment "Environment"
    field temperature "Temperature"
    field notes "Notes"

  ux:
    purpose: "Record field testing session details"

    for tester:
      defaults:
        tester_id: current_user
        environment: indoor

# Surface: Firmware Release Timeline
surface firmware_release_list "Firmware Releases":
  uses entity FirmwareRelease
  mode: list

  section main "Firmware Releases":
    field version "Version"
    field status "Status"
    field release_date "Release Date"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Track firmware versions and release history"
    sort: release_date desc
    filter: status, applies_to_batch
    search: version, release_notes
    empty: "No firmware releases yet."

    attention warning:
      when: status = deprecated
      message: "Deprecated firmware - upgrade recommended"
      action: firmware_release_detail

    for engineer:
      scope: all
      action_primary: firmware_release_create

# Surface: Firmware Release Detail
surface firmware_release_detail "Firmware Detail":
  uses entity FirmwareRelease
  mode: view

  section main "Firmware Information":
    field version "Version"
    field release_notes "Release Notes"
    field release_date "Release Date"
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "View firmware release details"

    for engineer:
      scope: all
      action_primary: firmware_release_edit

# Surface: Firmware Release Create
surface firmware_release_create "Create Firmware Release":
  uses entity FirmwareRelease
  mode: create

  section main "New Firmware Release":
    field version "Version"
    field release_notes "Release Notes"
    field release_date "Release Date"
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Create a new firmware release"

    for engineer:
      defaults:
        status: draft

# Surface: Firmware Release Edit
surface firmware_release_edit "Edit Firmware Release":
  uses entity FirmwareRelease
  mode: edit

  section main "Edit Firmware Release":
    field version "Version"
    field release_notes "Release Notes"
    field release_date "Release Date"
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Update firmware release"

    for engineer:
      scope: all

# Surface: Task List
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main "Tasks":
    field type "Type"
    field status "Status"
    field assigned_to_id "Assigned To"
    field created_at "Created"

  ux:
    purpose: "Track debugging and maintenance tasks"
    sort: status asc, created_at desc
    filter: type, status, assigned_to_id
    search: notes
    empty: "No tasks yet."

    for engineer:
      scope: all
      action_primary: task_create

# Surface: Task Detail
surface task_detail "Task Detail":
  uses entity Task
  mode: view

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

    for engineer:
      scope: all
      action_primary: task_edit

# Surface: Task Create
surface task_create "Create Task":
  uses entity Task
  mode: create

  section main "New Task":
    field type "Type"
    field assigned_to_id "Assign To"
    field notes "Notes"

  ux:
    purpose: "Create maintenance or debugging task"

    for engineer:
      defaults:
        created_by_id: current_user
        status: open

# Surface: Task Edit
surface task_edit "Edit Task":
  uses entity Task
  mode: edit

  section main "Edit Task":
    field type "Type"
    field assigned_to_id "Assign To"
    field status "Status"
    field notes "Notes"

  ux:
    purpose: "Update task status and assignment"

    for engineer:
      scope: all

# =============================================================================
# WORKSPACES
# =============================================================================

# Workspace: Engineering Dashboard
workspace engineering_dashboard "Engineering Dashboard":
  purpose: "Comprehensive field testing oversight"

  critical_issues:
    source: IssueReport
    filter: severity = critical and status != closed
    sort: reported_at desc
    limit: 10
    display: list
    action: issue_report_detail
    empty: "No critical issues!"

  recent_reports:
    source: IssueReport
    sort: reported_at desc
    limit: 20
    display: list
    action: issue_report_detail
    empty: "No recent reports"

  active_devices:
    source: Device
    filter: status = active
    sort: batch_number asc
    limit: 50
    display: grid
    action: device_detail
    empty: "No active devices"

  metrics:
    source: IssueReport
    aggregate:
      total_issues: count(IssueReport)
      critical: count(IssueReport where severity = critical)
      open: count(IssueReport where status = open)

  ux:
    for engineer:
      purpose: "Monitor field testing quality and issues"
      focus: critical_issues, metrics, recent_reports

    for manager:
      purpose: "Track product quality and field performance"
      focus: metrics, critical_issues

# Workspace: Tester Dashboard
workspace tester_dashboard "Tester Dashboard":
  purpose: "Personal field testing hub"

  my_devices:
    source: Device
    filter: assigned_tester_id = current_user
    sort: name asc
    limit: 10
    display: list
    action: device_detail
    empty: "No devices assigned to you yet"

  my_issues:
    source: IssueReport
    filter: reported_by_id = current_user
    sort: reported_at desc
    limit: 20
    display: list
    action: issue_report_detail
    empty: "No issues reported yet"

  my_sessions:
    source: TestSession
    filter: tester_id = current_user
    sort: logged_at desc
    limit: 10
    display: timeline
    empty: "No test sessions logged"

  my_stats:
    source: IssueReport
    aggregate:
      total_reports: count(IssueReport where reported_by_id = current_user)
      critical_found: count(IssueReport where reported_by_id = current_user and severity = critical)

  ux:
    for tester:
      purpose: "Your field testing activity"
      focus: my_devices, my_issues
