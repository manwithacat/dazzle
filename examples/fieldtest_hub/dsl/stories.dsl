story ST-001 "Engineer creates a new Device":
  actor: Engineer
  trigger: form_submitted
  scope: [Device]
  given:
    - "Engineer has permission to create Device"
  then:
    - "New Device is saved to database"
    - "Engineer sees confirmation message"

story ST-002 "Engineer changes Device from prototype to active":
  actor: Engineer
  trigger: status_changed
  scope: [Device]
  given:
    - "Device.status is 'prototype'"
  then:
    - "Device.status becomes 'active'"
    - "Timestamp is recorded"

story ST-003 "Engineer changes Device from active to recalled":
  actor: Engineer
  trigger: status_changed
  scope: [Device]
  given:
    - "Device.status is 'active'"
  then:
    - "Device.status becomes 'recalled'"
    - "Timestamp is recorded"

story ST-004 "Engineer changes Device from active to retired":
  actor: Engineer
  trigger: status_changed
  scope: [Device]
  given:
    - "Device.status is 'active'"
  then:
    - "Device.status becomes 'retired'"
    - "Timestamp is recorded"

story ST-005 "Engineer creates a new Tester":
  actor: Engineer
  trigger: form_submitted
  scope: [Tester]
  given:
    - "Engineer has permission to create Tester"
  then:
    - "New Tester is saved to database"
    - "Engineer sees confirmation message"

story ST-006 "Engineer creates a new Issue Report":
  actor: Engineer
  trigger: form_submitted
  scope: [IssueReport]
  given:
    - "Engineer has permission to create IssueReport"
  then:
    - "New IssueReport is saved to database"
    - "Engineer sees confirmation message"

story ST-007 "Engineer changes IssueReport from open to triaged":
  actor: Engineer
  trigger: status_changed
  scope: [IssueReport]
  given:
    - "IssueReport.status is 'open'"
  then:
    - "IssueReport.status becomes 'triaged'"
    - "Timestamp is recorded"

story ST-008 "Engineer changes IssueReport from triaged to in_progress":
  actor: Engineer
  trigger: status_changed
  scope: [IssueReport]
  given:
    - "IssueReport.status is 'triaged'"
  then:
    - "IssueReport.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-009 "Engineer changes IssueReport from in_progress to fixed":
  actor: Engineer
  trigger: status_changed
  scope: [IssueReport]
  given:
    - "IssueReport.status is 'in_progress'"
  then:
    - "IssueReport.status becomes 'fixed'"
    - "Timestamp is recorded"

story ST-010 "Engineer creates a new Test Session":
  actor: Engineer
  trigger: form_submitted
  scope: [TestSession]
  given:
    - "Engineer has permission to create TestSession"
  then:
    - "New TestSession is saved to database"
    - "Engineer sees confirmation message"

story ST-011 "Engineer creates a new Firmware Release":
  actor: Engineer
  trigger: form_submitted
  scope: [FirmwareRelease]
  given:
    - "Engineer has permission to create FirmwareRelease"
  then:
    - "New FirmwareRelease is saved to database"
    - "Engineer sees confirmation message"

story ST-012 "Engineer changes FirmwareRelease from draft to released":
  actor: Engineer
  trigger: status_changed
  scope: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'draft'"
  then:
    - "FirmwareRelease.status becomes 'released'"
    - "Timestamp is recorded"

story ST-013 "Engineer changes FirmwareRelease from released to deprecated":
  actor: Engineer
  trigger: status_changed
  scope: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'released'"
  then:
    - "FirmwareRelease.status becomes 'deprecated'"
    - "Timestamp is recorded"

story ST-014 "Engineer changes FirmwareRelease from deprecated to draft":
  actor: Engineer
  trigger: status_changed
  scope: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'deprecated'"
  then:
    - "FirmwareRelease.status becomes 'draft'"
    - "Timestamp is recorded"

story ST-015 "Engineer creates a new Task":
  actor: Engineer
  trigger: form_submitted
  scope: [Task]
  given:
    - "Engineer has permission to create Task"
  then:
    - "New Task is saved to database"
    - "Engineer sees confirmation message"

