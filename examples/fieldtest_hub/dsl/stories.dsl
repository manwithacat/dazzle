story ST-019 "Engineer creates a new Device":
  status: accepted
  executed_by: surface.device_create
  persona: engineer
  trigger: form_submitted
  entities: [Device]
  given:
    - "Engineer has permission to create Device"
  then:
    - "New Device is saved to database"
    - "Engineer sees confirmation message"

story ST-020 "Engineer changes Device from prototype to active":
  status: accepted
  executed_by: surface.device_edit
  persona: engineer
  trigger: status_changed
  entities: [Device]
  given:
    - "Device.status is 'prototype'"
  then:
    - "Device.status becomes 'active'"

story ST-021 "Engineer changes Device from active to recalled":
  status: accepted
  executed_by: surface.device_edit
  persona: engineer
  trigger: status_changed
  entities: [Device]
  given:
    - "Device.status is 'active'"
  then:
    - "Device.status becomes 'recalled'"

story ST-022 "Engineer changes Device from active to retired":
  status: accepted
  executed_by: surface.device_edit
  persona: engineer
  trigger: status_changed
  entities: [Device]
  given:
    - "Device.status is 'active'"
  then:
    - "Device.status becomes 'retired'"

story ST-023 "Engineer creates a new Tester":
  status: accepted
  executed_by: surface.tester_create
  persona: engineer
  trigger: form_submitted
  entities: [Tester]
  given:
    - "Engineer has permission to create Tester"
  then:
    - "New Tester is saved to database"
    - "Engineer sees confirmation message"

story ST-024 "Engineer creates a new Issue Report":
  status: accepted
  executed_by: surface.issue_report_create
  persona: engineer
  trigger: form_submitted
  entities: [IssueReport]
  given:
    - "Engineer has permission to create IssueReport"
  then:
    - "New IssueReport is saved to database"
    - "Engineer sees confirmation message"

story ST-025 "Engineer changes IssueReport from open to triaged":
  status: accepted
  executed_by: surface.issue_report_edit
  persona: engineer
  trigger: status_changed
  entities: [IssueReport]
  given:
    - "IssueReport.status is 'open'"
  then:
    - "IssueReport.status becomes 'triaged'"

story ST-026 "Engineer changes IssueReport from triaged to in_progress":
  status: accepted
  executed_by: surface.issue_report_edit
  persona: engineer
  trigger: status_changed
  entities: [IssueReport]
  given:
    - "IssueReport.status is 'triaged'"
  then:
    - "IssueReport.status becomes 'in_progress'"

story ST-027 "Engineer changes IssueReport from in_progress to fixed":
  status: accepted
  executed_by: surface.issue_report_edit
  persona: engineer
  trigger: status_changed
  entities: [IssueReport]
  given:
    - "IssueReport.status is 'in_progress'"
  then:
    - "IssueReport.status becomes 'fixed'"

story ST-028 "Engineer creates a new Test Session":
  status: accepted
  executed_by: surface.test_session_create
  persona: engineer
  trigger: form_submitted
  entities: [TestSession]
  given:
    - "Engineer has permission to create TestSession"
  then:
    - "New TestSession is saved to database"
    - "Engineer sees confirmation message"

story ST-029 "Engineer creates a new Firmware Release":
  status: accepted
  executed_by: surface.firmware_release_create
  persona: engineer
  trigger: form_submitted
  entities: [FirmwareRelease]
  given:
    - "Engineer has permission to create FirmwareRelease"
  then:
    - "New FirmwareRelease is saved to database"
    - "Engineer sees confirmation message"

story ST-030 "Engineer changes FirmwareRelease from draft to released":
  status: accepted
  executed_by: surface.firmware_release_edit
  persona: engineer
  trigger: status_changed
  entities: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'draft'"
  then:
    - "FirmwareRelease.status becomes 'released'"

story ST-031 "Engineer changes FirmwareRelease from released to deprecated":
  status: accepted
  executed_by: surface.firmware_release_edit
  persona: engineer
  trigger: status_changed
  entities: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'released'"
  then:
    - "FirmwareRelease.status becomes 'deprecated'"

story ST-032 "Engineer changes FirmwareRelease from deprecated to draft":
  status: accepted
  executed_by: surface.firmware_release_edit
  persona: engineer
  trigger: status_changed
  entities: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'deprecated'"
  then:
    - "FirmwareRelease.status becomes 'draft'"

story ST-033 "Engineer creates a new Task":
  status: accepted
  executed_by: surface.task_create
  persona: engineer
  trigger: form_submitted
  entities: [Task]
  given:
    - "Engineer has permission to create Task"
  then:
    - "New Task is saved to database"
    - "Engineer sees confirmation message"

