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
      as: ops_engineer, admin
    read: all
      as: ops_engineer, admin
    # v0.71.19 (#1123): System management is admin-only — `all as: admin`
    # mirrors the permit gate. Ops engineers can list/read but not mutate.
    create: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin

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
  # #999 — replaced `acknowledged: bool` with a 3-state lifecycle so
  # the alert_pipeline / ops_actions chart regions (lines 354/371/374/377)
  # can count by status name. Pre-fix those regions referenced
  # `where status = active|acknowledged|resolved` against an entity
  # that had no `status` field — silent zero-counts in the dashboard.
  status: enum[active,acknowledged,resolved]=active
  acknowledged_by: str(200)

  # Computed field: hours since alert was triggered
  hours_open: computed days_since(triggered_at)

  # Invariant: alerts past the active state must record who acknowledged.
  invariant: status = active or acknowledged_by != null

  # Access control
  permit:
    list: role(ops_engineer) or role(admin)
    read: role(ops_engineer) or role(admin)
    create: role(ops_engineer) or role(admin)
    update: role(ops_engineer) or role(admin)
    delete: role(admin)

  scope:
    list: all
      as: ops_engineer, admin
    read: all
      as: ops_engineer, admin
    # v0.71.19 (#1123): Alerts are operational records — engineers can
    # create + ack + resolve (update). Delete is admin-only (audit trail).
    create: all
      as: ops_engineer, admin
    update: all
      as: ops_engineer, admin
    delete: all
      as: admin

  fitness:
    repr_fields: [system, severity, message, status, triggered_at]

# v0.61.72 (#6) — single-row Integration entity for the
# confirm_action_panel demo. AegisMark UX patterns roadmap item #6
# uses this shape for the SIMS-sync opt-in: one record per tenant,
# state-machine drives the panel mode, audit tracks the transition.
entity Integration "Integration":
  id: uuid pk
  name: str(100) required
  status: enum[off,pending,live,revoked] = off
  enabled_at: datetime
  notes: str(500)

  audit: all

  permit:
    list: role(ops_engineer) or role(admin)
    read: role(ops_engineer) or role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

  scope:
    list: all
      as: ops_engineer, admin
    read: all
      as: ops_engineer, admin
    # v0.71.19 (#1123): single-row admin-managed config — admin-only on writes.
    create: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin

# =============================================================================
# Persona
# =============================================================================

persona admin "Administrator":
  # Product command center — not framework platform chrome (#1626).
  default_workspace: command_center

persona ops_engineer "Operations Engineer":
  goals:
    - "Monitor system health in real-time"
    - "Respond quickly to alerts"
  proficiency_level: expert
  session_style: deep_work
  default_workspace: command_center
  # WI N: job desks first — not auto entity-list soup
  uses nav ops_nav

# Curated sidebar: workspace destinations only (WI N).
nav ops_nav:
  group "Ops":
    command_center
    incident_review
    systems_desk
    alerts_desk
    integrations_desk
    critical_ops
    active_alerts
    resolved_alerts
    degraded_ops
    integration_ops

# =============================================================================
# Workspace - COMMAND_CENTER Stage
# =============================================================================

