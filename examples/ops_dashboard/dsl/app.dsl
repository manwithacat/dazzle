# DAZZLE Operations Dashboard - COMMAND_CENTER Stage Example
# Demonstrates v0.7.0 Business Logic Features:
# - State machine for system status lifecycle
# - Invariants for metric validation
# - Access rules for ops_engineer roles
# - COMMAND_CENTER stage for dense expert interface

module ops_dashboard.core

app ops_dashboard "Operations Dashboard":
  security_profile: basic
  # v0.61.43 (Phase B Patch 2): app-shell theme via the DSL.
  # Wins over [ui] theme in dazzle.toml — spec is the source of truth.
  theme: linear-dark

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
    list: role(ops_engineer) or role(admin)
    read: role(ops_engineer) or role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

  scope:
    list: all
      for: ops_engineer, admin

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
    list: role(ops_engineer) or role(admin)
    read: role(ops_engineer) or role(admin)
    create: role(ops_engineer) or role(admin)
    update: role(ops_engineer) or role(admin)
    delete: role(admin)

  scope:
    list: all
      for: ops_engineer, admin

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

  # Health Summary — metrics tile region. Picks up the v0.61.65
  # per-tile tones (#2) and v0.61.68 notice band (#7) from the
  # AegisMark UX patterns roadmap.
  health_summary:
    source: System
    display: metrics
    notice:
      title: "Status as of last sync"
      body: "Counts refresh every 30s; alert deltas use the prior 24h window."
      tone: accent
    aggregate:
      total_systems: count(System)
      healthy_count: count(System WHERE status = 'healthy')
      critical_count: count(System WHERE status = 'critical')
      avg_response_time: avg(response_time_ms)
    tones:
      healthy_count: positive
      critical_count: destructive

  # Alert Volume — bar-chart distribution by severity
  alert_severity_breakdown:
    source: Alert
    display: bar_chart
    group_by: severity
    aggregate:
      count: count(Alert)
    empty: "No alerts"

  # Alerts by System — FK distribution (Strategy C aggregate fast path).
  # Group by an FK column to exercise the LEFT JOIN + display-field
  # resolution path of Repository.aggregate. The bar labels render the
  # System.name (probed via display_name → name → title → label → code).
  alerts_by_system:
    source: Alert
    display: bar_chart
    group_by: system
    aggregate:
      count: count(Alert)
    empty: "No alerts grouped by system"

  # Pivot Table — multi-dimension cross-tab (cycle 25, v0.59.3).
  # Combines an FK dim (system) with a scalar enum dim (severity) so each
  # row is one (system, severity) cell with its count. Exercises the
  # multi-dim Repository.aggregate path: indexed FK aliases, multi-key
  # GROUP BY, label resolution.
  alert_pivot:
    source: Alert
    display: pivot_table
    group_by: [system, severity]
    aggregate:
      count: count(Alert)
    empty: "No alerts to pivot"

  # Alert Heatmap — density of alerts by severity
  alert_heatmap:
    source: Alert
    display: heatmap
    group_by: severity
    aggregate:
      count: count(Alert)
    empty: "No alerts"

  # Time-series: alerts per day (v0.60.0, cycle 28 — Strategy C time
  # bucket fast path). group_by: bucket(triggered_at, day) emits a single
  # date_trunc('day', triggered_at) GROUP BY query.
  alerts_timeseries:
    source: Alert
    display: line_chart
    group_by: bucket(triggered_at, day)
    aggregate:
      count: count(Alert)
    empty: "No alerts in the window"

  # Time-series stacked by severity: one area per severity level across
  # weeks. Exercises the two-dim BucketRef + scalar fast path.
  alerts_weekly_stacked:
    source: Alert
    display: area_chart
    group_by: [bucket(triggered_at, week), severity]
    aggregate:
      count: count(Alert)
    empty: "No alerts to stack"

  # Sparkline: daily volume for the last window — the compact tile form
  # of the time series. Shares the Strategy C fast path with line_chart.
  alerts_daily_sparkline:
    source: Alert
    display: sparkline
    group_by: bucket(triggered_at, day)
    aggregate:
      count: count(Alert)
    empty: "—"

  # Acknowledgement Queue — review queue for unacked alerts
  ack_queue:
    source: Alert
    filter: acknowledged = false
    display: queue
    sort: severity desc, triggered_at desc
    action: alert_ack
    empty: "All alerts acknowledged"

  # Histogram — distribution of response times across all systems with
  # an SLA threshold reference line. Exercises the v0.61.27 (#882) bin +
  # reference-line primitive: rows fetched via list query, binned in
  # Python via Sturges' rule, vertical reference line at 500ms.
  response_time_distribution:
    source: System
    display: histogram
    value: response_time_ms
    bins: auto
    reference_lines:
      - label: "SLA target", value: 500, style: dashed
    empty: "No system metrics yet"

  # Radar — service-type profile shape. Exercises the v0.61.28 (#879)
  # polar-chart pipeline: one spoke per service_type, value = system
  # count for that type. Single-series MVP works through the existing
  # Strategy C count fast path.
  service_type_profile:
    source: System
    display: radar
    group_by: service_type
    aggregate:
      systems: count(System where service_type = current_bucket)
    empty: "No systems registered"

  # Box plot — response-time spread per service_type. Exercises the
  # v0.61.29 (#881) per-group quartile pipeline: in-process Q1/median/
  # Q3 + Tukey 1.5×IQR whiskers + outlier dots, no SQL percentile_cont.
  response_time_spread:
    source: System
    display: box_plot
    group_by: service_type
    value: response_time_ms
    show_outliers: true
    reference_lines:
      - label: "SLA target", value: 500, style: dashed
    empty: "No system metrics yet"

  # Bullet — per-system response time vs reference bands. Exercises
  # the v0.61.30 (#880) Stephen Few primitive: one row per System,
  # actual = response_time_ms, comparative bands behind the bar
  # (positive < 250ms, warning 250–500ms, destructive > 500ms).
  system_response_bullet:
    source: System
    display: bullet
    bullet_label: name
    bullet_actual: response_time_ms
    reference_bands:
      - label: "Healthy", from: 0, to: 250, color: positive
      - label: "Watch",   from: 250, to: 500, color: warning
      - label: "Breach",  from: 500, to: 1000, color: destructive
    empty: "No system metrics yet"

  # Bar track — per-system response-time as a horizontal track. Same
  # data as the bullet above, different visual idiom. Exercises the
  # v0.61.53 (#893) bar_track display mode.
  system_response_track:
    source: System
    display: bar_track
    group_by: name
    aggregate:
      value: avg(response_time_ms)
    track_max: 1000
    track_format: "{:.0f}ms"
    empty: "No system metrics yet"

  # Action grid — operator CTAs surfacing common next-steps. Exercises
  # the v0.61.54 (#891) action_grid display mode. Each card carries an
  # independent count_aggregate that fires per-card.
  ops_actions:
    display: action_grid
    actions:
      - label: "Active alerts"
        icon: "alert-triangle"
        count_aggregate: count(Alert where status = active)
        action: alert_list
        tone: warning
      - label: "Add system"
        icon: "plus"
        action: system_create
        tone: positive

  # Pipeline steps — incident triage workflow. Exercises the v0.61.56
  # (#890) pipeline_steps display mode with per-stage values. The
  # final stage uses a literal-string value (v0.61.66 #4) to describe
  # a downstream system that has no entity backing — flow-card style.
  alert_pipeline:
    display: pipeline_steps
    stages:
      - label: "Active"
        caption: "currently firing"
        value: count(Alert where status = active)
      - label: "Acknowledged"
        caption: "an engineer is on it"
        value: count(Alert where status = acknowledged)
      - label: "Resolved"
        caption: "closed in this window"
        value: count(Alert where status = resolved)
      - label: "Audit"
        caption: "external compliance log"
        value: "Daily 02:00 UTC"

  # Status list — surface ops-readiness checks in a vertical row of
  # icon + title + copy + state-pill entries. Exercises the v0.61.69
  # (#3) status_list display mode (AegisMark UX patterns roadmap).
  ops_readiness:
    display: status_list
    entries:
      - title: "On-call rotation"
        caption: "Verified for the next 24h"
        icon: "user-check"
        state: positive
      - title: "Runbook coverage"
        caption: "All P1 alerts have linked runbooks"
        icon: "book-open"
        state: positive
      - title: "Pager test"
        caption: "Last weekly test 3 days ago"
        icon: "clock"
        state: warning
      - title: "Audit window"
        caption: "External SOC 2 evidence freeze in effect"
        icon: "shield"
        state: accent

  # Profile card — single-system identity panel. Exercises the v0.61.55
  # (#892) profile_card display mode with `filter: id = current_context`
  # narrowing to one row.
  system_identity:
    source: System
    display: profile_card
    filter: id = current_context
    primary: name
    secondary: "{{ service_type }}"
    stats:
      - label: "Status"
        value: status
      - label: "Response"
        value: response_time_ms

  ux:
    for ops_engineer:
      scope: all
      purpose: "Full visibility into all systems and alerts"

