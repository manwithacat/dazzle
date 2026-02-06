# DAZZLE Operations Dashboard - COMMAND_CENTER Stage Example
# Demonstrates v0.7.0 Business Logic Features:
# - State machine for system status lifecycle
# - Invariants for metric validation
# - Access rules for operator roles
# - COMMAND_CENTER stage for dense expert interface

module ops_dashboard.core

app ops_dashboard "Operations Dashboard"

# =============================================================================
# Entities with v0.7.0 Business Logic
# =============================================================================

entity System "System":
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

  # Access: only operators and admins can modify
  access:
    read: role(operator) or role(admin)
    write: role(admin)

entity Alert "Alert":
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

  # Access: operators can acknowledge, admins can modify
  access:
    read: role(operator) or role(admin)
    write: role(operator) or role(admin)

# =============================================================================
# Persona
# =============================================================================

persona ops_engineer "Operations Engineer":
  goals:
    - "Monitor system health in real-time"
    - "Respond quickly to alerts"
  proficiency_level: expert
  session_style: deep_work

# =============================================================================
# Workspace - COMMAND_CENTER Stage
# =============================================================================

workspace command_center "Command Center":
  purpose: "Real-time operations monitoring and incident response"
  stage: "command_center"

  # Alert Feed - Shows active alerts
  active_alerts:
    source: Alert
    filter: acknowledged = false
    sort: severity desc, triggered_at desc
    limit: 20

  # System Status Grid
  system_status:
    source: System
    sort: status asc, name asc

  # Health Summary
  health_summary:
    source: System
    aggregate:
      total_systems: count(System)
      healthy_count: count(System WHERE status = 'healthy')
      critical_count: count(System WHERE status = 'critical')
      avg_response_time: avg(response_time_ms)

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
    sort: triggered_at desc
    filter: severity, acknowledged
    search: message, acknowledged_by
    empty: "No alerts. All systems operational."

surface alert_ack "Acknowledge Alert":
  uses entity Alert
  mode: edit

  section main "Acknowledge":
    field acknowledged "Acknowledged"
    field acknowledged_by "Acknowledged By"