workspace command_center "Command Center":
  purpose: "Real-time operations monitoring and incident response"
  stage: "command_center"
  access: persona(ops_engineer, admin)
  # #1399 — SSE live push: cards update instantly on alert mutations; the
  # per-region `refresh: every 30s` below stays as a fallback heartbeat.
  live: on

  # Alert Feed - Shows active alerts. Live-refreshes (#1391) so the
  # on-call engineer sees new alerts without reloading — the region's
  # HTMX card re-fetches every 30s.
  active_alerts:
    source: Alert
    filter: status = active
    sort: severity desc, triggered_at desc
    limit: 20
    refresh: every 30s

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

  # System RAG board — a list region with the #1470 fixed-band RAG decorator:
  # `rag_on: error_rate` colours each cell green/amber/red against author
  # thresholds (WCAG-safe tone + icon + label), so an operator triages by
  # severity at a glance. Deterministic — no statistics, no LLM.
  system_rag:
    source: System
    display: list
    sort: name asc
    rag_on: error_rate
    tone_bands:
      - at: 5
        tone: destructive
      - at: 1
        tone: warning
      - at: 0
        tone: positive

  # System Response League — a plain list region with the #1470 outlier
  # decorator: `outlier_on: response_time_ms` flags rows whose response time
  # is a statistical outlier (IQR Tukey fences) vs the displayed systems, so
  # an operator spots the anomalously slow/fast box at a glance. WCAG-safe
  # (tone colour + ⚠ icon + high/low text). Reuses the list render + the
  # comparison slice's flag_outliers engine — no new query semantics.
  system_response_times:
    source: System
    display: list
    sort: name asc
    outlier_on: response_time_ms
    outlier_method: iqr
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
      healthy_count: count(System where status = healthy)
      critical_count: count(System where status = critical)
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

  # Alert Insight — deterministic grounded narrative (#1470). The framework
  # computes the real per-system alert counts and writes a scale/leader/outlier
  # summary above a trust block listing the underlying values — no LLM, so every
  # claim cites an exact number the operator can verify against the charts.
  alert_insight:
    source: Alert
    display: insight_summary
    group_by: system
    aggregate:
      count: count(Alert)

  # System League — ranked comparison of systems by alert volume (#1470).
  # `display: comparison` ranks the group_by buckets by the `rank_by`
  # aggregate and auto-flags statistical outliers (IQR Tukey fences) so an
  # operator sees at a glance which system is anomalously noisy/quiet. Reuses
  # the same scope-safe GROUP BY spine as bar_chart — no new query semantics.
  system_alert_league:
    source: Alert
    display: comparison
    group_by: system
    aggregate:
      count: count(Alert)
    rank_by: count
    order: desc
    outlier_method: iqr
    empty: "No alerts to rank"

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
    filter: status = active
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

  # ── #1015–#1018 region primitives (typed pilots, v0.67.2–v0.67.8) ─
  # Each of these new region kinds has its own typed config block on
  # WorkspaceRegion (cohort_strip_config / day_timeline_config /
  # task_inbox_config / entity_card_config). The DSL surface for those
  # config blocks is not yet parser-supported — these regions consume
  # the dispatch surface only and degrade to the unconfigured/empty
  # path until the data-resolution ship wires real source rows. Kept
  # in ops_dashboard because it's the framework's reference apartment
  # for "every display mode has a working consumer" (CI coverage gate).
  systems_strip:
    source: System
    display: cohort_strip
    cohort_strip_config:
      member_via: id
      default_lens: status
      lenses:
        - id: status
          label: Status
          primary: status
        - id: response_time
          label: "Response time"
          primary: response_time_ms
          threshold: 500

  ops_today:
    source: Alert
    display: day_timeline
    day_timeline_config:
      starts_at: triggered_at
      ends_at: triggered_at
      card: alert_card

  ops_inbox:
    source: Alert
    display: task_inbox
    task_inbox_config:
      empty_state: "All systems quiet."
      sources:
        - source: Alert
          filter: status = active
          as_task:
            icon: "alert-triangle"
            title: "{{ message }}"
            meta: "{{ severity }}"
        - source: Alert
          filter: status = acknowledged
          count_as: "alerts being worked"

  alert_360:
    source: Alert
    display: entity_card
    entity_card_config:
      scope_param: id
      sections:
        - name: halo
          mode: halo
          fields: [message, severity]
        - name: meta
          mode: flags
          fields: [status, acknowledged_by]
        - name: recent_alerts
          mode: mini_bars
          source: Alert
          fields: [hours_open, message]
          limit: 5
        - name: history
          mode: stamps
          source: Alert
          limit: 5
        - name: ops
          mode: quick_actions
          actions: [alert_create, alert_list]

  ux:
    as ops_engineer:
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
      active: count(Alert where status = active)
      resolved: count(Alert where status = resolved)
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
      critical: count(System where status = critical)
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

  # v0.61.72 (#6): confirm_action_panel demo. Single-row Integration
  # entity narrowed via filter; the panel reads `status` to switch
  # between off (checklist + dual-button), live (revoke), and
  # revoked (re-enable) modes. Audit footer auto-renders because
  # Integration has `audit: all`.
  integration_authorise:
    source: Integration
    display: confirm_action_panel
    state_field: status
    eyebrow: "Final authorisation"
    title: "Enable read-only telemetry sync"
    notice:
      title: "Switching on starts the first read cycle"
      body: "All access is logged with your account, IP address, and timestamp."
      tone: warning
    confirmations:
      - title: "I confirm I am authorised by the platform owner"
        caption: "Recorded in the audit log against my account"
      - title: "I authorise read-only access to the telemetry stream"
      - title: "I have reviewed the data scopes listed above"
        required: false
    primary_action: integration_enable
    secondary_action: integration_save_draft
    revoke: integration_revoke

  ux:
    as ops_engineer:
      scope: all
      purpose: "Pair-strip review of pending incidents"

