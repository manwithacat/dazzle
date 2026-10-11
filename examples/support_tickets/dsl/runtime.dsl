# Runtime primitives — exercise the audit / tenancy primitives
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
