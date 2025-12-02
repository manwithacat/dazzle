# Operations Dashboard - Product Specification

> **Document Status**: Refined specification ready for DSL conversion
> **Complexity Level**: Intermediate+
> **DSL Features Demonstrated**: Personas, COMMAND_CENTER archetype, engine hints, aggregations

---

## Vision Statement

A real-time operations monitoring dashboard for DevOps and SRE teams. The command center interface enables engineers to monitor system health, respond to alerts, and maintain situational awareness across their infrastructure.

---

## User Personas

### Primary: Operations Engineer
- **Role**: DevOps engineer, SRE, or system administrator
- **Proficiency**: Expert - deep technical knowledge, daily monitoring use
- **Need**: Comprehensive visibility into system health at a glance
- **Pain Point**: Switching between multiple monitoring tools, missing critical alerts
- **Session Style**: Deep work - monitoring for extended periods
- **Goal**: Rapid identification and response to incidents

---

## Domain Model

### Entity: System

A monitored service or infrastructure component.

| Field | Type | Required | Default | Business Rules |
|-------|------|----------|---------|----------------|
| `id` | UUID | Yes | Auto | Immutable primary key |
| `name` | String(200) | Yes | - | Service name (e.g., "api-gateway-prod") |
| `service_type` | Enum | Yes | `web` | web, api, database, cache, queue |
| `status` | Enum | Yes | `healthy` | healthy, degraded, critical, offline |
| `response_time_ms` | Integer | No | - | Latency in milliseconds |
| `error_rate` | Decimal(5,2) | No | - | Error percentage (0.00-100.00) |
| `cpu_usage` | Decimal(5,2) | No | - | CPU utilization percentage |
| `memory_usage` | Decimal(5,2) | No | - | Memory utilization percentage |
| `last_check` | DateTime | Yes | Auto | Last health check timestamp |
| `created_at` | DateTime | Yes | Auto | When system was added to monitoring |

### Entity: Alert

An incident or warning requiring attention.

| Field | Type | Required | Default | Business Rules |
|-------|------|----------|---------|----------------|
| `id` | UUID | Yes | Auto | Immutable primary key |
| `system` | Ref(System) | Yes | - | Which system triggered the alert |
| `severity` | Enum | Yes | `low` | low, medium, high, critical |
| `message` | String(500) | Yes | - | Alert description |
| `triggered_at` | DateTime | Yes | Auto | When alert was triggered |
| `acknowledged` | Boolean | Yes | `false` | Has someone seen this? |
| `acknowledged_by` | String(200) | No | - | Who acknowledged the alert |

---

## User Interface Specification

### Archetype: COMMAND_CENTER

The COMMAND_CENTER archetype provides a dense, expert-focused layout optimized for:
- High information density
- Real-time monitoring
- Quick alert response
- Multi-system visibility

### Layout Structure

```
+------------------------------------------------------------------+
|  HEADER: Critical alerts banner + status indicators               |
+------------------------------------------------------------------+
|         |                                    |                    |
| LEFT    |         MAIN GRID                  |      RIGHT         |
| RAIL    |     (2-4 column metrics)           |      RAIL          |
| Quick   |                                    |    Context &       |
| Actions |     System status cards            |    Details         |
|         |     Alert feed                     |                    |
|         |     Key metrics                    |                    |
+------------------------------------------------------------------+
|  FOOTER: System status summary + keyboard shortcuts               |
+------------------------------------------------------------------+
```

### Workspace: Command Center

**Purpose**: Real-time operations monitoring and incident response

**Signals**:

| Signal | Type | Purpose |
|--------|------|---------|
| `active_alerts` | Item List | Unacknowledged alerts sorted by severity |
| `system_status` | Table | All systems with current health status |
| `health_summary` | KPI | Aggregate metrics (total, healthy, critical counts) |

**Engine Hint**: `command_center` (forces archetype selection)

---

## User Stories & Acceptance Criteria

### US-1: Monitor System Health
**As an** operations engineer
**I want to** see the health status of all systems at a glance
**So that** I can identify problems immediately

**Acceptance Criteria**:
- [ ] Systems displayed in a status grid
- [ ] Color coding: green=healthy, yellow=degraded, red=critical, gray=offline
- [ ] Response time and error rate visible
- [ ] Auto-refresh every 30 seconds

**Test Flow**:
```
1. Open command center workspace
2. Verify all systems displayed
3. Verify status colors match system state
4. Verify metrics are current (last_check recent)
```

---

### US-2: Respond to Critical Alerts
**As an** operations engineer
**I want to** see and acknowledge critical alerts
**So that** I can respond to incidents quickly

**Acceptance Criteria**:
- [ ] Unacknowledged alerts shown prominently
- [ ] Sorted by severity (critical first)
- [ ] Can acknowledge alert with one click
- [ ] Shows which system triggered alert

**Test Flow**:
```
1. View active_alerts signal
2. Verify critical alerts at top
3. Click to acknowledge an alert
4. Verify alert marked as acknowledged
5. Verify acknowledged_by recorded
```

---

### US-3: View System Details
**As an** operations engineer
**I want to** drill into a specific system's metrics
**So that** I can investigate issues

**Acceptance Criteria**:
- [ ] Click system to see full details
- [ ] All metrics displayed (CPU, memory, response time, error rate)
- [ ] Related alerts shown
- [ ] Last check timestamp visible

---

### US-4: View Health Summary
**As an** operations engineer
**I want to** see aggregate health metrics
**So that** I understand overall system health

**Acceptance Criteria**:
- [ ] Total system count displayed
- [ ] Healthy system count displayed
- [ ] Critical system count displayed (highlighted if > 0)
- [ ] Average response time displayed

---

## Persona-Specific UX

### For Operations Engineer (Expert)

| Aspect | Configuration |
|--------|---------------|
| **Proficiency** | Expert - minimal guidance |
| **Session Style** | Deep work - sustained attention |
| **Scope** | All systems and alerts visible |
| **Purpose** | Full visibility for incident response |

This persona expects:
- Dense information presentation
- Keyboard shortcuts
- Quick actions without confirmation dialogs
- Technical metrics without simplification

---

## Technical Notes

### DSL Features Demonstrated
- **Persona definition**: `proficiency_level: expert`, `session_style: deep_work`
- **Engine hint**: Force COMMAND_CENTER archetype
- **Aggregations**: count, avg across system data
- **Filtered signals**: `acknowledged = false` for active alerts
- **Ref fields**: Alert references System

### Building on support_tickets
This example adds:
1. **Personas** - User proficiency and session style
2. **Engine hints** - Explicit archetype selection
3. **Aggregate signals** - KPI metrics from entity data
4. **Expert UX** - Dense information for power users

### Out of Scope (Intermediate+ Example)
- WebSocket real-time updates
- Incident management workflows
- Runbook automation
- External monitoring integrations
- Mobile responsive layout (command center is desktop-focused)

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Alert acknowledgment time | < 30 seconds | Time from alert to acknowledgment |
| System visibility | 100% | All systems visible on single screen |
| Information density | 20+ metrics | Visible without scrolling |

---

*This specification is designed to be converted to DAZZLE DSL. See `dsl/app.dsl` for the implementation.*