# Third product workspace (WI density D): systems portfolio desk.
workspace systems_desk "Systems":
  purpose: "Fleet health desk — systems pulse, grid, queue, trail, and status mix"
  access: persona(ops_engineer, admin)

  fleet_pulse:
    source: System
    display: metrics
    aggregate:
      systems: count(System)
      critical: count(System where status = critical)
      alerts: count(Alert where status = active)
    tones:
      critical: destructive
      alerts: warning

  # WI D: grid family — fleet cards (not list pad)
  systems_grid:
    source: System
    sort: name asc
    limit: 20
    display: grid
    action: system_detail
    empty: "No systems registered"

  # WI D: queue family — degraded/critical first
  pressure_queue:
    source: System
    filter: status = degraded or status = critical
    sort: status desc, last_check desc
    limit: 15
    display: queue
    action: system_detail
    empty: "No degraded or critical systems"

  # WI D: context family — recent checks
  check_trail:
    source: System
    sort: last_check desc
    limit: 15
    display: timeline
    action: system_detail
    empty: "No systems yet"

  # WI D: chart family — health mix
  status_mix:
    source: System
    display: bar_chart
    group_by: status
    aggregate:
      count: count(System)
    empty: "No systems yet"

# Fourth product workspace (WI density D): alerts-first on-call desk.
workspace alerts_desk "Alerts":
  purpose: "On-call desk — active and recent alerts without warehouse CRUD"
  access: persona(ops_engineer, admin)

  alert_pulse:
    source: Alert
    display: metrics
    aggregate:
      active: count(Alert where status = active)
      resolved: count(Alert where status = resolved)
      systems: count(System)
    tones:
      active: warning
      resolved: positive

  active_queue:
    source: Alert
    filter: status = active
    sort: severity desc, triggered_at desc
    limit: 25
    display: queue
    empty: "No active alerts"

  # WI D: grid family — systems with pressure
  systems_grid:
    source: System
    filter: status = degraded or status = critical
    sort: name asc
    limit: 15
    display: grid
    action: system_detail
    empty: "No systems under pressure"

  # WI D: context family — recent alert trail
  alert_trail:
    source: Alert
    sort: triggered_at desc
    limit: 15
    display: timeline
    empty: "No alerts yet"

  # WI D: chart family — severity mix
  severity_mix:
    source: Alert
    display: bar_chart
    group_by: severity
    aggregate:
      count: count(Alert)
    empty: "No alerts yet"

# Fifth product desk (WI D): integrations pulse for ops engineers.
workspace integrations_desk "Integrations":
  purpose: "Integration health — pending/live/revoked connectors and notes trail"
  access: persona(ops_engineer, admin)

  integration_pulse:
    source: Integration
    display: metrics
    aggregate:
      total: count(Integration)
      live: count(Integration where status = live)
      pending: count(Integration where status = pending)
    tones:
      live: positive
      pending: warning

  # WI D: queue family — pending opt-ins first
  pending_queue:
    source: Integration
    filter: status = pending
    sort: name asc
    limit: 15
    display: queue
    empty: "No pending integrations"

  # WI D: grid family — live connectors
  live_grid:
    source: Integration
    filter: status = live
    sort: name asc
    limit: 20
    display: grid
    empty: "No live integrations"

  # WI D: context family — enablement trail
  enable_trail:
    source: Integration
    sort: enabled_at desc
    limit: 15
    display: timeline
    empty: "No integration activity yet"

  # WI D: chart family — status mix
  status_mix:
    source: Integration
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Integration)
    empty: "No integrations yet"