story ST-034 "Engineer changes Task from open to in_progress":
  status: accepted
  executed_by: surface.task_edit
  persona: engineer
  trigger: status_changed
  entities: [Task]
  given:
    - "Task.status is 'open'"
  then:
    - "Task.status becomes 'in_progress'"

story ST-035 "Engineer changes Task from in_progress to completed":
  status: accepted
  executed_by: surface.task_edit
  persona: engineer
  trigger: status_changed
  entities: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'completed'"

story ST-036 "Engineer changes Task from in_progress to open":
  status: accepted
  executed_by: surface.task_edit
  persona: engineer
  trigger: status_changed
  entities: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'open'"

story ST-037 "Engineer triages recent issue reports":
  status: accepted
  executed_by: surface.issue_report_list
  persona: engineer
  trigger: user_click
  entities: [IssueReport, Device]
  given:
    - "Engineer is on the engineering_dashboard workspace"
    - "IssueReports exist with status open"
  then:
    - "Engineer sees open reports in the triage_queue sorted by severity desc"
    - "Issue board row open hops to the Device hub via device_id"
    - "Engineer can transition a report from open to triaged"

story ST-038 "Engineer links firmware release to a device batch":
  status: accepted
  executed_by: surface.firmware_release_edit
  persona: engineer
  trigger: form_submitted
  entities: [FirmwareRelease, Device]
  given:
    - "FirmwareRelease exists with status 'draft'"
  then:
    - "FirmwareRelease.applies_to_batch is set"
    - "Devices matching the batch_number show the new firmware version"

story ST-039 "Engineer marks a device as recalled":
  status: accepted
  executed_by: surface.device_edit
  persona: engineer
  trigger: status_changed
  entities: [Device]
  given:
    - "Device.status is 'active'"
    - "A critical IssueReport references the device batch"
  then:
    - "Device.status becomes 'recalled'"
    - "Associated testers are notified"

story ST-040 "Manager reviews team workload":
  status: accepted
  executed_by: surface.device_list
  persona: manager
  trigger: user_click
  entities: [Task, Tester, Device]
  given:
    - "Manager is on the engineering_dashboard workspace"
  then:
    - "Manager sees fleet metrics and a non-active device attention queue"
    - "Manager sees open Tasks in a work queue"
    - "Opening a device hops to the Device hub with issues and sessions"

story ST-041 "Manager tracks release progress":
  status: accepted
  executed_by: surface.firmware_release_list
  persona: manager
  trigger: user_click
  entities: [FirmwareRelease]
  given:
    - "Manager is on the engineering_dashboard workspace"
    - "FirmwareReleases exist in various statuses"
  then:
    - "Manager sees release counts on the metrics strip"
    - "Manager can open firmware detail for draft vs released context"

story ST-042 "Field Tester reports a device issue":
  status: accepted
  executed_by: surface.issue_report_create
  persona: tester
  trigger: form_submitted
  entities: [IssueReport, Device]
  given:
    - "Field Tester is assigned to a Device with an issue"
  then:
    - "IssueReport is created with the Device reference and their id"
    - "IssueReport.status starts as 'open'"

story ST-043 "Field Tester logs a test session":
  status: accepted
  executed_by: surface.test_session_create
  persona: tester
  trigger: form_submitted
  entities: [TestSession, Device]
  given:
    - "Field Tester has completed a hands-on test"
  then:
    - "TestSession records the device, tester, environment, duration"
    - "Session appears in the tester's dashboard"

story ST-044 "Field Tester views devices assigned to them":
  status: accepted
  executed_by: surface.device_list
  persona: tester
  trigger: user_click
  entities: [Device]
  given:
    - "Field Tester is on their tester_dashboard"
  then:
    - "Field Tester sees only Devices where assigned_tester_id = self"
    - "Row open hops to Device hub to log a session or report an issue"

story ST-045 "Engineer opens device hub with issues and sessions":
  status: accepted
  executed_by: surface.device_detail
  persona: engineer
  trigger: user_click
  entities: [Device, IssueReport, TestSession]
  given:
    - "Device exists and is readable"
  then:
    - "Device hub shows production strip, assignment, related issues, and sessions"

story ST-046 "Engineer opens issue then hops to device context":
  status: accepted
  executed_by: surface.issue_report_list
  persona: engineer
  trigger: user_click
  entities: [IssueReport, Device]
  given:
    - "Engineer has list permission on IssueReport"
  then:
    - "Issue list open hops to Device via device_id"
    - "Device hub shows related IssueReports for the batch"

story ST-047 "Manager opens tester hub for assignments and activity":
  status: accepted
  executed_by: surface.tester_detail
  persona: manager
  trigger: user_click
  entities: [Tester, Device, Task, TestSession]
  given:
    - "Manager has list permission on Tester"
  then:
    - "Tester hub shows related testing activity and device/task assignments"
