story ST-001 "Operations Engineer creates a new System":
  actor: ops_engineer
  trigger: form_submitted
  scope: [System]
  given:
    - "Operations Engineer has permission to create System"
  then:
    - "New System is saved to database"
    - "Operations Engineer sees confirmation message"

story ST-002 "Operations Engineer changes System from healthy to degraded":
  actor: ops_engineer
  trigger: status_changed
  scope: [System]
  given:
    - "System.status is 'healthy'"
  then:
    - "System.status becomes 'degraded'"
    - "Timestamp is recorded"

story ST-003 "Operations Engineer changes System from healthy to critical":
  actor: ops_engineer
  trigger: status_changed
  scope: [System]
  given:
    - "System.status is 'healthy'"
  then:
    - "System.status becomes 'critical'"
    - "Timestamp is recorded"

story ST-004 "Operations Engineer changes System from degraded to healthy":
  actor: ops_engineer
  trigger: status_changed
  scope: [System]
  given:
    - "System.status is 'degraded'"
  then:
    - "System.status becomes 'healthy'"
    - "Timestamp is recorded"

story ST-005 "Operations Engineer creates a new Alert":
  actor: ops_engineer
  trigger: form_submitted
  scope: [Alert]
  given:
    - "Operations Engineer has permission to create Alert"
  then:
    - "New Alert is saved to database"
    - "Operations Engineer sees confirmation message"