# =============================================================================
# Workspace - PAIR_STRIP Stage (v0.61.71, AegisMark UX patterns #5)
# =============================================================================
# Demonstrates the pair_strip stage layout — every region renders at
# half-width and CSS grid auto-flows them into rows of two. Used for
# explicit (info, action) pair flows where each row tells one part of
# a story. See AegisMark's `consent-grid` pattern in
# `static/prototypes/sims-sync-opt-in.html`. Mobile collapses to a
# single column via the project's responsive rules.

workspace incident_review "Incident Review":
  purpose: "Side-by-side pairs for change-management review"
  stage: "pair_strip"
  access: persona(ops_engineer)

  # Pair 1: alert overview + alert list
  alert_summary:
    source: Alert
    display: metrics
    aggregate:
      active: count(Alert WHERE acknowledged = false)
      resolved: count(Alert WHERE status = 'resolved')
    tones:
      active: warning
      resolved: positive

  recent_alerts:
    source: Alert
    sort: triggered_at desc
    limit: 5

  # Pair 2: system context + readiness checklist
  system_overview:
    source: System
    display: metrics
    aggregate:
      total: count(System)
      critical: count(System WHERE status = 'critical')
    tones:
      critical: destructive

  review_checklist:
    display: status_list
    notice:
      title: "Review checklist"
      body: "All four items must be confirmed before closing the incident."
      tone: accent
    entries:
      - title: "Root cause documented"
        caption: "Linked from the timeline section"
        icon: "file-text"
        state: positive
      - title: "Customer impact assessed"
        caption: "SLA breach window calculated"
        icon: "users"
        state: positive
      - title: "Postmortem scheduled"
        caption: "Within 48h of resolution"
        icon: "calendar"
        state: warning
      - title: "Runbook updated"
        caption: "Document any new mitigation steps"
        icon: "book-open"
        state: warning

  ux:
    for ops_engineer:
      scope: all
      purpose: "Pair-strip review of pending incidents"

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