# Sixth product desk (WI D): skip invoice_ops desk-cap; densify ops_dashboard.
workspace critical_ops "Critical Ops":
  purpose: "Critical pressure — critical systems and high-severity alerts without warehouse CRUD"
  access: persona(ops_engineer, admin)

  critical_pulse:
    source: System
    display: metrics
    aggregate:
      critical: count(System where status = critical)
      degraded: count(System where status = degraded)
      active_alerts: count(Alert where status = active)
    tones:
      critical: destructive
      degraded: warning
      active_alerts: accent

  # WI D: queue family — critical systems first
  critical_queue:
    source: System
    filter: status = critical or status = degraded
    sort: status desc, name asc
    limit: 20
    display: queue
    action: system_edit
    empty: "No critical or degraded systems"

  # WI D: grid family — critical open alerts
  critical_alerts:
    source: Alert
    filter: severity = critical and status = active
    sort: triggered_at asc
    limit: 15
    display: grid
    empty: "No active critical alerts"

  # WI D: context family — recent alert trail
  alert_trail:
    source: Alert
    filter: severity = critical or severity = high
    sort: triggered_at desc
    limit: 15
    display: timeline
    empty: "No high or critical alerts yet"

  # WI D: chart family — system health mix
  status_mix:
    source: System
    display: bar_chart
    group_by: status
    aggregate:
      count: count(System)
    empty: "No systems to chart"

# Seventh product desk (WI D): skip invoice_ops desk-cap; densify ops_dashboard.
workspace active_alerts "Active Alerts":
  purpose: "Alert pressure — unacknowledged active incidents without warehouse CRUD"
  access: persona(ops_engineer, admin)

  alert_pulse:
    source: Alert
    display: metrics
    aggregate:
      active: count(Alert where status = active)
      acked: count(Alert where status = acknowledged)
      resolved: count(Alert where status = resolved)
    tones:
      active: destructive
      acked: warning
      resolved: positive

  # WI D: queue family — active alerts first
  active_queue:
    source: Alert
    filter: status = active
    sort: triggered_at asc
    limit: 20
    display: queue
    action: alert_detail
    empty: "No active alerts"

  # WI D: grid family — active alert cards
  active_grid:
    source: Alert
    filter: status = active
    sort: severity desc, triggered_at asc
    limit: 15
    display: grid
    action: alert_detail
    empty: "No active alerts"

  # WI D: context family — recent alert trail
  alert_trail:
    source: Alert
    filter: status = active or status = acknowledged
    sort: triggered_at desc
    limit: 15
    display: timeline
    action: alert_detail
    empty: "No open alert activity yet"

  # WI D: chart family — severity mix among active
  severity_mix:
    source: Alert
    filter: status = active
    display: bar_chart
    group_by: severity
    aggregate:
      count: count(Alert)
    empty: "No active alerts to chart"


# Eighth product desk (WI D): skip invoice/fieldtest/acme soft-cap; densify ops_dashboard.
workspace resolved_alerts "Resolved Alerts":
  purpose: "Close-out pressure — resolved incidents without warehouse CRUD"
  access: persona(ops_engineer, admin)

  resolved_pulse:
    source: Alert
    display: metrics
    aggregate:
      resolved: count(Alert where status = resolved)
      acked: count(Alert where status = acknowledged)
      active: count(Alert where status = active)
    tones:
      resolved: positive
      acked: warning
      active: destructive

  # WI D: queue family — resolved first
  resolved_queue:
    source: Alert
    filter: status = resolved
    sort: triggered_at desc
    limit: 20
    display: queue
    action: alert_detail
    empty: "No resolved alerts"

  # WI D: grid family — resolved cards
  resolved_grid:
    source: Alert
    filter: status = resolved
    sort: severity desc, triggered_at desc
    limit: 15
    display: grid
    action: alert_detail
    empty: "No resolved alerts"

  # WI D: context family — resolve trail
  resolve_trail:
    source: Alert
    filter: status = resolved or status = acknowledged
    sort: triggered_at desc
    limit: 15
    display: timeline
    action: alert_detail
    empty: "No close-out activity yet"

  # WI D: chart family — severity mix among resolved
  severity_mix:
    source: Alert
    filter: status = resolved
    display: bar_chart
    group_by: severity
    aggregate:
      count: count(Alert)
    empty: "No resolved alerts to chart"


# Ninth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify ops_dashboard.
workspace degraded_ops "Degraded Ops":
  purpose: "Degraded/offline system pressure without warehouse CRUD"
  access: persona(ops_engineer, admin)

  degraded_pulse:
    source: System
    display: metrics
    aggregate:
      degraded: count(System where status = degraded)
      offline: count(System where status = offline)
      healthy: count(System where status = healthy)
    tones:
      degraded: warning
      offline: destructive
      healthy: positive

  # WI D: queue family — degraded/offline first
  degraded_queue:
    source: System
    filter: status = degraded or status = offline
    sort: status desc, name asc
    limit: 20
    display: queue
    action: system_edit
    empty: "No degraded or offline systems"

  # WI D: grid family — degraded system cards
  degraded_grid:
    source: System
    filter: status = degraded or status = offline
    sort: name asc
    limit: 15
    display: grid
    action: system_edit
    empty: "No degraded or offline systems"

  # WI D: context family — system status trail
  system_trail:
    source: System
    filter: status = degraded or status = offline or status = critical
    sort: name asc
    limit: 15
    display: timeline
    action: system_edit
    empty: "No unhealthy systems yet"

  # WI D: chart family — system status mix
  status_mix:
    source: System
    display: bar_chart
    group_by: status
    aggregate:
      count: count(System)
    empty: "No systems to chart"


