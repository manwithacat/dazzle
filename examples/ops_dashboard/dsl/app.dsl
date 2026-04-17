# DAZZLE Operations Dashboard - COMMAND_CENTER Stage Example
# Demonstrates v0.7.0 Business Logic Features:
# - State machine for system status lifecycle
# - Invariants for metric validation
# - Access rules for operator roles
# - COMMAND_CENTER stage for dense expert interface

module ops_dashboard.core

app ops_dashboard "Operations Dashboard":
  security_profile: basic

# =============================================================================
# Entities with v0.7.0 Business Logic
# =============================================================================

entity System "System":
  intent: "Monitor operational health and response characteristics of a backend service"
  domain: operations
  patterns: lifecycle, monitoring
  display_field: name
  id: uuid pk
  name: str(200) required
  service_type: enum[web,api,database,cache,queue]=web
  status: enum[healthy,degraded,critical,offline]=healthy
  response_time_ms: int
  error_rate: decimal(5,2)
  cpu_usage: decimal(5,2)
  memory_usage: decimal(5,2)
  last_check: datetime auto_update
  created_at: datetime auto_add

  # State machine: system status transitions
  transitions:
    healthy -> degraded
    healthy -> critical
    degraded -> healthy
    degraded -> critical
    critical -> degraded
    critical -> offline
    offline -> healthy: role(admin)
    * -> offline: role(admin)

  # Invariants: metrics must be within valid ranges
  invariant: cpu_usage >= 0 and cpu_usage <= 100
  invariant: memory_usage >= 0 and memory_usage <= 100
  invariant: error_rate >= 0 and error_rate <= 100

  # Access control
  permit:
    list: role(operator) or role(admin)
    read: role(operator) or role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

  scope:
    list: all
      for: operator, admin

  fitness:
    repr_fields: [name, service_type, status, response_time_ms, error_rate]

entity Alert "Alert":
  intent: "Record a time-bound operational incident on a monitored System until acknowledged"
  domain: operations
  patterns: event_log, audit_trail
  id: uuid pk
  system: ref System required
  severity: enum[low,medium,high,critical]=low
  message: str(500) required
  triggered_at: datetime auto_add
  acknowledged: bool = false
  acknowledged_by: str(200)

  # Computed field: hours since alert was triggered
  hours_open: computed days_since(triggered_at)

  # Invariant: acknowledged alerts must have acknowledger
  invariant: acknowledged = false or acknowledged_by != null

  # Access control
  permit:
    list: role(operator) or role(admin)
    read: role(operator) or role(admin)
    create: role(operator) or role(admin)
    update: role(operator) or role(admin)
    delete: role(admin)

  scope:
    list: all
      for: operator, admin

  fitness:
    repr_fields: [system, severity, message, acknowledged, triggered_at]

# =============================================================================
# Persona
# =============================================================================

persona admin "Administrator":
  default_workspace: _platform_admin

persona ops_engineer "Operations Engineer":
  goals:
    - "Monitor system health in real-time"
    - "Respond quickly to alerts"
  proficiency_level: expert
  session_style: deep_work
  default_workspace: command_center

# =============================================================================
# Workspace - COMMAND_CENTER Stage
# =============================================================================

workspace command_center "Command Center":
  purpose: "Real-time operations monitoring and incident response"
  stage: "command_center"
  access: persona(ops_engineer)

  # Alert Feed - Shows active alerts
  active_alerts:
    source: Alert
    filter: acknowledged = false
    sort: severity desc, triggered_at desc
    limit: 20

  # Alert Timeline — chronological event stream across all systems
  alert_timeline:
    source: Alert
    sort: triggered_at desc
    limit: 50
    display: timeline
    empty: "No alerts yet"

  # System Status Kanban — systems grouped by health state
  system_board:
    source: System
    display: kanban
    group_by: status
    action: system_edit
    empty: "No systems registered"

  # System Status Grid — canonical card-grid region. Kept explicit
  # (`display: grid`) so this workspace exercises the grid region
  # template in QA: previously no example app hit that path, which
  # hid the region_card + grid-item card-in-card regression.
  system_status:
    source: System
    display: grid
    sort: status asc, name asc
    action: system_detail
    empty: "No systems registered"

  # Health Summary — metrics tile region
  health_summary:
    source: System
    display: metrics
    aggregate:
      total_systems: count(System)
      healthy_count: count(System WHERE status = 'healthy')
      critical_count: count(System WHERE status = 'critical')
      avg_response_time: avg(response_time_ms)

  # Alert Volume — bar-chart distribution by severity
  alert_severity_breakdown:
    source: Alert
    display: bar_chart
    group_by: severity
    aggregate:
      count: count(Alert)
    empty: "No alerts"

  # Alert Heatmap — density of alerts by severity
  alert_heatmap:
    source: Alert
    display: heatmap
    group_by: severity
    aggregate:
      count: count(Alert)
    empty: "No alerts"

  # Acknowledgement Queue — review queue for unacked alerts
  ack_queue:
    source: Alert
    filter: acknowledged = false
    display: queue
    sort: severity desc, triggered_at desc
    action: alert_ack
    empty: "All alerts acknowledged"

  ux:
    for ops_engineer:
      scope: all
      purpose: "Full visibility into all systems and alerts"