story ST-016 "Engineer changes Task from open to in_progress":
  actor: Engineer
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'open'"
  then:
    - "Task.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-017 "Engineer changes Task from in_progress to completed":
  actor: Engineer
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'completed'"
    - "Timestamp is recorded"

story ST-018 "Engineer changes Task from in_progress to open":
  actor: Engineer
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'open'"
    - "Timestamp is recorded"

story ST-019 "Engineer creates a new Device":
  status: accepted
  actor: Engineer
  trigger: form_submitted
  scope: [Device]
  given:
    - "Engineer has permission to create Device"
  then:
    - "New Device is saved to database"
    - "Engineer sees confirmation message"

story ST-020 "Engineer changes Device from prototype to active":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [Device]
  given:
    - "Device.status is 'prototype'"
  then:
    - "Device.status becomes 'active'"

story ST-021 "Engineer changes Device from active to recalled":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [Device]
  given:
    - "Device.status is 'active'"
  then:
    - "Device.status becomes 'recalled'"

story ST-022 "Engineer changes Device from active to retired":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [Device]
  given:
    - "Device.status is 'active'"
  then:
    - "Device.status becomes 'retired'"

story ST-023 "Engineer creates a new Tester":
  status: accepted
  actor: Engineer
  trigger: form_submitted
  scope: [Tester]
  given:
    - "Engineer has permission to create Tester"
  then:
    - "New Tester is saved to database"
    - "Engineer sees confirmation message"

story ST-024 "Engineer creates a new Issue Report":
  status: accepted
  actor: Engineer
  trigger: form_submitted
  scope: [IssueReport]
  given:
    - "Engineer has permission to create IssueReport"
  then:
    - "New IssueReport is saved to database"
    - "Engineer sees confirmation message"

story ST-025 "Engineer changes IssueReport from open to triaged":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [IssueReport]
  given:
    - "IssueReport.status is 'open'"
  then:
    - "IssueReport.status becomes 'triaged'"

story ST-026 "Engineer changes IssueReport from triaged to in_progress":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [IssueReport]
  given:
    - "IssueReport.status is 'triaged'"
  then:
    - "IssueReport.status becomes 'in_progress'"

story ST-027 "Engineer changes IssueReport from in_progress to fixed":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [IssueReport]
  given:
    - "IssueReport.status is 'in_progress'"
  then:
    - "IssueReport.status becomes 'fixed'"

story ST-028 "Engineer creates a new Test Session":
  status: accepted
  actor: Engineer
  trigger: form_submitted
  scope: [TestSession]
  given:
    - "Engineer has permission to create TestSession"
  then:
    - "New TestSession is saved to database"
    - "Engineer sees confirmation message"

story ST-029 "Engineer creates a new Firmware Release":
  status: accepted
  actor: Engineer
  trigger: form_submitted
  scope: [FirmwareRelease]
  given:
    - "Engineer has permission to create FirmwareRelease"
  then:
    - "New FirmwareRelease is saved to database"
    - "Engineer sees confirmation message"

story ST-030 "Engineer changes FirmwareRelease from draft to released":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'draft'"
  then:
    - "FirmwareRelease.status becomes 'released'"

story ST-031 "Engineer changes FirmwareRelease from released to deprecated":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'released'"
  then:
    - "FirmwareRelease.status becomes 'deprecated'"

story ST-032 "Engineer changes FirmwareRelease from deprecated to draft":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [FirmwareRelease]
  given:
    - "FirmwareRelease.status is 'deprecated'"
  then:
    - "FirmwareRelease.status becomes 'draft'"

story ST-033 "Engineer creates a new Task":
  status: accepted
  actor: Engineer
  trigger: form_submitted
  scope: [Task]
  given:
    - "Engineer has permission to create Task"
  then:
    - "New Task is saved to database"
    - "Engineer sees confirmation message"

story ST-034 "Engineer changes Task from open to in_progress":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'open'"
  then:
    - "Task.status becomes 'in_progress'"

story ST-035 "Engineer changes Task from in_progress to completed":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'completed'"

story ST-036 "Engineer changes Task from in_progress to open":
  status: accepted
  actor: Engineer
  trigger: status_changed
  scope: [Task]
  given:
    - "Task.status is 'in_progress'"
  then:
    - "Task.status becomes 'open'"