# Tenth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify ops_dashboard.
workspace integration_ops "Integration Ops":
  purpose: "Integration-wire pressure — pending/live/revoked connectors without warehouse CRUD"
  access: persona(ops_engineer, admin)

  integration_pulse:
    source: Integration
    display: metrics
    aggregate:
      live: count(Integration where status = live)
      pending: count(Integration where status = pending)
      revoked: count(Integration where status = revoked)
    tones:
      live: positive
      pending: warning
      revoked: muted

  # WI D: queue family — pending first
  pending_queue:
    source: Integration
    filter: status = pending or status = live
    sort: name asc
    limit: 20
    display: queue
    empty: "No pending or live integrations"

  # WI D: grid family — integration cards
  integration_grid:
    source: Integration
    filter: status != off
    sort: name asc
    limit: 15
    display: grid
    empty: "No active integrations"

  # WI D: context family — integration trail
  integration_trail:
    source: Integration
    sort: name asc
    limit: 15
    display: timeline
    empty: "No integration activity yet"

  # WI D: chart family — status mix
  status_mix:
    source: Integration
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Integration)
    empty: "No integrations to chart"

# =============================================================================
# Surfaces
# =============================================================================

surface system_list "Systems":
  uses entity System
  mode: list
  render: fragment
  open: System via id

  section main "Monitored Systems":
    field name "Name"
    field service_type "Type"
    field status "Status"
    field response_time_ms "Response Time (ms)"
    field error_rate "Error Rate"

  ux:
    purpose: "Review monitored systems — open a row for the system hub"
    sort: name asc
    filter: service_type, status
    search: name
    empty: "No systems registered. Add a system to begin monitoring."

surface system_detail "System Detail":
  uses entity System
  mode: view
  render: fragment

  section identity "Identity":
    field name "Name"
    field service_type "Type"

  section health "Health":
    layout: strip
    field status "Status"
    field last_check "Last Check"
    field response_time_ms "Response Time (ms)"
    field error_rate "Error Rate"

  section capacity "Capacity":
    field cpu_usage "CPU Usage"
    field memory_usage "Memory Usage"

  related alerts "Open alerts":
    display: table
    show: Alert
    columns: severity, message, status, triggered_at

  ux:
    purpose: "System hub — health strip and open alerts in one place"

surface system_create "Register System":
  uses entity System
  mode: create
  render: fragment
  access: persona(admin)
  section main "New System":
    field name "Name"
    field service_type "Service Type"
  ux:
    purpose: "Register a new system for monitoring"

surface system_edit "Edit System":
  uses entity System
  mode: edit
  render: fragment
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
  render: fragment
  section main "New Alert":
    field system "System"
    field severity "Severity"
    field message "Message"
  ux:
    purpose: "Manually create an alert for a system"

surface alert_list "Alerts":
  uses entity Alert
  mode: list
  render: fragment
  open: System via system

  section main "Active Alerts":
    field system "System"
    field severity "Severity"
    field message "Message"
    field triggered_at "Triggered"
    field status "Status"

  ux:
    purpose: "Review alerts by severity — open a row for the parent System hub"
    sort: triggered_at desc
    filter: severity, status
    search: message, acknowledged_by
    empty: "No alerts. All systems operational."

surface alert_detail "Alert Detail":
  uses entity Alert
  mode: view
  render: fragment

  section summary "Summary":
    field system "System"
    field message "Message"

  section severity "Severity":
    layout: strip
    field severity "Severity"
    field status "Status"
    field triggered_at "Triggered"
    field acknowledged_by "Acknowledged By"

  ux:
    purpose: "Inspect alert severity strip and parent System context"

surface alert_ack "Acknowledge Alert":
  uses entity Alert
  mode: edit
  render: fragment

  section main "Acknowledge":
    field status "Status"
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