# =============================================================================
# Surfaces
# =============================================================================

surface system_list "Systems":
  uses entity System
  mode: list

  section main "Monitored Systems":
    field name "Name"
    field service_type "Type"
    field status "Status"
    field response_time_ms "Response Time (ms)"
    field error_rate "Error Rate"

  ux:
    purpose: "Review all monitored systems and spot degraded or critical ones at a glance"
    sort: name asc
    filter: service_type, status
    search: name
    empty: "No systems registered. Add a system to begin monitoring."

surface system_detail "System Detail":
  uses entity System
  mode: view

  section main "System Details":
    field name "Name"
    field service_type "Type"
    field status "Status"
    field last_check "Last Check"
    field response_time_ms "Response Time (ms)"
    field error_rate "Error Rate"
    field cpu_usage "CPU Usage"
    field memory_usage "Memory Usage"

surface system_create "Register System":
  uses entity System
  mode: create
  access: persona(admin)
  section main "New System":
    field name "Name"
    field service_type "Service Type"
  ux:
    purpose: "Register a new system for monitoring"

surface system_edit "Edit System":
  uses entity System
  mode: edit
  access: persona(admin)
  section main "Edit System":
    field name "Name"
    field service_type "Service Type"
    field status "Status"
  ux:
    purpose: "Update system details and status"

surface alert_create "Create Alert":
  uses entity Alert
  mode: create
  section main "New Alert":
    field system "System"
    field severity "Severity"
    field message "Message"
  ux:
    purpose: "Manually create an alert for a system"

surface alert_list "Alerts":
  uses entity Alert
  mode: list

  section main "Active Alerts":
    field system "System"
    field severity "Severity"
    field message "Message"
    field triggered_at "Triggered"
    field acknowledged "Acknowledged"

  ux:
    purpose: "Review active alerts sorted by severity and acknowledge them as they're handled"
    sort: triggered_at desc
    filter: severity, acknowledged
    search: message, acknowledged_by
    empty: "No alerts. All systems operational."

surface alert_detail "Alert Detail":
  uses entity Alert
  mode: view

  section main "Alert":
    field system "System"
    field severity "Severity"
    field message "Message"
    field triggered_at "Triggered"
    field acknowledged "Acknowledged"
    field acknowledged_by "Acknowledged By"

  ux:
    purpose: "Inspect the full context of an alert and its acknowledgement status"

surface alert_ack "Acknowledge Alert":
  uses entity Alert
  mode: edit

  section main "Acknowledge":
    field acknowledged "Acknowledged"
    field acknowledged_by "Acknowledged By"

# =============================================================================
# SERVICE — upstream monitoring API registration
# =============================================================================

service datadog "Datadog Monitoring API":
  spec: url "https://api.datadoghq.com/api/v1/openapi.json"
  auth_profile: api_key_header header="DD-API-KEY"
  owner: "ops@example.com"

# =============================================================================
# INTEGRATION — external pager service for alert forwarding
# =============================================================================

integration pager_duty "PagerDuty":
  uses service datadog

  base_url: "https://events.pagerduty.com/v2"
  auth: api_key from env("PAGERDUTY_API_KEY")

  mapping forward_alert on Alert:
    trigger: on_create when severity = critical
    request: POST "/enqueue"
    map_response:
      dedup_key <- response.dedup_key

# =============================================================================
# FOREIGN_MODEL — Datadog monitor as source-of-truth
# =============================================================================

foreign_model DatadogMonitor from datadog "Datadog Monitor":
  key: monitor_id

  monitor_id: str(50) required
  name: str(200)
  query: str(500)
  threshold: decimal(10,2)
  last_triggered: datetime

# =============================================================================
# EXPERIENCE — guided incident response wizard
# =============================================================================

experience incident_response "Incident Response":
  start at step triage

  step triage:
    kind: surface
    surface alert_list
    on success -> step investigate

  step investigate:
    kind: surface
    surface alert_detail
    on success -> step acknowledge

  step acknowledge:
    kind: surface
    surface alert_ack
