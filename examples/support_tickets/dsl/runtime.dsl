# Runtime primitives — exercise the audit / jobs / tenancy primitives
# shipped during the v0.63.43 → v0.63.74 cycle sweep.
#
# Goal: dogfood each declaration, find friction, document it.

module support_tickets.runtime

use support_tickets.core

# =============================================================================
# Multi-tenancy (#957)
# =============================================================================

tenancy:
  mode: shared_schema
  partition_key: tenant_id
  per_tenant_config:
    sla_response_minutes: int
    default_ticket_priority: str
    feature_internal_notes: bool

# =============================================================================
# Audit log (#956)
# =============================================================================

audit on Ticket:
  track: status, priority, assigned_to
  show_to: persona(agent, manager)
  retention: 90d

audit on Comment:
  track: content, is_internal
  show_to: persona(manager)
  retention: 30d

# =============================================================================
# Background jobs (#953)
# =============================================================================

# Trigger: when a ticket is marked critical, ping the on-call.
job notify_oncall_critical "Notify on-call for critical tickets":
  trigger: on_create Ticket when priority is_set
  run: app.jobs:notify_oncall
  retry: 3
  retry_backoff: exponential
  timeout: 30s

# Trigger: when a ticket is resolved, send the customer a survey.
# NOTE: field_changed syntax requires `Entity.field` (DOT separator) —
# `Entity field` parses cleanly but produces a non-firing trigger.
job send_resolution_survey "Send post-resolution survey":
  trigger: on_field_changed Ticket.status
  run: app.jobs:send_survey
  retry: 2

# Schedule: hourly stale-ticket check — anything open > 48h.
job stale_ticket_sweep "Stale-ticket sweep":
  schedule: cron("0 * * * *")
  run: app.jobs:flag_stale
  timeout: 5m

# Schedule: daily metrics roll-up — feeds manager dashboard.
job daily_metrics_rollup "Daily metrics roll-up":
  schedule: cron("0 1 * * *")
  run: app.jobs:rollup_metrics
  retry: 1
  timeout: 10m
