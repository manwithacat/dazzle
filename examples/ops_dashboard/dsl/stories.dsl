story ST-001 "Operations Engineer creates a new System":
  status: accepted
  executed_by: surface.system_create
  persona: ops_engineer
  trigger: form_submitted
  entities: [System]
  given:
    - "Operations Engineer has permission to create System"
  then:
    - "New System is saved to database"
    - "Operations Engineer sees confirmation message"

story ST-002 "Operations Engineer changes System from healthy to degraded":
  status: accepted
  executed_by: surface.system_edit
  persona: ops_engineer
  trigger: status_changed
  entities: [System]
  given:
    - "System.status is 'healthy'"
  then:
    - "System.status becomes 'degraded'"
    - "Timestamp is recorded"

story ST-003 "Operations Engineer changes System from healthy to critical":
  status: accepted
  executed_by: surface.system_edit
  persona: ops_engineer
  trigger: status_changed
  entities: [System]
  given:
    - "System.status is 'healthy'"
  then:
    - "System.status becomes 'critical'"
    - "Timestamp is recorded"

story ST-004 "Operations Engineer changes System from degraded to healthy":
  status: accepted
  executed_by: surface.system_edit
  persona: ops_engineer
  trigger: status_changed
  entities: [System]
  given:
    - "System.status is 'degraded'"
  then:
    - "System.status becomes 'healthy'"
    - "Timestamp is recorded"

story ST-005 "Operations Engineer creates a new Alert":
  status: accepted
  executed_by: surface.alert_create
  persona: ops_engineer
  trigger: form_submitted
  entities: [Alert]
  given:
    - "Operations Engineer has permission to create Alert"
  then:
    - "New Alert is saved to database"
    - "Operations Engineer sees confirmation message"

story ST-006 "Operations Engineer monitors health from the command center":
  status: accepted
  executed_by: surface.system_list
  persona: ops_engineer
  trigger: user_click
  entities: [System]
  given:
    - "Operations Engineer is on the command_center workspace"
  then:
    - "Operations Engineer sees health_summary metrics and system status at a glance"
    - "Critical systems are visually distinguished"
    - "Opening a system hops to the System detail hub"

story ST-007 "Operations Engineer acknowledges an alert from the ack queue":
  status: accepted
  executed_by: surface.alert_ack
  persona: ops_engineer
  trigger: user_click
  entities: [Alert]
  given:
    - "Operations Engineer is on the command_center workspace"
    - "Alert.status = active"
  then:
    - "Active alerts appear in the acknowledgement queue"
    - "Alert.status becomes acknowledged from the queue or detail"

story ST-008 "Operations Engineer triages alerts by severity then opens system context":
  status: accepted
  executed_by: surface.alert_list
  persona: ops_engineer
  trigger: user_click
  entities: [Alert, System]
  given:
    - "Operations Engineer is on the command_center workspace"
    - "Open Alerts exist across systems"
  then:
    - "Severity breakdown charts and the ack queue surface critical/high first"
    - "Alert row open hops to the System overview hub via system FK"

story ST-009 "Operations Engineer drills into a degraded system hub":
  status: accepted
  executed_by: surface.system_detail
  persona: ops_engineer
  trigger: user_click
  entities: [System, Alert]
  given:
    - "System.status is degraded or critical"
  then:
    - "System hub shows health strip and related open Alerts"
    - "Operations Engineer can transition status from the detail path"

story ST-010 "Operations Engineer reviews alert history against system health":
  status: accepted
  executed_by: surface.alert_detail
  persona: ops_engineer
  trigger: user_click
  entities: [System, Alert]
  given:
    - "System has transitioned through degraded / critical states"
  then:
    - "Alert detail shows severity strip and parent System"
    - "Operator correlates status-change timestamps with triggering Alerts"
