story ST-001 "Operations Engineer creates a new System":
  persona: ops_engineer
  trigger: form_submitted
  entities: [System]
  given:
    - "Operations Engineer has permission to create System"
  then:
    - "New System is saved to database"
    - "Operations Engineer sees confirmation message"

story ST-002 "Operations Engineer changes System from healthy to degraded":
  persona: ops_engineer
  trigger: status_changed
  entities: [System]
  given:
    - "System.status is 'healthy'"
  then:
    - "System.status becomes 'degraded'"
    - "Timestamp is recorded"

story ST-003 "Operations Engineer changes System from healthy to critical":
  persona: ops_engineer
  trigger: status_changed
  entities: [System]
  given:
    - "System.status is 'healthy'"
  then:
    - "System.status becomes 'critical'"
    - "Timestamp is recorded"

story ST-004 "Operations Engineer changes System from degraded to healthy":
  persona: ops_engineer
  trigger: status_changed
  entities: [System]
  given:
    - "System.status is 'degraded'"
  then:
    - "System.status becomes 'healthy'"
    - "Timestamp is recorded"

story ST-005 "Operations Engineer creates a new Alert":
  persona: ops_engineer
  trigger: form_submitted
  entities: [Alert]
  given:
    - "Operations Engineer has permission to create Alert"
  then:
    - "New Alert is saved to database"
    - "Operations Engineer sees confirmation message"

story ST-006 "Operations Engineer views all system health statuses at a glance":
  persona: ops_engineer
  trigger: user_click
  entities: [System]
  given:
    - "Operations Engineer is on the command_center workspace"
  then:
    - "Operations Engineer sees every System grouped by status"
    - "Critical and offline Systems are visually distinguished"

story ST-007 "Operations Engineer acknowledges an alert with one click":
  persona: ops_engineer
  trigger: user_click
  entities: [Alert]
  given:
    - "Alert.status = active"
  then:
    - "Alert.status becomes acknowledged"
    - "Alert.acknowledged_by records the Operations Engineer"

story ST-008 "Operations Engineer views alerts grouped by severity":
  persona: ops_engineer
  trigger: user_click
  entities: [Alert]
  given:
    - "Open Alerts exist across systems"
  then:
    - "Operations Engineer sees Alerts sorted by severity desc, triggered_at desc"
    - "Critical and high severity alerts appear above medium/low"

story ST-009 "Operations Engineer drills into a degraded system":
  persona: ops_engineer
  trigger: user_click
  entities: [System, Alert]
  given:
    - "System.status is 'degraded' or 'critical'"
  then:
    - "Operations Engineer sees the System detail with its open Alerts"
    - "Operations Engineer can transition status from the detail page"

story ST-010 "Operations Engineer reviews recent deploy history":
  persona: ops_engineer
  trigger: user_click
  entities: [System, Alert]
  given:
    - "System has transitioned through degraded / critical / offline states"
  then:
    - "Operations Engineer sees status-change timestamps per System"
    - "Operations Engineer can correlate each status change with its triggering Alerts"
